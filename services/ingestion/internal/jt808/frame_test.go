package jt808

import (
	"bytes"
	"testing"
)

func TestEscapeUnescapeRoundTrip(t *testing.T) {
	cases := [][]byte{
		{},
		{0x00, 0x01, 0x02},
		{0x7e},
		{0x7d},
		{0x7e, 0x7d, 0x7e, 0x7d, 0x00, 0xff},
		{0x30, 0x7d, 0x08, 0x7e, 0x55},
	}
	for _, c := range cases {
		esc := Escape(c)
		// Escaped form must contain no bare flag byte.
		for i, b := range esc {
			if b == Flag {
				t.Fatalf("escaped output contains bare flag at %d: % x", i, esc)
			}
		}
		got, err := Unescape(esc)
		if err != nil {
			t.Fatalf("unescape(%x): %v", esc, err)
		}
		if !bytes.Equal(got, c) {
			t.Fatalf("round trip mismatch: want % x got % x", c, got)
		}
	}
}

func TestUnescapeBadSequence(t *testing.T) {
	if _, err := Unescape([]byte{0x7d, 0x09}); err == nil {
		t.Fatal("expected error for invalid escape sequence")
	}
	if _, err := Unescape([]byte{0x30, 0x7d}); err == nil {
		t.Fatal("expected error for dangling escape byte")
	}
}

func TestChecksumKnownVector(t *testing.T) {
	// Canonical JT/T 808-2013 heartbeat (msg 0x0002), phone 013912344794, serial 1.
	payload := []byte{0x00, 0x02, 0x00, 0x00, 0x01, 0x39, 0x12, 0x34, 0x47, 0x94, 0x00, 0x01}
	if got := Checksum(payload); got != 0xce {
		t.Fatalf("checksum = 0x%02x, want 0xce", got)
	}
}

func TestExtractFramesSingle(t *testing.T) {
	stream := []byte{0x7e, 0x11, 0x22, 0x33, 0x7e}
	frames, rest := ExtractFrames(stream)
	if len(frames) != 1 || !bytes.Equal(frames[0], []byte{0x11, 0x22, 0x33}) {
		t.Fatalf("frames=%v", frames)
	}
	// The trailing flag may be retained as rest; it must not contain a full frame.
	if len(rest) > 1 {
		t.Fatalf("unexpected rest: % x", rest)
	}
}

func TestExtractFramesMultiple(t *testing.T) {
	// Two frames, separate delimiters, plus leading junk.
	stream := []byte{0xaa, 0x7e, 0x01, 0x7e, 0x7e, 0x02, 0x03, 0x7e}
	frames, _ := ExtractFrames(stream)
	if len(frames) != 2 {
		t.Fatalf("want 2 frames, got %d: %v", len(frames), frames)
	}
	if !bytes.Equal(frames[0], []byte{0x01}) || !bytes.Equal(frames[1], []byte{0x02, 0x03}) {
		t.Fatalf("frames=%v", frames)
	}
}

func TestExtractFramesSharedDelimiter(t *testing.T) {
	stream := []byte{0x7e, 0x01, 0x7e, 0x02, 0x03, 0x7e}
	frames, _ := ExtractFrames(stream)
	if len(frames) != 2 {
		t.Fatalf("want 2 frames, got %d: %v", len(frames), frames)
	}
}

func TestExtractFramesPartial(t *testing.T) {
	// First read: opening flag + partial body, no closing flag.
	part1 := []byte{0x7e, 0x11, 0x22}
	frames, rest := ExtractFrames(part1)
	if len(frames) != 0 {
		t.Fatalf("expected no complete frames yet, got %v", frames)
	}
	// Second read completes the frame.
	part2 := append(rest, 0x33, 0x7e)
	frames, _ = ExtractFrames(part2)
	if len(frames) != 1 || !bytes.Equal(frames[0], []byte{0x11, 0x22, 0x33}) {
		t.Fatalf("frames=%v", frames)
	}
}
