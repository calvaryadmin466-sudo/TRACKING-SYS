package jt808

import "testing"

func TestDecodeHeartbeatKnownVector(t *testing.T) {
	raw := []byte{0x00, 0x02, 0x00, 0x00, 0x01, 0x39, 0x12, 0x34, 0x47, 0x94, 0x00, 0x01, 0xce}
	m, err := Decode(raw)
	if err != nil {
		t.Fatalf("decode: %v", err)
	}
	if !m.ChecksumOK {
		t.Fatal("checksum should be OK")
	}
	if m.Header.MsgID != MsgTerminalHeartbeat {
		t.Fatalf("msg id = 0x%04x", m.Header.MsgID)
	}
	if m.Header.Phone != "013912344794" {
		t.Fatalf("phone = %q", m.Header.Phone)
	}
	if m.Header.ID != "13912344794" {
		t.Fatalf("reporting id = %q", m.Header.ID)
	}
	if m.Header.Serial != 1 {
		t.Fatalf("serial = %d", m.Header.Serial)
	}
	if !m.Recognised {
		t.Fatal("heartbeat should be recognised")
	}
}

func TestDecodeChecksumMismatchReported(t *testing.T) {
	raw := []byte{0x00, 0x02, 0x00, 0x00, 0x01, 0x39, 0x12, 0x34, 0x47, 0x94, 0x00, 0x01, 0xff}
	m, err := Decode(raw)
	if err != nil {
		t.Fatalf("decode: %v", err)
	}
	if m.ChecksumOK {
		t.Fatal("checksum should NOT be OK")
	}
}

func TestDecodeUnknownMessageNotDiscarded(t *testing.T) {
	// A well-framed message with an unsupported ID (0x0900).
	frame := buildFrame(0x0900, encodeBCD("13912344794", 6), false, 0, 7, []byte{0xde, 0xad})
	m, err := DecodeFrame(frame[1 : len(frame)-1]) // strip flags
	if err != nil {
		t.Fatalf("decode: %v", err)
	}
	if m.Recognised {
		t.Fatal("0x0900 must be reported as not recognised")
	}
	if m.Kind != "unknown_0x0900" {
		t.Fatalf("kind = %q", m.Kind)
	}
	if !m.ChecksumOK {
		t.Fatal("checksum should still validate for an unknown message")
	}
}

func TestDecodeRegisterRoundTrip(t *testing.T) {
	phone := encodeBCD("100000000001", 6)
	reg := Registration{
		ManufacturerID: "ACME", TerminalModel: "XV-900-8",
		TerminalID: "SN12345", PlateColor: 1, Plate: "WB-01-AB-1234",
	}
	frame := BuildRegister(phone, false, 0, 3, reg)
	m, err := DecodeFrame(frame[1 : len(frame)-1])
	if err != nil {
		t.Fatalf("decode: %v", err)
	}
	if m.Header.MsgID != MsgTerminalRegister || m.Registration == nil {
		t.Fatalf("not a registration: %s", m.Kind)
	}
	if m.Registration.TerminalID != "SN12345" {
		t.Fatalf("terminal id = %q", m.Registration.TerminalID)
	}
	if m.Registration.Plate != "WB-01-AB-1234" {
		t.Fatalf("plate = %q", m.Registration.Plate)
	}
}
