package server

import (
	"context"
	"errors"
	"io"
	"net"
	"time"

	"tracking/ingestion/internal/inspector"
	"tracking/ingestion/internal/jt808"
	"tracking/ingestion/internal/store"
)

// handleConn runs the read loop for a single device connection: it reads bytes,
// records a raw capture of every chunk, reassembles complete JT/T 808 frames
// (handling partial and concatenated frames) and dispatches each frame to the
// message handler. Unknown bytes are logged and stored, never silently dropped.
func (s *Server) handleConn(ctx context.Context, conn net.Conn) {
	remote := conn.RemoteAddr().String()
	connID := s.newConnID()
	sess := &Session{ConnID: connID, RemoteAddr: remote, connectedAt: time.Now().UTC()}
	sess.setConn(conn)
	s.registry.add(sess)

	s.log.Info("device connected", "conn", connID, "remote", remote)
	_ = s.store.SaveConnectionEvent(ctx, store.ConnectionEvent{
		ConnID: connID, RemoteAddr: remote, Event: "connected", At: time.Now().UTC(),
	})

	disconnectReason := "closed"
	defer func() {
		conn.Close()
		s.registry.remove(sess)
		s.log.Info("device disconnected", "conn", connID, "remote", remote,
			"reason", disconnectReason, "reporting_id", sess.ReportingID(),
			"bytes_in", sess.BytesIn.Load(), "packets", sess.PacketsIn.Load(),
			"decoded", sess.Decoded.Load(), "unknown", sess.Unknown.Load())
		_ = s.store.SaveConnectionEvent(ctx, store.ConnectionEvent{
			ConnID: connID, RemoteAddr: remote, ReportingID: sess.ReportingID(),
			Event: "disconnected", Reason: disconnectReason, At: time.Now().UTC(),
		})
	}()

	var buf []byte
	readBuf := make([]byte, 4096)
	for {
		if s.cfg.ReadTimeout > 0 {
			_ = conn.SetReadDeadline(time.Now().Add(s.cfg.ReadTimeout))
		}
		n, err := conn.Read(readBuf)
		if n > 0 {
			sess.BytesIn.Add(int64(n))
			chunk := readBuf[:n]

			capRec := inspector.Capture(connID, remote, chunk)
			if s.cfg.LogRawPackets {
				s.log.Debug("raw rx", "conn", connID, "len", n,
					"flags", len(capRec.FlagOffsets), "hex", capRec.Hex)
			}

			buf = append(buf, chunk...)
			frames, rest := jt808.ExtractFrames(buf)
			buf = rest

			// Guard against a peer that never sends a frame delimiter.
			if len(buf) > s.cfg.MaxFrameBytes {
				s.log.Warn("reassembly buffer exceeded; dropping and recording unidentified bytes",
					"conn", connID, "buffered", len(buf))
				s.recordUnidentified(ctx, sess, buf, "reassembly buffer overflow: no frame delimiter")
				buf = nil
			}

			for _, fr := range frames {
				sess.PacketsIn.Add(1)
				s.handleFrame(ctx, conn, sess, fr)
			}
		}
		if err != nil {
			switch {
			case errors.Is(err, io.EOF):
				disconnectReason = "eof"
			case errors.Is(err, net.ErrClosed):
				disconnectReason = "server closed"
			default:
				var ne net.Error
				if errors.As(err, &ne) && ne.Timeout() {
					disconnectReason = "read timeout (no heartbeat)"
				} else {
					disconnectReason = "read error: " + err.Error()
				}
			}
			return
		}
	}
}

// recordUnidentified stores a chunk of bytes that could not be framed/decoded,
// so no traffic is ever lost. It never crashes the connection.
func (s *Server) recordUnidentified(ctx context.Context, sess *Session, b []byte, note string) {
	_ = s.store.SaveRawPacket(ctx, store.RawPacket{
		ConnID:      sess.ConnID,
		RemoteAddr:  sess.RemoteAddr,
		ReportingID: sess.ReportingID(),
		ReceivedAt:  time.Now().UTC(),
		Length:      len(b),
		Hex:         inspector.Hex(b),
		ASCII:       inspector.ASCII(b),
		MessageName: "unidentified",
		Decoded:     false,
		Note:        note,
	})
	sess.Unknown.Add(1)
}
