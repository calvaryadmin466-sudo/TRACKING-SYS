// Package mediagw implements the JT/T 1078 media gateway: a TCP server that
// accepts device video-stream connections, reassembles 1078 packets, and reports
// per-(SIM, channel) stream statistics.
//
// It captures and measures GENUINE device streams only. It never fabricates
// video. Decoding/transcoding 1078 payloads into a browser-playable stream
// (fMP4/WebRTC/HLS) is intentionally not done here: that pipeline must be built
// and validated against a physical XV-900-8 that actually streams H.264/H.265.
package mediagw

import (
	"context"
	"fmt"
	"log/slog"
	"net"
	"sort"
	"sync"
	"sync/atomic"
	"time"

	"tracking/ingestion/internal/inspector"
	"tracking/ingestion/internal/jt1078"
)

// StreamStat is a snapshot of one live device video stream.
type StreamStat struct {
	Key         string    `json:"key"`
	SIM         string    `json:"sim"`
	Channel     int       `json:"channel"`
	RemoteAddr  string    `json:"remote_addr"`
	ConnID      string    `json:"conn_id"`
	PayloadType int       `json:"payload_type"`
	StartedAt   time.Time `json:"started_at"`
	LastAt      time.Time `json:"last_at"`
	Packets     int64     `json:"packets"`
	Bytes       int64     `json:"bytes"`
	VideoFrames int64     `json:"video_frames"`
	KeyFrames   int64     `json:"key_frames"`
	AudioFrames int64     `json:"audio_frames"`
}

type streamState struct {
	mu   sync.Mutex
	stat StreamStat
}

// Gateway is the JT/T 1078 media gateway.
type Gateway struct {
	addr    string
	log     *slog.Logger
	ln      net.Listener
	wg      sync.WaitGroup
	closed  atomic.Bool
	connSeq atomic.Uint64

	mu      sync.RWMutex
	streams map[string]*streamState
}

// New creates a media gateway bound to addr.
func New(addr string, log *slog.Logger) *Gateway {
	return &Gateway{addr: addr, log: log, streams: make(map[string]*streamState)}
}

// Addr returns the bound listener address (valid after Listen).
func (g *Gateway) Addr() net.Addr {
	if g.ln == nil {
		return nil
	}
	return g.ln.Addr()
}

// Listen binds the TCP port without serving.
func (g *Gateway) Listen() error {
	ln, err := net.Listen("tcp", g.addr)
	if err != nil {
		return fmt.Errorf("mediagw: listen %s: %w", g.addr, err)
	}
	g.ln = ln
	g.log.Info("jt1078 media gateway listening", "addr", ln.Addr().String())
	return nil
}

// Serve accepts stream connections until the context is cancelled.
func (g *Gateway) Serve(ctx context.Context) error {
	if g.ln == nil {
		if err := g.Listen(); err != nil {
			return err
		}
	}
	go func() { <-ctx.Done(); g.Close() }()
	for {
		conn, err := g.ln.Accept()
		if err != nil {
			if g.closed.Load() {
				break
			}
			g.log.Error("mediagw accept error", "err", err)
			continue
		}
		g.wg.Add(1)
		go func() { defer g.wg.Done(); g.handleConn(conn) }()
	}
	g.wg.Wait()
	return nil
}

// Close stops accepting new stream connections.
func (g *Gateway) Close() {
	if g.closed.Swap(true) {
		return
	}
	if g.ln != nil {
		_ = g.ln.Close()
	}
}

func (g *Gateway) handleConn(conn net.Conn) {
	defer conn.Close()
	remote := conn.RemoteAddr().String()
	connID := fmt.Sprintf("v%d", g.connSeq.Add(1))
	g.log.Info("media stream connected", "conn", connID, "remote", remote)

	var buf []byte
	readBuf := make([]byte, 32*1024)
	logged := 0
	for {
		_ = conn.SetReadDeadline(time.Now().Add(60 * time.Second))
		n, err := conn.Read(readBuf)
		if n > 0 {
			chunk := readBuf[:n]
			if logged < 2 { // sample the first reads for diagnostics
				g.log.Debug("media raw rx", "conn", connID, "len", n,
					"hex", inspector.Hex(chunk[:min(n, 48)]))
				logged++
			}
			buf = append(buf, chunk...)
			packets, rest := jt1078.ExtractPackets(buf)
			buf = rest
			for _, p := range packets {
				g.record(connID, remote, p)
			}
			if len(buf) > 4*1024*1024 { // guard runaway buffer
				g.log.Warn("media buffer overflow, resetting", "conn", connID)
				buf = nil
			}
		}
		if err != nil {
			g.log.Info("media stream disconnected", "conn", connID, "remote", remote, "err", err)
			return
		}
	}
}

func (g *Gateway) record(connID, remote string, p *jt1078.Packet) {
	key := fmt.Sprintf("%s:%d", p.SIM, p.Channel)
	g.mu.Lock()
	st := g.streams[key]
	if st == nil {
		st = &streamState{stat: StreamStat{
			Key: key, SIM: p.SIM, Channel: int(p.Channel), RemoteAddr: remote,
			ConnID: connID, PayloadType: int(p.PayloadType), StartedAt: time.Now().UTC(),
		}}
		g.streams[key] = st
		g.log.Info("media stream started", "sim", p.SIM, "channel", p.Channel, "pt", p.PayloadType)
	}
	g.mu.Unlock()

	st.mu.Lock()
	s := &st.stat
	s.LastAt = time.Now().UTC()
	s.Packets++
	s.Bytes += int64(p.TotalLen)
	switch {
	case p.DataType == jt1078.DataVideoIFrame:
		s.VideoFrames++
		s.KeyFrames++
	case p.IsVideo():
		s.VideoFrames++
	case p.DataType == jt1078.DataAudio:
		s.AudioFrames++
	}
	st.mu.Unlock()
}

// min removed: Go's builtin min is used instead.

// Stats returns a snapshot of all known streams, newest activity first.
func (g *Gateway) Stats() []StreamStat {
	g.mu.RLock()
	defer g.mu.RUnlock()
	out := make([]StreamStat, 0, len(g.streams))
	for _, st := range g.streams {
		st.mu.Lock()
		out = append(out, st.stat)
		st.mu.Unlock()
	}
	sort.Slice(out, func(i, j int) bool { return out[i].LastAt.After(out[j].LastAt) })
	return out
}
