package jt808

import "strings"

// Registration is a decoded 0x0100 terminal registration body. The field widths
// differ between JT/T 808-2013 and -2019; the version flag from the header
// selects the layout. Fields that cannot be parsed are left empty and the raw
// body is preserved on the decoded Message for inspection.
type Registration struct {
	ProvinceID     uint16
	CityID         uint16
	ManufacturerID string // trimmed ASCII
	TerminalModel  string // trimmed ASCII
	TerminalID     string // trimmed ASCII -- candidate hardware serial number
	PlateColor     byte
	Plate          string // license plate (best-effort ASCII; may be GBK on device)
}

// DecodeRegistration decodes a 0x0100 body. hasVersion selects the 2019 layout
// (11-byte manufacturer, 30-byte model, 30-byte terminal id) versus the 2013
// layout (5-byte manufacturer, 20-byte model, 7-byte terminal id).
func DecodeRegistration(body []byte, hasVersion bool) *Registration {
	r := &Registration{}
	if len(body) < 4 {
		return r
	}
	r.ProvinceID = be16(body[0:2])
	r.CityID = be16(body[2:4])
	off := 4

	mfLen, modelLen, idLen := 5, 20, 7
	if hasVersion {
		mfLen, modelLen, idLen = 11, 30, 30
	}

	take := func(n int) []byte {
		if off+n > len(body) {
			n = len(body) - off
		}
		if n < 0 {
			n = 0
		}
		s := body[off : off+n]
		off += n
		return s
	}
	r.ManufacturerID = trimField(take(mfLen))
	r.TerminalModel = trimField(take(modelLen))
	r.TerminalID = trimField(take(idLen))
	if off < len(body) {
		r.PlateColor = body[off]
		off++
	}
	if off < len(body) {
		r.Plate = trimField(body[off:])
	}
	return r
}

// trimField trims NUL padding and surrounding whitespace from a fixed-width
// ASCII field.
func trimField(b []byte) string {
	return strings.TrimSpace(strings.Trim(string(b), "\x00"))
}
