package server_test

import (
	"bufio"
	"context"
	"io"
	"log/slog"
	"net"
	"testing"
	"time"

	"tracking/ingestion/internal/config"
	"tracking/ingestion/internal/jt808"
	"tracking/ingestion/internal/server"
	"tracking/ingestion/internal/store"
)

func startTestServer(t *testing.T) (*server.Server, *store.MemoryStore, string) {
	t.Helper()
	st := store.NewMemoryStore()
	cfg := config.Config{
		JT808Addr:     "127.0.0.1:0",
		ReadTimeout:   2 * time.Second,
		MaxFrameBytes: 64 * 1024,
		LogRawPackets: false,
	}
	log := slog.New(slog.NewTextHandler(io.Discard, nil))
	srv := server.New(cfg, st, log)
	if err := srv.Listen(); err != nil {
		t.Fatalf("listen: %v", err)
	}
	ctx, cancel := context.WithCancel(context.Background())
	t.Cleanup(cancel)
	go func() { _ = srv.Serve(ctx) }()
	return srv, st, srv.Addr().String()
}

func readFrame(t *testing.T, r *bufio.Reader) *jt808.Message {
	t.Helper()
	for {
		b, err := r.ReadByte()
		if err != nil {
			t.Fatalf("read flag: %v", err)
		}
		if b == jt808.Flag {
			break
		}
	}
	var body []byte
	for {
		b, err := r.ReadByte()
		if err != nil {
			t.Fatalf("read body: %v", err)
		}
		if b == jt808.Flag {
			if len(body) == 0 {
				continue
			}
			break
		}
		body = append(body, b)
	}
	m, err := jt808.DecodeFrame(body)
	if err != nil {
		t.Fatalf("decode reply: %v", err)
	}
	return m
}

func TestFullDeviceFlow(t *testing.T) {
	_, st, addr := startTestServer(t)

	conn, err := net.Dial("tcp", addr)
	if err != nil {
		t.Fatalf("dial: %v", err)
	}
	defer conn.Close()
	r := bufio.NewReader(conn)

	phone := jt808.EncodePhone("100000000099", false)

	// Register.
	// JT/T 808-2013 terminal-ID field is 7 bytes, so serials are <= 7 chars here.
	reg := jt808.Registration{ManufacturerID: "ACME", TerminalModel: "XV-900-8", TerminalID: "REAL001", PlateColor: 1, Plate: "WB-99-ZZ-0001"}
	if _, err := conn.Write(jt808.BuildRegister(phone, false, 0, 1, reg)); err != nil {
		t.Fatalf("write register: %v", err)
	}
	resp := readFrame(t, r)
	if resp.Header.MsgID != jt808.MsgRegisterResp {
		t.Fatalf("expected register resp, got %s", resp.Kind)
	}
	if len(resp.Body) < 3 || resp.Body[2] != jt808.RegResultSuccess {
		t.Fatalf("registration not successful: % x", resp.Body)
	}
	authCode := string(resp.Body[3:])
	if authCode == "" {
		t.Fatal("expected auth code")
	}

	// Verify device identity fields are stored separately.
	dev, ok, _ := st.GetDeviceByReportingID(context.Background(), "100000000099")
	if !ok {
		t.Fatal("device not registered in store")
	}
	if dev.ReportingID != "100000000099" {
		t.Fatalf("reporting id = %q", dev.ReportingID)
	}
	if dev.SerialNumber != "REAL001" {
		t.Fatalf("serial = %q (must be distinct from reporting id)", dev.SerialNumber)
	}
	if dev.SerialNumber == dev.ReportingID {
		t.Fatal("serial number and reporting id must never be equal")
	}

	// Authenticate.
	if _, err := conn.Write(jt808.BuildAuth(phone, false, 0, 2, authCode)); err != nil {
		t.Fatalf("write auth: %v", err)
	}
	if ack := readFrame(t, r); ack.Header.MsgID != jt808.MsgPlatformGeneralResp {
		t.Fatalf("expected auth ack, got %s", ack.Kind)
	}

	// Heartbeat.
	if _, err := conn.Write(jt808.BuildHeartbeat(phone, false, 0, 3)); err != nil {
		t.Fatalf("write heartbeat: %v", err)
	}
	readFrame(t, r)

	// Location.
	loc := jt808.Location{ACC: true, Positioned: true, Valid: true, Latitude: 22.5726, Longitude: 88.3639, Speed: 40, Heading: 45, DeviceTime: time.Now().UTC(), Satellites: 9}
	if _, err := conn.Write(jt808.BuildLocation(phone, false, 0, 4, loc)); err != nil {
		t.Fatalf("write location: %v", err)
	}
	if ack := readFrame(t, r); ack.Header.MsgID != jt808.MsgPlatformGeneralResp {
		t.Fatalf("expected location ack, got %s", ack.Kind)
	}

	if st.PositionCount() != 1 {
		t.Fatalf("expected 1 stored position, got %d", st.PositionCount())
	}
	p, _ := st.LastPosition()
	if p.ReportingID != "100000000099" || p.Latitude < 22.57 || p.Latitude > 22.58 {
		t.Fatalf("stored position wrong: %+v", p)
	}
	if p.DeviceID != dev.ID {
		t.Fatalf("position device id %d != device id %d", p.DeviceID, dev.ID)
	}
}

func TestUnknownFrameNotDiscarded(t *testing.T) {
	_, st, addr := startTestServer(t)
	conn, err := net.Dial("tcp", addr)
	if err != nil {
		t.Fatalf("dial: %v", err)
	}
	defer conn.Close()
	r := bufio.NewReader(conn)

	phone := jt808.EncodePhone("100000000077", false)
	// Build a well-framed but unsupported message id.
	frame := buildUnknownFrame(phone, 0x0999, []byte{0x01, 0x02, 0x03})
	if _, err := conn.Write(frame); err != nil {
		t.Fatalf("write: %v", err)
	}
	ack := readFrame(t, r)
	if ack.Header.MsgID != jt808.MsgPlatformGeneralResp {
		t.Fatalf("expected general resp ack, got %s", ack.Kind)
	}
	// The server must have stored the unknown packet, not discarded it.
	deadline := time.Now().Add(time.Second)
	for time.Now().Before(deadline) {
		if len(st.UnknownPackets()) > 0 {
			return
		}
		time.Sleep(10 * time.Millisecond)
	}
	t.Fatal("unknown packet was not stored")
}

func TestPartialFrameReassembly(t *testing.T) {
	_, st, addr := startTestServer(t)
	conn, err := net.Dial("tcp", addr)
	if err != nil {
		t.Fatalf("dial: %v", err)
	}
	defer conn.Close()
	r := bufio.NewReader(conn)

	phone := jt808.EncodePhone("100000000055", false)
	loc := jt808.Location{ACC: true, Positioned: true, Valid: true, Latitude: 1.23, Longitude: 4.56, DeviceTime: time.Now().UTC()}
	frame := jt808.BuildLocation(phone, false, 0, 1, loc)

	// Send the frame split across two writes.
	half := len(frame) / 2
	if _, err := conn.Write(frame[:half]); err != nil {
		t.Fatalf("write half1: %v", err)
	}
	time.Sleep(50 * time.Millisecond)
	if _, err := conn.Write(frame[half:]); err != nil {
		t.Fatalf("write half2: %v", err)
	}
	if ack := readFrame(t, r); ack.Header.MsgID != jt808.MsgPlatformGeneralResp {
		t.Fatalf("expected ack, got %s", ack.Kind)
	}
	if st.PositionCount() != 1 {
		t.Fatalf("expected 1 position from reassembled frame, got %d", st.PositionCount())
	}
}

// buildUnknownFrame constructs a valid JT/T 808 frame with an arbitrary message
// id for negative testing (mirrors jt808.buildFrame, which is unexported).
func buildUnknownFrame(phoneBCD []byte, msgID uint16, body []byte) []byte {
	attrs := uint16(len(body) & 0x03ff)
	hdr := []byte{byte(msgID >> 8), byte(msgID), byte(attrs >> 8), byte(attrs)}
	hdr = append(hdr, phoneBCD...)
	hdr = append(hdr, 0x00, 0x05) // serial
	payload := append(hdr, body...)
	var chk byte
	for _, b := range payload {
		chk ^= b
	}
	full := append(payload, chk)
	return append(append([]byte{jt808.Flag}, jt808.Escape(full)...), jt808.Flag)
}
