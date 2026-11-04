package jt808

// Header is a decoded JT/T 808 message header. The layout depends on the
// version flag (bit 14 of the body attributes): when set, the message follows
// JT/T 808-2019 (a 1-byte protocol version follows the attributes and the phone
// field is 10 BCD bytes); when clear it follows JT/T 808-2013 (no version byte,
// 6 BCD phone bytes).
type Header struct {
	MsgID      uint16
	Attributes uint16

	BodyLength int  // bits 0-9 of attributes
	Encryption byte // bits 10-12
	Fragmented bool // bit 13
	HasVersion bool // bit 14 (JT/T 808-2019 header)
	Version    byte // protocol version number, valid only when HasVersion

	PhoneBCD []byte // raw BCD phone bytes (6 or 10)
	Phone    string // decoded digits, leading zeros preserved
	ID       string // canonical reporting ID (decoded digits, leading zeros trimmed)

	Serial uint16 // message serial number

	TotalPackets uint16 // fragmentation total, valid only when Fragmented
	PacketSeq    uint16 // fragmentation sequence, valid only when Fragmented

	Length int // number of bytes consumed by this header
}

// ParseHeader decodes a JT/T 808 header from the start of an unescaped message
// (header + body + check code). It returns the decoded header; the caller slices
// the body using Header.Length and Header.BodyLength.
func ParseHeader(b []byte) (Header, error) {
	var h Header
	if len(b) < 4 {
		return h, ErrShortFrame
	}
	h.MsgID = be16(b[0:2])
	h.Attributes = be16(b[2:4])
	h.BodyLength = int(h.Attributes & 0x03ff)
	h.Encryption = byte((h.Attributes >> 10) & 0x07)
	h.Fragmented = (h.Attributes>>13)&0x01 == 1
	h.HasVersion = (h.Attributes>>14)&0x01 == 1

	off := 4
	phoneLen := 6
	if h.HasVersion {
		if len(b) < off+1 {
			return h, ErrShortFrame
		}
		h.Version = b[off]
		off++
		phoneLen = 10
	}
	if len(b) < off+phoneLen+2 {
		return h, ErrShortFrame
	}
	h.PhoneBCD = append([]byte(nil), b[off:off+phoneLen]...)
	off += phoneLen
	if phone, err := decodeBCD(h.PhoneBCD); err == nil {
		h.Phone = phone
		h.ID = normalizePhone(phone)
	}
	h.Serial = be16(b[off : off+2])
	off += 2

	if h.Fragmented {
		if len(b) < off+4 {
			return h, ErrShortFrame
		}
		h.TotalPackets = be16(b[off : off+2])
		h.PacketSeq = be16(b[off+2 : off+4])
		off += 4
	}
	h.Length = off
	return h, nil
}
