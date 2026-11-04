package jt1078

import (
	"bytes"
	"testing"
)

func TestVideoPacketRoundTrip(t *testing.T) {
	in := &Packet{
		PayloadType: 98, Mark: true, Sequence: 7, SIM: "100000000001", Channel: 1,
		DataType: DataVideoIFrame, SubPackage: SubAtomic, Timestamp: 1699000000000,
		LastIFrame: 40, LastFrame: 40, Body: []byte{0x00, 0x00, 0x00, 0x01, 0x67, 0x42},
	}
	raw := Build(in)
	got, n, err := Parse(raw)
	if err != nil {
		t.Fatalf("parse: %v", err)
	}
	if n != len(raw) {
		t.Fatalf("consumed %d want %d", n, len(raw))
	}
	if got.SIM != "100000000001" || got.Channel != 1 || got.DataType != DataVideoIFrame {
		t.Fatalf("header mismatch: %+v", got)
	}
	if got.PayloadType != 98 || !got.Mark || got.Sequence != 7 || got.Timestamp != 1699000000000 {
		t.Fatalf("fields mismatch: %+v", got)
	}
	if !bytes.Equal(got.Body, in.Body) {
		t.Fatalf("body mismatch: % x", got.Body)
	}
	if got.HeaderLen != 30 {
		t.Fatalf("video header len = %d want 30", got.HeaderLen)
	}
}

func TestAudioAndTransparentHeaderLengths(t *testing.T) {
	audio := Build(&Packet{SIM: "1", Channel: 1, DataType: DataAudio, Body: []byte{1, 2, 3}})
	a, _, err := Parse(audio)
	if err != nil || a.HeaderLen != 26 {
		t.Fatalf("audio header len = %v (%v)", a, err)
	}
	trans := Build(&Packet{SIM: "1", Channel: 1, DataType: DataTransparent, Body: []byte{9}})
	tr, _, err := Parse(trans)
	if err != nil || tr.HeaderLen != 18 {
		t.Fatalf("transparent header len = %v (%v)", tr, err)
	}
}

func TestParseNeedMore(t *testing.T) {
	full := Build(&Packet{SIM: "1", Channel: 1, DataType: DataVideoIFrame, Body: []byte{1, 2, 3, 4}})
	if _, _, err := Parse(full[:20]); err != ErrNeedMore {
		t.Fatalf("expected ErrNeedMore, got %v", err)
	}
}

func TestExtractPacketsMultipleAndPartial(t *testing.T) {
	p1 := Build(&Packet{SIM: "1", Channel: 1, DataType: DataVideoIFrame, Sequence: 1, Body: []byte{1, 2}})
	p2 := Build(&Packet{SIM: "1", Channel: 1, DataType: DataVideoPFrame, Sequence: 2, Body: []byte{3, 4, 5}})
	stream := append(append([]byte{}, p1...), p2...)
	pkts, rest := ExtractPackets(stream)
	if len(pkts) != 2 {
		t.Fatalf("want 2 packets, got %d", len(pkts))
	}
	if len(rest) != 0 {
		t.Fatalf("unexpected rest: % x", rest)
	}
	// Split the second packet across reads.
	half := len(p1) + 5
	pkts, rest = ExtractPackets(stream[:half])
	if len(pkts) != 1 {
		t.Fatalf("want 1 packet before completion, got %d", len(pkts))
	}
	pkts2, _ := ExtractPackets(append(rest, stream[half:]...))
	if len(pkts2) != 1 {
		t.Fatalf("want 1 packet after completion, got %d", len(pkts2))
	}
}

func TestExtractResyncsOnJunk(t *testing.T) {
	p1 := Build(&Packet{SIM: "1", Channel: 1, DataType: DataVideoIFrame, Body: []byte{1, 2}})
	stream := append([]byte{0xaa, 0xbb, 0xcc}, p1...)
	pkts, _ := ExtractPackets(stream)
	if len(pkts) != 1 {
		t.Fatalf("want 1 packet after junk, got %d", len(pkts))
	}
}
