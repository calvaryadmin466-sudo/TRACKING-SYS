// Package inspector provides raw-packet inspection for the ingestion server:
// hex/ASCII dumps, frame-boundary detection and human-readable summaries of the
// bytes received from a device. It is deliberately decode-agnostic so that even
// completely unrecognised traffic can be captured and understood.
package inspector

import (
	"fmt"
	"strings"
	"time"
)

// FlagByte is the JT/T 808 frame delimiter; exposed so boundary detection does
// not depend on the jt808 package.
const FlagByte = 0x7e

// RawCapture is a structured record of one chunk of bytes received on a
// connection, suitable for logging and for persistence as a diagnostic record.
type RawCapture struct {
	ReceivedAt  time.Time
	ConnID      string
	RemoteAddr  string
	Length      int
	Hex         string // compact hex string, e.g. "7e0200..."
	HexDump     string // offset/hex/ascii dump, multi-line
	ASCII       string // printable ASCII rendering ('.' for non-printable)
	FlagOffsets []int  // indexes of 0x7e, i.e. candidate frame boundaries
}

// Capture builds a RawCapture for a received chunk.
func Capture(connID, remote string, b []byte) RawCapture {
	return RawCapture{
		ReceivedAt:  time.Now().UTC(),
		ConnID:      connID,
		RemoteAddr:  remote,
		Length:      len(b),
		Hex:         Hex(b),
		HexDump:     HexDump(b),
		ASCII:       ASCII(b),
		FlagOffsets: FlagOffsets(b),
	}
}

// Hex returns a continuous lowercase hex string for b.
func Hex(b []byte) string {
	var sb strings.Builder
	sb.Grow(len(b) * 2)
	const hexdigits = "0123456789abcdef"
	for _, c := range b {
		sb.WriteByte(hexdigits[c>>4])
		sb.WriteByte(hexdigits[c&0x0f])
	}
	return sb.String()
}

// ASCII renders b as printable ASCII, substituting '.' for non-printable bytes.
func ASCII(b []byte) string {
	out := make([]byte, len(b))
	for i, c := range b {
		if c >= 0x20 && c < 0x7f {
			out[i] = c
		} else {
			out[i] = '.'
		}
	}
	return string(out)
}

// FlagOffsets returns the indexes of every 0x7e byte: the candidate frame
// boundaries within a chunk.
func FlagOffsets(b []byte) []int {
	var out []int
	for i, c := range b {
		if c == FlagByte {
			out = append(out, i)
		}
	}
	return out
}

// HexDump produces a classic 16-byte-per-row hex+ascii dump.
func HexDump(b []byte) string {
	var sb strings.Builder
	for off := 0; off < len(b); off += 16 {
		end := off + 16
		if end > len(b) {
			end = len(b)
		}
		row := b[off:end]
		fmt.Fprintf(&sb, "%08x  ", off)
		for i := 0; i < 16; i++ {
			if i < len(row) {
				fmt.Fprintf(&sb, "%02x ", row[i])
			} else {
				sb.WriteString("   ")
			}
			if i == 7 {
				sb.WriteByte(' ')
			}
		}
		sb.WriteString(" |")
		sb.WriteString(ASCII(row))
		sb.WriteString("|\n")
	}
	return sb.String()
}
