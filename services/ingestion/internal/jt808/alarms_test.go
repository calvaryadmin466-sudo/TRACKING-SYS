package jt808

import (
	"strings"
	"testing"
)

func TestAlarmNames(t *testing.T) {
	if AlarmNames(0) != nil {
		t.Fatal("zero flag should yield no alarms")
	}
	// bit0 (SOS) + bit1 (overspeed) + bit7 (undervoltage)
	flag := uint32(1<<0 | 1<<1 | 1<<7)
	got := strings.Join(AlarmNames(flag), ",")
	want := "emergency_sos,overspeed,main_power_undervoltage"
	if got != want {
		t.Fatalf("got %q want %q", got, want)
	}
}

func TestAlarmNamesUnknownBit(t *testing.T) {
	names := AlarmNames(1 << 17) // undocumented bit
	if len(names) != 1 || names[0] != "alarm_bit17" {
		t.Fatalf("unknown bit = %v", names)
	}
}
