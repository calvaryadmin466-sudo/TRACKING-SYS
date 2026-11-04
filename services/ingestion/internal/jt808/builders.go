package jt808

import (
	"encoding/binary"
	"time"
)

// buildFrame assembles a complete, flag-wrapped, escaped JT/T 808 frame from a
// message ID, phone BCD, version info, serial number and a raw body. Encryption
// and fragmentation are never set by this server's builders.
func buildFrame(msgID uint16, phoneBCD []byte, hasVersion bool, version byte, serial uint16, body []byte) []byte {
	attrs := uint16(len(body) & 0x03ff)
	if hasVersion {
		attrs |= 1 << 14
	}
	hdr := make([]byte, 0, 16)
	hdr = binary.BigEndian.AppendUint16(hdr, msgID)
	hdr = binary.BigEndian.AppendUint16(hdr, attrs)
	if hasVersion {
		hdr = append(hdr, version)
	}
	hdr = append(hdr, phoneBCD...)
	hdr = binary.BigEndian.AppendUint16(hdr, serial)

	payload := append(hdr, body...)
	chk := Checksum(payload)
	full := append(payload, chk)
	return append(append([]byte{Flag}, Escape(full)...), Flag)
}

// BuildPlatformGeneralResp builds a 0x8001 platform general response that
// acknowledges a terminal message. ackSerial/ackMsgID identify the message being
// acknowledged; the response is addressed back to the terminal using the same
// phone/version shape it used.
func BuildPlatformGeneralResp(reqHeader Header, platformSerial uint16, ackMsgID uint16, result byte) []byte {
	body := make([]byte, 5)
	binary.BigEndian.PutUint16(body[0:2], reqHeader.Serial)
	binary.BigEndian.PutUint16(body[2:4], ackMsgID)
	body[4] = result
	return buildFrame(MsgPlatformGeneralResp, reqHeader.PhoneBCD, reqHeader.HasVersion, reqHeader.Version, platformSerial, body)
}

// BuildRegisterResp builds a 0x8100 registration response. When result is
// RegResultSuccess the authCode is appended; otherwise it is omitted.
func BuildRegisterResp(reqHeader Header, platformSerial uint16, result byte, authCode string) []byte {
	body := make([]byte, 3, 3+len(authCode))
	binary.BigEndian.PutUint16(body[0:2], reqHeader.Serial)
	body[2] = result
	if result == RegResultSuccess {
		body = append(body, []byte(authCode)...)
	}
	return buildFrame(MsgRegisterResp, reqHeader.PhoneBCD, reqHeader.HasVersion, reqHeader.Version, platformSerial, body)
}

// BuildTextMessage builds a 0x8300 text message distribution packet to the terminal.
// flag is a bitmask of delivery flags:
//   bit 0: emergency
//   bit 2: terminal display (LCD)
//   bit 3: TTS voice broadcast
//   bit 4: advertisement display
//   bit 5: CAN fault / notification
// text is the message body string.
func BuildTextMessage(phoneBCD []byte, hasVersion bool, version byte, serial uint16, flag byte, text string) []byte {
	textBytes := []byte(text)
	body := make([]byte, 1+len(textBytes))
	body[0] = flag
	copy(body[1:], textBytes)
	return buildFrame(MsgTextMessage, phoneBCD, hasVersion, version, serial, body)
}

// --- Terminal-side builders, used by the labelled device simulator only. ---

// EncodePhone encodes a reporting ID into the BCD phone bytes for the chosen
// protocol version (10 bytes for 2019, 6 bytes for 2013).
func EncodePhone(id string, hasVersion bool) []byte {
	if hasVersion {
		return encodeBCD(id, 10)
	}
	return encodeBCD(id, 6)
}

// BuildRegister builds a 0x0100 registration message (simulator).
func BuildRegister(phoneBCD []byte, hasVersion bool, version byte, serial uint16, reg Registration) []byte {
	mfLen, modelLen, idLen := 5, 20, 7
	if hasVersion {
		mfLen, modelLen, idLen = 11, 30, 30
	}
	body := make([]byte, 0, 4+mfLen+modelLen+idLen+1+len(reg.Plate))
	body = binary.BigEndian.AppendUint16(body, reg.ProvinceID)
	body = binary.BigEndian.AppendUint16(body, reg.CityID)
	body = append(body, fixedField(reg.ManufacturerID, mfLen)...)
	body = append(body, fixedField(reg.TerminalModel, modelLen)...)
	body = append(body, fixedField(reg.TerminalID, idLen)...)
	body = append(body, reg.PlateColor)
	body = append(body, []byte(reg.Plate)...)
	return buildFrame(MsgTerminalRegister, phoneBCD, hasVersion, version, serial, body)
}

// BuildAuth builds a 0x0102 authentication message carrying an auth code (simulator).
func BuildAuth(phoneBCD []byte, hasVersion bool, version byte, serial uint16, authCode string) []byte {
	return buildFrame(MsgTerminalAuth, phoneBCD, hasVersion, version, serial, []byte(authCode))
}

// BuildHeartbeat builds a 0x0002 heartbeat message (simulator).
func BuildHeartbeat(phoneBCD []byte, hasVersion bool, version byte, serial uint16) []byte {
	return buildFrame(MsgTerminalHeartbeat, phoneBCD, hasVersion, version, serial, nil)
}

// BuildLocation builds a 0x0200 location report from a Location (simulator).
func BuildLocation(phoneBCD []byte, hasVersion bool, version byte, serial uint16, l Location) []byte {
	body := make([]byte, 28)
	binary.BigEndian.PutUint32(body[0:4], l.AlarmFlag)

	status := l.Status
	if l.ACC {
		status |= statusACC
	}
	if l.Positioned || l.Valid {
		status |= statusPositioned
	}
	lat := l.Latitude
	lon := l.Longitude
	if lat < 0 {
		status |= statusLatSouth
		lat = -lat
	}
	if lon < 0 {
		status |= statusLonWest
		lon = -lon
	}
	binary.BigEndian.PutUint32(body[4:8], status)
	binary.BigEndian.PutUint32(body[8:12], uint32(lat*1e6))
	binary.BigEndian.PutUint32(body[12:16], uint32(lon*1e6))
	binary.BigEndian.PutUint16(body[16:18], uint16(l.Altitude))
	binary.BigEndian.PutUint16(body[18:20], uint16(l.Speed*10))
	binary.BigEndian.PutUint16(body[20:22], uint16(l.Heading))
	copy(body[22:28], encodeBCDTime(l.DeviceTime))

	if l.Satellites > 0 {
		body = append(body, 0x31, 0x01, byte(l.Satellites))
	}
	return buildFrame(MsgLocationReport, phoneBCD, hasVersion, version, serial, body)
}

// fixedField right-pads (with NUL) or truncates s to exactly n bytes.
func fixedField(s string, n int) []byte {
	out := make([]byte, n)
	copy(out, s)
	return out
}

// encodeBCDTime encodes a time as 6 BCD bytes YYMMDDhhmmss.
func encodeBCDTime(t time.Time) []byte {
	if t.IsZero() {
		t = time.Now().UTC()
	}
	y := t.Year() % 100
	s := twoDigit(y) + twoDigit(int(t.Month())) + twoDigit(t.Day()) +
		twoDigit(t.Hour()) + twoDigit(t.Minute()) + twoDigit(t.Second())
	return encodeBCD(s, 6)
}

func twoDigit(n int) string {
	return string([]byte{byte('0' + n/10%10), byte('0' + n%10)})
}
