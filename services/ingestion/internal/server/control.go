package server

import (
	"context"
	"encoding/json"
	"fmt"
	"net"
	"net/http"
	"time"

	"tracking/ingestion/internal/jt808"
	"tracking/ingestion/internal/mediagw"
)

// ControlServer exposes an internal, token-guarded HTTP API that lets the web
// API send JT/T 808 video-control commands to connected devices and read live
// media-gateway statistics. Bind it to localhost only.
type ControlServer struct {
	s     *Server
	gw    *mediagw.Gateway
	token string
	srv   *http.Server
}

// NewControlServer builds the control server.
func (s *Server) NewControlServer(gw *mediagw.Gateway) *ControlServer {
	return &ControlServer{s: s, gw: gw, token: s.cfg.ControlToken}
}

// Serve runs the control HTTP server until the context is cancelled.
func (cs *ControlServer) Serve(ctx context.Context) error {
	mux := http.NewServeMux()
	mux.HandleFunc("GET /internal/health", cs.wrap(cs.health))
	mux.HandleFunc("GET /internal/devices/{id}/status", cs.wrap(cs.status))
	mux.HandleFunc("POST /internal/devices/{id}/stream/start", cs.wrap(cs.streamStart))
	mux.HandleFunc("POST /internal/devices/{id}/stream/stop", cs.wrap(cs.streamStop))
	mux.HandleFunc("POST /internal/devices/{id}/playback", cs.wrap(cs.playback))
	mux.HandleFunc("POST /internal/devices/{id}/message", cs.wrap(cs.textMessage))
	mux.HandleFunc("GET /internal/video/streams", cs.wrap(cs.streams))

	cs.srv = &http.Server{Addr: cs.s.cfg.ControlAddr, Handler: mux}
	ln, err := net.Listen("tcp", cs.s.cfg.ControlAddr)
	if err != nil {
		return fmt.Errorf("control: listen %s: %w", cs.s.cfg.ControlAddr, err)
	}
	cs.s.log.Info("internal control API listening", "addr", ln.Addr().String())
	go func() { <-ctx.Done(); _ = cs.srv.Close() }()
	if err := cs.srv.Serve(ln); err != nil && err != http.ErrServerClosed {
		return err
	}
	return nil
}

func (cs *ControlServer) wrap(h http.HandlerFunc) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		if cs.token != "" && r.Header.Get("Authorization") != "Bearer "+cs.token {
			writeJSON(w, http.StatusUnauthorized, map[string]string{"error": "unauthorized"})
			return
		}
		h(w, r)
	}
}

func (cs *ControlServer) health(w http.ResponseWriter, _ *http.Request) {
	writeJSON(w, http.StatusOK, map[string]any{"status": "ok", "streams": len(cs.gw.Stats())})
}

func (cs *ControlServer) status(w http.ResponseWriter, r *http.Request) {
	id := r.PathValue("id")
	_, ok := cs.s.registry.GetByPhone(id)
	writeJSON(w, http.StatusOK, map[string]any{"reporting_id": id, "connected": ok})
}

type streamStartReq struct {
	Channel    int `json:"channel"`
	DataType   int `json:"data_type"`
	StreamType int `json:"stream_type"`
}

func (cs *ControlServer) streamStart(w http.ResponseWriter, r *http.Request) {
	id := r.PathValue("id")
	var req streamStartReq
	_ = json.NewDecoder(r.Body).Decode(&req)
	host, tcp, err := cs.s.sendRealtimeAV(id, byte(req.Channel), byte(req.DataType), byte(req.StreamType))
	if err != nil {
		writeJSON(w, http.StatusConflict, map[string]string{"error": err.Error()})
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{
		"ok": true, "reporting_id": id, "channel": req.Channel,
		"video_host": host, "video_tcp_port": tcp,
	})
}

type streamStopReq struct {
	Channel int `json:"channel"`
}

func (cs *ControlServer) streamStop(w http.ResponseWriter, r *http.Request) {
	id := r.PathValue("id")
	var req streamStopReq
	_ = json.NewDecoder(r.Body).Decode(&req)
	if err := cs.s.sendAVControl(id, byte(req.Channel), 0, 0, 0); err != nil {
		writeJSON(w, http.StatusConflict, map[string]string{"error": err.Error()})
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"ok": true})
}

type playbackReq struct {
	Channel   int    `json:"channel"`
	StartTime string `json:"start_time"` // "YYMMDDhhmmss"
	EndTime   string `json:"end_time"`
}

func (cs *ControlServer) playback(w http.ResponseWriter, r *http.Request) {
	id := r.PathValue("id")
	var req playbackReq
	_ = json.NewDecoder(r.Body).Decode(&req)
	host, tcp, err := cs.s.sendPlayback(id, byte(req.Channel), req.StartTime, req.EndTime)
	if err != nil {
		writeJSON(w, http.StatusConflict, map[string]string{"error": err.Error()})
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{
		"ok": true, "video_host": host, "video_tcp_port": tcp})
}

type messageReq struct {
	Flag int    `json:"flag"`
	Text string `json:"text"`
}

func (cs *ControlServer) textMessage(w http.ResponseWriter, r *http.Request) {
	id := r.PathValue("id")
	var req messageReq
	_ = json.NewDecoder(r.Body).Decode(&req)
	if err := cs.s.sendTextMessage(id, byte(req.Flag), req.Text); err != nil {
		writeJSON(w, http.StatusConflict, map[string]string{"error": err.Error()})
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"ok": true, "reporting_id": id})
}

func (cs *ControlServer) streams(w http.ResponseWriter, _ *http.Request) {
	writeJSON(w, http.StatusOK, map[string]any{"streams": cs.gw.Stats()})
}

func writeJSON(w http.ResponseWriter, code int, v any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(code)
	_ = json.NewEncoder(w).Encode(v)
}

// --- command senders ---

func (s *Server) videoEndpoint() (string, uint16) {
	return s.cfg.VideoPublicHost, uint16(s.cfg.VideoPublicTCPPort)
}

func (s *Server) sendRealtimeAV(reportingID string, channel, dataType, streamType byte) (string, uint16, error) {
	sess, ok := s.registry.GetByPhone(reportingID)
	if !ok {
		return "", 0, fmt.Errorf("device %s not connected", reportingID)
	}
	phone, hasVer, ver := sess.Identity()
	host, tcp := s.videoEndpoint()
	frame := jt808.BuildRealtimeAVRequest(phone, hasVer, ver, s.nextPlatformSerial(),
		host, tcp, uint16(s.cfg.VideoPublicUDPPort), channel, dataType, streamType)
	if err := sess.Send(frame); err != nil {
		return "", 0, err
	}
	s.log.Info("sent 0x9101 realtime AV request", "reporting_id", reportingID,
		"channel", channel, "video_host", host, "video_tcp", tcp)
	return host, tcp, nil
}

func (s *Server) sendAVControl(reportingID string, channel, command, closeType, switchType byte) error {
	sess, ok := s.registry.GetByPhone(reportingID)
	if !ok {
		return fmt.Errorf("device %s not connected", reportingID)
	}
	phone, hasVer, ver := sess.Identity()
	frame := jt808.BuildAVControl(phone, hasVer, ver, s.nextPlatformSerial(),
		channel, command, closeType, switchType)
	s.log.Info("sent 0x9102 AV control", "reporting_id", reportingID, "channel", channel, "cmd", command)
	return sess.Send(frame)
}

func (s *Server) sendPlayback(reportingID string, channel byte, startTime, endTime string) (string, uint16, error) {
	sess, ok := s.registry.GetByPhone(reportingID)
	if !ok {
		return "", 0, fmt.Errorf("device %s not connected", reportingID)
	}
	phone, hasVer, ver := sess.Identity()
	host, tcp := s.videoEndpoint()
	frame := jt808.BuildPlaybackRequest(phone, hasVer, ver, s.nextPlatformSerial(),
		host, tcp, uint16(s.cfg.VideoPublicUDPPort), channel,
		jt808.AVVideoOnly, jt808.StreamMain, 0, 0, 1,
		bcdTime(startTime), bcdTime(endTime))
	if err := sess.Send(frame); err != nil {
		return "", 0, err
	}
	s.log.Info("sent 0x9201 playback request", "reporting_id", reportingID, "channel", channel)
	return host, tcp, nil
}

func (s *Server) sendTextMessage(reportingID string, flag byte, text string) error {
	sess, ok := s.registry.GetByPhone(reportingID)
	if !ok {
		return fmt.Errorf("device %s not connected", reportingID)
	}
	phone, hasVer, ver := sess.Identity()
	frame := jt808.BuildTextMessage(phone, hasVer, ver, s.nextPlatformSerial(), flag, text)
	s.log.Info("sent 0x8300 text message", "reporting_id", reportingID, "flag", flag, "text_len", len(text))
	return sess.Send(frame)
}

// bcdTime converts a "YYMMDDhhmmss" string to 6 BCD bytes (zero-filled if blank).
func bcdTime(s string) []byte {
	out := make([]byte, 6)
	if len(s) != 12 {
		s = time.Now().UTC().Format("060102150405")
	}
	for i := 0; i < 6; i++ {
		out[i] = (s[i*2]-'0')<<4 | (s[i*2+1] - '0')
	}
	return out
}
