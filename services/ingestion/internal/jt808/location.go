package jt808

import (
	"fmt"
	"time"
)

// Status bit masks for the 0x0200 location report status DWORD.
const (
	statusACC        uint32 = 1 << 0 // ignition / ACC on
	statusPositioned uint32 = 1 << 1 // position is fixed
	statusLatSouth   uint32 = 1 << 2 // latitude is south
	statusLonWest    uint32 = 1 << 3 // longitude is west
)

// Extra holds one additional-information item (TLV) from a location report.
type Extra struct {
	ID    byte
	Value []byte
}

// Location is a decoded 0x0200 location report.
type Location struct {
	AlarmFlag uint32
	Status    uint32

	Latitude  float64 // decimal degrees, signed (south negative)
	Longitude float64 // decimal degrees, signed (west negative)
	Altitude  int     // metres
	Speed     float64 // km/h
	Heading   int     // degrees, 0-359

	// DeviceTime is the terminal's reported wall-clock time (BCD YYMMDDhhmmss),
	// expressed in UTC location but NOT timezone-converted: it is the device's
	// local clock as reported. The server also records its own reception time.
	DeviceTime time.Time

	ACC        bool
	Positioned bool

	// Known decoded extras (0 when absent).
	MileageKM      float64 // additional item 0x01, 1/10 km -> km
	Satellites     int     // additional item 0x31, GNSS satellite count
	SignalStrength int     // additional item 0x30, wireless signal strength

	Extras []Extra // every additional item, raw, for diagnostics/forward-compat

	// Valid is true when the report claims a positioning fix and the coordinates
	// fall within the geographic range. Invalid reports are still stored, but are
	// kept distinct from fresh/valid positions.
	Valid bool
}

// DecodeLocation decodes the body of a 0x0200 location report.
func DecodeLocation(body []byte) (*Location, error) {
	if len(body) < 28 {
		return nil, fmt.Errorf("jt808: location body too short: %d bytes", len(body))
	}
	l := &Location{}
	l.AlarmFlag = be32(body[0:4])
	l.Status = be32(body[4:8])

	latRaw := be32(body[8:12])
	lonRaw := be32(body[12:16])
	l.Latitude = float64(latRaw) / 1e6
	l.Longitude = float64(lonRaw) / 1e6
	l.Altitude = int(be16(body[16:18]))
	l.Speed = float64(be16(body[18:20])) / 10.0
	l.Heading = int(be16(body[20:22]))

	l.ACC = l.Status&statusACC != 0
	l.Positioned = l.Status&statusPositioned != 0
	if l.Status&statusLatSouth != 0 {
		l.Latitude = -l.Latitude
	}
	if l.Status&statusLonWest != 0 {
		l.Longitude = -l.Longitude
	}

	if t, err := decodeBCDTime(body[22:28]); err == nil {
		l.DeviceTime = t
	}

	l.Extras = parseExtras(body[28:])
	for _, e := range l.Extras {
		switch e.ID {
		case 0x01:
			if len(e.Value) == 4 {
				l.MileageKM = float64(be32(e.Value)) / 10.0
			}
		case 0x30:
			if len(e.Value) == 1 {
				l.SignalStrength = int(e.Value[0])
			}
		case 0x31:
			if len(e.Value) == 1 {
				l.Satellites = int(e.Value[0])
			}
		}
	}

	l.Valid = l.Positioned &&
		l.Latitude >= -90 && l.Latitude <= 90 &&
		l.Longitude >= -180 && l.Longitude <= 180 &&
		!(latRaw == 0 && lonRaw == 0)
	return l, nil
}

// parseExtras walks the additional-information TLV items. Each item is
// id(1) + length(1) + value(length). Malformed tails are stopped on, not guessed.
func parseExtras(b []byte) []Extra {
	var out []Extra
	i := 0
	for i+2 <= len(b) {
		id := b[i]
		ln := int(b[i+1])
		if i+2+ln > len(b) {
			break
		}
		val := append([]byte(nil), b[i+2:i+2+ln]...)
		out = append(out, Extra{ID: id, Value: val})
		i += 2 + ln
	}
	return out
}

// decodeBCDTime decodes a 6-byte BCD YYMMDDhhmmss timestamp. The year is taken
// as 2000+YY. The time is returned with a UTC location but represents the
// device's reported wall-clock reading (timezone depends on device config).
func decodeBCDTime(b []byte) (time.Time, error) {
	s, err := decodeBCD(b)
	if err != nil || len(s) != 12 {
		return time.Time{}, fmt.Errorf("jt808: bad BCD time")
	}
	atoi := func(x string) int {
		n := 0
		for i := 0; i < len(x); i++ {
			n = n*10 + int(x[i]-'0')
		}
		return n
	}
	year := 2000 + atoi(s[0:2])
	mon := atoi(s[2:4])
	day := atoi(s[4:6])
	hour := atoi(s[6:8])
	min := atoi(s[8:10])
	sec := atoi(s[10:12])
	if mon < 1 || mon > 12 || day < 1 || day > 31 || hour > 23 || min > 59 || sec > 59 {
		return time.Time{}, fmt.Errorf("jt808: out-of-range BCD time %q", s)
	}
	return time.Date(year, time.Month(mon), day, hour, min, sec, 0, time.UTC), nil
}
