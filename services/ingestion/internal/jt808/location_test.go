package jt808

import (
	"math"
	"testing"
	"time"
)

func approx(a, b float64) bool { return math.Abs(a-b) < 1e-6 }

func TestLocationRoundTrip(t *testing.T) {
	phone := encodeBCD("100000000001", 6)
	when := time.Date(2026, 11, 3, 10, 20, 30, 0, time.UTC)
	in := Location{
		ACC: true, Positioned: true, Valid: true,
		Latitude: 22.572600, Longitude: 88.363900,
		Altitude: 15, Speed: 42.5, Heading: 90,
		DeviceTime: when, Satellites: 11,
		AlarmFlag: 0,
	}
	frame := BuildLocation(phone, false, 0, 1, in)
	m, err := DecodeFrame(frame[1 : len(frame)-1])
	if err != nil {
		t.Fatalf("decode: %v", err)
	}
	if m.Location == nil {
		t.Fatalf("not decoded as location: %s", m.Kind)
	}
	loc := m.Location
	if !approx(loc.Latitude, 22.5726) || !approx(loc.Longitude, 88.3639) {
		t.Fatalf("coords = %.6f,%.6f", loc.Latitude, loc.Longitude)
	}
	if !approx(loc.Speed, 42.5) {
		t.Fatalf("speed = %.2f", loc.Speed)
	}
	if loc.Heading != 90 || loc.Altitude != 15 {
		t.Fatalf("heading/altitude = %d/%d", loc.Heading, loc.Altitude)
	}
	if !loc.ACC || !loc.Positioned || !loc.Valid {
		t.Fatalf("status flags acc=%v pos=%v valid=%v", loc.ACC, loc.Positioned, loc.Valid)
	}
	if loc.Satellites != 11 {
		t.Fatalf("satellites = %d", loc.Satellites)
	}
	if !loc.DeviceTime.Equal(when) {
		t.Fatalf("device time = %v want %v", loc.DeviceTime, when)
	}
}

func TestLocationSouthWestSigns(t *testing.T) {
	phone := encodeBCD("100000000001", 6)
	in := Location{
		Positioned: true, Valid: true,
		Latitude: -33.8688, Longitude: -151.2093, // southern & western hemisphere
		DeviceTime: time.Date(2026, 1, 1, 0, 0, 0, 0, time.UTC),
	}
	frame := BuildLocation(phone, false, 0, 1, in)
	m, _ := DecodeFrame(frame[1 : len(frame)-1])
	if m.Location == nil {
		t.Fatal("no location")
	}
	if m.Location.Latitude >= 0 || m.Location.Longitude >= 0 {
		t.Fatalf("expected negative coords, got %.6f,%.6f", m.Location.Latitude, m.Location.Longitude)
	}
	if !approx(m.Location.Latitude, -33.8688) || !approx(m.Location.Longitude, -151.2093) {
		t.Fatalf("coords = %.6f,%.6f", m.Location.Latitude, m.Location.Longitude)
	}
}

func TestLocationNotPositionedIsInvalid(t *testing.T) {
	body := make([]byte, 28)
	// status = 0 (not positioned), coords zero.
	l, err := DecodeLocation(body)
	if err != nil {
		t.Fatalf("decode: %v", err)
	}
	if l.Valid {
		t.Fatal("a report with no fix and zero coords must be invalid")
	}
}

func TestLocationTooShort(t *testing.T) {
	if _, err := DecodeLocation(make([]byte, 10)); err == nil {
		t.Fatal("expected error for short location body")
	}
}
