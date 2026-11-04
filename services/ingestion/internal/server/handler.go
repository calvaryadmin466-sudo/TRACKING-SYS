package server

import (
	"context"
	"crypto/rand"
	"encoding/hex"
	"net"
	"strings"
	"time"

	"tracking/ingestion/internal/inspector"
	"tracking/ingestion/internal/jt808"
	"tracking/ingestion/internal/store"
)

// isSimulatedRegistration recognises devices created by this project's simulator
// / load-test tools so their data can be flagged simulated end-to-end. Real
// terminals never use these manufacturer codes or the "-SIM" model suffix.
func isSimulatedRegistration(reg *jt808.Registration) bool {
	mf := strings.ToUpper(reg.ManufacturerID)
	if mf == "SIMUL" || mf == "LOAD" {
		return true
	}
	return strings.Contains(strings.ToUpper(reg.TerminalModel), "SIM")
}

// handleFrame decodes one reassembled frame, persists a raw-packet diagnostic
// record (always), dispatches recognised messages and writes the appropriate
// JT/T 808 acknowledgement back to the device.
func (s *Server) handleFrame(ctx context.Context, conn net.Conn, sess *Session, frame []byte) {
	now := time.Now().UTC()
	msg, err := jt808.DecodeFrame(frame)

	// The raw packet is recorded for every frame, decoded or not.
	rec := store.RawPacket{
		ConnID:      sess.ConnID,
		RemoteAddr:  sess.RemoteAddr,
		ReportingID: sess.ReportingID(),
		ReceivedAt:  now,
		Length:      len(frame),
		Hex:         inspector.Hex(frame),
		ASCII:       inspector.ASCII(frame),
	}

	if err != nil {
		rec.Decoded = false
		rec.MessageName = "undecodable"
		rec.Note = "decode error: " + err.Error()
		_ = s.store.SaveRawPacket(ctx, rec)
		sess.Unknown.Add(1)
		s.log.Warn("undecodable frame", "conn", sess.ConnID, "err", err, "hex", rec.Hex)
		return
	}

	id := msg.Header.MsgID
	rec.MessageID = &id
	rec.MessageName = msg.Kind
	rec.Decoded = msg.Recognised
	rec.ChecksumOK = msg.ChecksumOK
	if msg.Header.ID != "" {
		rec.ReportingID = msg.Header.ID
	}

	// Bind the session to its reporting id the first time we see it.
	if sess.ReportingID() == "" && msg.Header.ID != "" {
		sess.setIdentity(msg.Header.ID, msg.Header.PhoneBCD, msg.Header.HasVersion, msg.Header.Version)
		s.registry.bind(msg.Header.ID, sess)
	}
	sess.touch(now)

	if !msg.ChecksumOK {
		rec.Note = "checksum mismatch"
		_ = s.store.SaveRawPacket(ctx, rec)
		sess.Unknown.Add(1)
		s.log.Warn("checksum mismatch", "conn", sess.ConnID, "msg", msg.Kind, "hex", rec.Hex)
		// Tell the device the message was malformed rather than ignoring it.
		s.reply(conn, jt808.BuildPlatformGeneralResp(msg.Header, s.nextPlatformSerial(), id, jt808.ResultMessageError))
		return
	}

	_ = s.store.SaveRawPacket(ctx, rec)
	if msg.Recognised {
		sess.Decoded.Add(1)
	} else {
		sess.Unknown.Add(1)
	}

	switch id {
	case jt808.MsgTerminalRegister:
		s.handleRegister(ctx, conn, sess, msg)
	case jt808.MsgTerminalAuth:
		s.handleAuth(ctx, conn, sess, msg)
	case jt808.MsgTerminalHeartbeat:
		s.handleHeartbeat(ctx, conn, sess, msg)
	case jt808.MsgLocationReport:
		s.handleLocation(ctx, conn, sess, msg)
	case jt808.MsgTerminalLogout:
		s.reply(conn, jt808.BuildPlatformGeneralResp(msg.Header, s.nextPlatformSerial(), id, jt808.ResultSuccess))
	case jt808.MsgTerminalGeneralResp, jt808.MsgPlatformGeneralResp:
		// Acknowledgement of a platform message; nothing to reply.
	default:
		// Recognised framing but unsupported message: acknowledge as unsupported
		// so the device knows it was received, and keep the raw record for study.
		s.log.Info("unsupported message", "conn", sess.ConnID, "msg_id", msg.Kind,
			"reporting_id", msg.Header.ID, "hex", rec.Hex)
		s.reply(conn, jt808.BuildPlatformGeneralResp(msg.Header, s.nextPlatformSerial(), id, jt808.ResultUnsupported))
	}
}

func (s *Server) handleRegister(ctx context.Context, conn net.Conn, sess *Session, msg *jt808.Message) {
	reg := msg.Registration
	dev := store.Device{
		ReportingID: msg.Header.ID,
		Protocol:    "JT808",
		LastSeen:    time.Now().UTC(),
	}
	if reg != nil {
		dev.SerialNumber = reg.TerminalID
		dev.Model = reg.TerminalModel
		dev.Manufacturer = reg.ManufacturerID
		dev.Plate = reg.Plate
		sess.setSerial(reg.TerminalID)
		// Data integrity: flag devices that identify themselves as simulators so
		// their records stay distinct from genuine device data everywhere.
		if isSimulatedRegistration(reg) {
			dev.Simulated = true
			sess.setSimulated(true)
			s.log.Info("device flagged simulated", "reporting_id", msg.Header.ID,
				"manufacturer", reg.ManufacturerID, "model", reg.TerminalModel)
		}
	}
	authCode := generateAuthCode()
	dev.AuthCode = authCode

	dbID, err := s.store.UpsertDevice(ctx, dev)
	if err != nil {
		s.log.Error("upsert device failed", "conn", sess.ConnID, "reporting_id", dev.ReportingID, "err", err)
		s.reply(conn, jt808.BuildRegisterResp(msg.Header, s.nextPlatformSerial(), jt808.RegResultNoSuchTerminal, ""))
		return
	}
	sess.setDBID(dbID)
	_ = s.store.SaveEvent(ctx, store.Event{
		DeviceID: dbID, ReportingID: dev.ReportingID, Type: "register",
		At: time.Now().UTC(), Detail: "serial=" + dev.SerialNumber + " model=" + dev.Model,
	})
	s.log.Info("device registered", "conn", sess.ConnID, "reporting_id", dev.ReportingID,
		"serial", dev.SerialNumber, "model", dev.Model, "db_id", dbID)
	s.reply(conn, jt808.BuildRegisterResp(msg.Header, s.nextPlatformSerial(), jt808.RegResultSuccess, authCode))
}

func (s *Server) handleAuth(ctx context.Context, conn net.Conn, sess *Session, msg *jt808.Message) {
	sess.setAuthenticated(true)
	// Ensure a device row exists even if auth arrives before/without registration.
	if sess.DBID() == 0 && msg.Header.ID != "" {
		if id, err := s.store.UpsertDevice(ctx, store.Device{
			ReportingID: msg.Header.ID, Protocol: "JT808", LastSeen: time.Now().UTC(),
		}); err == nil {
			sess.setDBID(id)
		}
	}
	_ = s.store.TouchDevice(ctx, msg.Header.ID, time.Now().UTC())
	s.log.Info("device authenticated", "conn", sess.ConnID, "reporting_id", msg.Header.ID)
	s.reply(conn, jt808.BuildPlatformGeneralResp(msg.Header, s.nextPlatformSerial(), jt808.MsgTerminalAuth, jt808.ResultSuccess))
}

func (s *Server) handleHeartbeat(ctx context.Context, conn net.Conn, sess *Session, msg *jt808.Message) {
	_ = s.store.TouchDevice(ctx, msg.Header.ID, time.Now().UTC())
	s.reply(conn, jt808.BuildPlatformGeneralResp(msg.Header, s.nextPlatformSerial(), jt808.MsgTerminalHeartbeat, jt808.ResultSuccess))
}

func (s *Server) handleLocation(ctx context.Context, conn net.Conn, sess *Session, msg *jt808.Message) {
	loc := msg.Location
	if loc == nil {
		s.reply(conn, jt808.BuildPlatformGeneralResp(msg.Header, s.nextPlatformSerial(), jt808.MsgLocationReport, jt808.ResultMessageError))
		return
	}
	pos := store.Position{
		DeviceID:    sess.DBID(),
		ReportingID: msg.Header.ID,
		DeviceTime:  loc.DeviceTime,
		ServerTime:  time.Now().UTC(),
		Latitude:    loc.Latitude,
		Longitude:   loc.Longitude,
		Altitude:    loc.Altitude,
		Speed:       loc.Speed,
		Heading:     loc.Heading,
		ACC:         loc.ACC,
		Positioned:  loc.Positioned,
		Valid:       loc.Valid,
		AlarmFlag:   loc.AlarmFlag,
		StatusFlag:  loc.Status,
		Satellites:  loc.Satellites,
		MileageKM:   loc.MileageKM,
		Simulated:   sess.Simulated(),
		RawHex:      inspector.Hex(msg.Body),
	}
	// Decode device-reported alarm bits into named safety alarms (rising edge).
	if rising := sess.newAlarmBits(loc.AlarmFlag); rising != 0 {
		for _, name := range jt808.AlarmNames(rising) {
			_ = s.store.SaveEvent(ctx, store.Event{
				DeviceID: sess.DBID(), ReportingID: msg.Header.ID,
				Type: "alarm_" + name, Severity: "alarm", At: time.Now().UTC(),
				Detail: "device-reported alarm", Latitude: loc.Latitude, Longitude: loc.Longitude,
				HasLocation: loc.Valid, Simulated: sess.Simulated(),
			})
			s.log.Warn("device alarm", "reporting_id", msg.Header.ID, "alarm", name)
		}
	}

	if err := s.store.SavePosition(ctx, pos); err != nil {
		s.log.Error("save position failed", "conn", sess.ConnID, "reporting_id", msg.Header.ID, "err", err)
	} else {
		s.log.Info("position", "reporting_id", msg.Header.ID,
			"lat", loc.Latitude, "lon", loc.Longitude, "speed", loc.Speed,
			"acc", loc.ACC, "valid", loc.Valid, "device_time", loc.DeviceTime.Format(time.RFC3339))
	}
	_ = s.store.TouchDevice(ctx, msg.Header.ID, time.Now().UTC())
	s.reply(conn, jt808.BuildPlatformGeneralResp(msg.Header, s.nextPlatformSerial(), jt808.MsgLocationReport, jt808.ResultSuccess))
}

// reply writes a prebuilt frame to the device, logging any write error.
func (s *Server) reply(conn net.Conn, frame []byte) {
	if len(frame) == 0 {
		return
	}
	if _, err := conn.Write(frame); err != nil {
		s.log.Warn("reply write failed", "err", err)
	}
}

// generateAuthCode returns a short random hex authentication token issued to a
// device on registration (used by the device in its 0x0102 auth message).
func generateAuthCode() string {
	b := make([]byte, 8)
	if _, err := rand.Read(b); err != nil {
		return "00000000"
	}
	return hex.EncodeToString(b)
}
