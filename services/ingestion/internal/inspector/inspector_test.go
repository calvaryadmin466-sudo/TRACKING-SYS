package inspector

import (
	"strings"
	"testing"
)

func TestHexAndASCII(t *testing.T) {
	b := []byte{0x7e, 0x41, 0x00, 0x7e}
	if got := Hex(b); got != "7e41007e" {
		t.Fatalf("hex = %q", got)
	}
	// 0x7e ('~') and 0x41 ('A') are printable; 0x00 is not.
	if got := ASCII(b); got != "~A.~" {
		t.Fatalf("ascii = %q", got)
	}
}

func TestFlagOffsets(t *testing.T) {
	b := []byte{0x7e, 0x01, 0x02, 0x7e, 0x03, 0x7e}
	got := FlagOffsets(b)
	want := []int{0, 3, 5}
	if len(got) != len(want) {
		t.Fatalf("offsets = %v", got)
	}
	for i := range want {
		if got[i] != want[i] {
			t.Fatalf("offsets = %v want %v", got, want)
		}
	}
}

func TestHexDumpShape(t *testing.T) {
	dump := HexDump([]byte("hello world"))
	if !strings.Contains(dump, "|hello world|") {
		t.Fatalf("dump missing ascii gutter:\n%s", dump)
	}
	if !strings.HasPrefix(dump, "00000000  ") {
		t.Fatalf("dump missing offset:\n%s", dump)
	}
}

func TestCapture(t *testing.T) {
	c := Capture("c1", "1.2.3.4:5", []byte{0x7e, 0xaa, 0x7e})
	if c.Length != 3 || len(c.FlagOffsets) != 2 || c.ConnID != "c1" {
		t.Fatalf("capture = %+v", c)
	}
}
