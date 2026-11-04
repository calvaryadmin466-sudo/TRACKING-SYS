package jt808

import "fmt"

// Message is a fully decoded JT/T 808 message.
type Message struct {
	Header     Header
	Body       []byte
	Checksum   byte
	ChecksumOK bool

	// Kind is the human message name (e.g. "location_report"). Recognised is
	// true only for message IDs this server understands and has type-decoded.
	Kind       string
	Recognised bool

	// Typed payloads; non-nil only for the matching Kind.
	Location     *Location
	Registration *Registration
}

// DecodeFrame decodes a single escaped frame (the bytes between the 0x7e flags,
// flags removed). It unescapes, verifies the check code, parses the header and
// decodes the body of recognised messages. A decode error is only returned when
// the bytes cannot form a header at all; a bad checksum or an unknown message ID
// is reported on the returned Message (ChecksumOK / Recognised) so the caller can
// log and acknowledge it rather than drop it.
func DecodeFrame(escaped []byte) (*Message, error) {
	raw, err := Unescape(escaped)
	if err != nil {
		return nil, err
	}
	return Decode(raw)
}

// Decode decodes an already-unescaped message (header + body + check code).
func Decode(raw []byte) (*Message, error) {
	if len(raw) < 5 {
		return nil, ErrShortFrame
	}
	m := &Message{}
	m.Checksum = raw[len(raw)-1]
	payload := raw[:len(raw)-1]
	m.ChecksumOK = Checksum(payload) == m.Checksum

	h, err := ParseHeader(payload)
	if err != nil {
		return nil, err
	}
	m.Header = h
	if h.Length > len(payload) {
		return nil, ErrShortFrame
	}
	m.Body = payload[h.Length:]

	m.Kind = MessageName(h.MsgID)
	switch h.MsgID {
	case MsgTerminalHeartbeat, MsgTerminalLogout, MsgTerminalAuth,
		MsgTerminalGeneralResp, MsgPlatformGeneralResp:
		m.Recognised = true
	case MsgTerminalRegister:
		m.Recognised = true
		m.Registration = DecodeRegistration(m.Body, h.HasVersion)
	case MsgLocationReport:
		m.Recognised = true
		if loc, lerr := DecodeLocation(m.Body); lerr == nil {
			m.Location = loc
		} else {
			// Body present but not decodable to the known layout: keep it as a
			// recognised-but-undecoded message rather than discarding it.
			m.Recognised = false
			m.Kind = fmt.Sprintf("%s(undecodable)", m.Kind)
		}
	default:
		m.Recognised = false
	}
	return m, nil
}
