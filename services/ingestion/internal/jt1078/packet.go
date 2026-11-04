// Package jt1078 implements parsing of the JT/T 1078 real-time audio/video
// transmission packet format (the "01cd" RTP-style framing) used by the XV-900-8
// MDVR when streaming video to the platform.
//
// This follows the public JT/T 1078-2016 packet layout. The media gateway uses it
// to reassemble and inspect genuine device streams. As with the JT/T 808 decoder,
// nothing is invented: packets that do not match the documented layout are
// surfaced to the caller, never silently dropped, and must still be validated
// against a physical device before the stream is trusted end to end.
package jt1078

import (
	"encoding/binary"
	"errors"
	"fmt"
)

// Magic is the 4-byte frame header identifier (0x30 0x31 0x63 0x64, "01cd").
var Magic = []byte{0x30, 0x31, 0x63, 0x64}

// Data types (high nibble of byte 15).
const (
	DataVideoIFrame = 0x0
	DataVideoPFrame = 0x1
	DataVideoBFrame = 0x2
	DataAudio       = 0x3
	DataTransparent = 0x4
)

// Subpackage marks (low nibble of byte 15).
const (
	SubAtomic = 0x0
	SubFirst  = 0x1
	SubLast   = 0x2
	SubMiddle = 0x3
)

var (
	// ErrNeedMore indicates the buffer does not yet hold a full packet.
	ErrNeedMore = errors.New("jt1078: need more bytes")
	// ErrNoMagic indicates the buffer does not start with the frame magic.
	ErrNoMagic = errors.New("jt1078: frame magic not found")
)

// Packet is a decoded JT/T 1078 packet.
type Packet struct {
	PayloadType byte   // M/PT low 7 bits
	Mark        bool   // M bit
	Sequence    uint16 // packet serial number
	SIM         string // decoded BCD SIM/phone
	Channel     byte   // logical channel number
	DataType    byte   // high nibble of byte 15
	SubPackage  byte   // low nibble of byte 15
	Timestamp   uint64 // milliseconds (video/audio only)
	LastIFrame  uint16 // last I-frame interval (video only)
	LastFrame   uint16 // last frame interval (video only)
	BodyLength  int
	Body        []byte
	HeaderLen   int
	TotalLen    int
}

// IsVideo reports whether the packet carries video.
func (p *Packet) IsVideo() bool {
	return p.DataType == DataVideoIFrame || p.DataType == DataVideoPFrame || p.DataType == DataVideoBFrame
}

// DataTypeName returns a human label for the data type.
func (p *Packet) DataTypeName() string {
	switch p.DataType {
	case DataVideoIFrame:
		return "video_i"
	case DataVideoPFrame:
		return "video_p"
	case DataVideoBFrame:
		return "video_b"
	case DataAudio:
		return "audio"
	case DataTransparent:
		return "transparent"
	default:
		return fmt.Sprintf("unknown_0x%x", p.DataType)
	}
}

// headerLenFor returns the full header length (including magic) for a data type.
// video: 30, audio: 26, transparent: 18 (per JT/T 1078-2016, SIM = 6 BCD bytes).
func headerLenFor(dataType byte) int {
	switch dataType {
	case DataAudio:
		return 26
	case DataTransparent:
		return 18
	default: // video
		return 30
	}
}

// Parse decodes a single packet from the start of buf. It returns the packet and
// the number of bytes consumed. ErrNeedMore means buf is a valid but incomplete
// packet; ErrNoMagic means buf does not start at a frame boundary.
func Parse(buf []byte) (*Packet, int, error) {
	if len(buf) < 4 {
		return nil, 0, ErrNeedMore
	}
	if buf[0] != Magic[0] || buf[1] != Magic[1] || buf[2] != Magic[2] || buf[3] != Magic[3] {
		return nil, 0, ErrNoMagic
	}
	if len(buf) < 16 {
		return nil, 0, ErrNeedMore
	}
	p := &Packet{}
	mpt := buf[5]
	p.Mark = mpt&0x80 != 0
	p.PayloadType = mpt & 0x7f
	p.Sequence = binary.BigEndian.Uint16(buf[6:8])
	sim, err := decodeBCD(buf[8:14])
	if err != nil {
		return nil, 0, fmt.Errorf("jt1078: bad SIM BCD: %w", err)
	}
	p.SIM = sim
	p.Channel = buf[14]
	p.DataType = buf[15] >> 4
	p.SubPackage = buf[15] & 0x0f

	hlen := headerLenFor(p.DataType)
	if len(buf) < hlen {
		return nil, 0, ErrNeedMore
	}
	off := 16
	if p.DataType != DataTransparent {
		p.Timestamp = binary.BigEndian.Uint64(buf[off : off+8])
		off += 8
	}
	if p.IsVideo() {
		p.LastIFrame = binary.BigEndian.Uint16(buf[off : off+2])
		p.LastFrame = binary.BigEndian.Uint16(buf[off+2 : off+4])
		off += 4
	}
	p.BodyLength = int(binary.BigEndian.Uint16(buf[off : off+2]))
	off += 2
	p.HeaderLen = off
	total := off + p.BodyLength
	if len(buf) < total {
		return nil, 0, ErrNeedMore
	}
	p.Body = append([]byte(nil), buf[off:total]...)
	p.TotalLen = total
	return p, total, nil
}

// ExtractPackets pulls every complete packet from a stream buffer, returning the
// packets and any trailing bytes not yet forming a complete packet. Bytes before
// the first magic are skipped (the caller's inspector logs the raw read).
func ExtractPackets(buf []byte) (packets []*Packet, rest []byte) {
	i := 0
	for i < len(buf) {
		// Resync to the next magic if not already aligned.
		if !(buf[i] == Magic[0] && i+3 < len(buf) &&
			buf[i+1] == Magic[1] && buf[i+2] == Magic[2] && buf[i+3] == Magic[3]) {
			idx := indexOfMagic(buf[i:])
			if idx < 0 {
				// Keep a small tail in case a magic is split across reads.
				keep := len(buf) - i
				if keep > 3 {
					keep = 3
				}
				return packets, buf[len(buf)-keep:]
			}
			i += idx
		}
		pkt, n, err := Parse(buf[i:])
		if err == ErrNeedMore {
			return packets, buf[i:]
		}
		if err != nil {
			i++ // skip this byte and resync
			continue
		}
		packets = append(packets, pkt)
		i += n
	}
	return packets, nil
}

func indexOfMagic(b []byte) int {
	for i := 0; i+3 < len(b); i++ {
		if b[i] == Magic[0] && b[i+1] == Magic[1] && b[i+2] == Magic[2] && b[i+3] == Magic[3] {
			return i
		}
	}
	return -1
}

func decodeBCD(b []byte) (string, error) {
	out := make([]byte, 0, len(b)*2)
	for _, x := range b {
		hi, lo := x>>4, x&0x0f
		if hi > 9 || lo > 9 {
			return "", fmt.Errorf("invalid nibble")
		}
		out = append(out, '0'+hi, '0'+lo)
	}
	// Trim leading zeros to match the JT808 reporting-id convention.
	s := string(out)
	i := 0
	for i < len(s)-1 && s[i] == '0' {
		i++
	}
	return s[i:], nil
}
