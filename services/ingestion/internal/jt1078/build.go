package jt1078

import (
	"encoding/binary"
	"strings"
)

// Build encodes a Packet back into JT/T 1078 wire bytes. Used by the labelled
// video simulator and by tests; the gateway itself only parses.
func Build(p *Packet) []byte {
	out := make([]byte, 0, 32+len(p.Body))
	out = append(out, Magic...)
	out = append(out, 0x81) // V=2,P=0,X=0,CC=1 (typical)
	mpt := p.PayloadType & 0x7f
	if p.Mark {
		mpt |= 0x80
	}
	out = append(out, mpt)
	out = binary.BigEndian.AppendUint16(out, p.Sequence)
	out = append(out, encodeBCD(p.SIM, 6)...)
	out = append(out, p.Channel)
	out = append(out, (p.DataType<<4)|(p.SubPackage&0x0f))
	if p.DataType != DataTransparent {
		out = binary.BigEndian.AppendUint64(out, p.Timestamp)
	}
	if p.IsVideo() {
		out = binary.BigEndian.AppendUint16(out, p.LastIFrame)
		out = binary.BigEndian.AppendUint16(out, p.LastFrame)
	}
	out = binary.BigEndian.AppendUint16(out, uint16(len(p.Body)))
	out = append(out, p.Body...)
	return out
}

func encodeBCD(digits string, n int) []byte {
	want := n * 2
	if len(digits) < want {
		digits = strings.Repeat("0", want-len(digits)) + digits
	} else if len(digits) > want {
		digits = digits[len(digits)-want:]
	}
	out := make([]byte, n)
	for i := 0; i < n; i++ {
		out[i] = (digits[i*2]-'0')<<4 | (digits[i*2+1] - '0')
	}
	return out
}
