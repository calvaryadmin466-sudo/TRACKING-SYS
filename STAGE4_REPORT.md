# Stage 4 Completion Report

JT/T 1078 video: media gateway, device video-control plane and dashboard camera
panel. Date: 2026-11-03.

This is the stage that genuinely needs a physical XV-900-8 to validate fully, so it
is built strictly to the public JT/T 1078-2016 / JT/T 808 video command spec, it
captures and meters **real** device streams only, and it shows **no fake video**.

## 1. Code added

**Go ingestion (`services/ingestion`):**
- `internal/jt1078/packet.go`, `build.go` — JT/T 1078 "01cd" packet parser + encoder
  (version/audio/transparent header lengths, SIM/channel/data-type, timestamp,
  body framing) and a stream de-framer (`ExtractPackets`) that handles partial and
  concatenated packets and resyncs on junk.
- `internal/mediagw/gateway.go` — TCP media gateway: accepts device video
  connections, reassembles 1078 packets, and reports per-(SIM, channel) stream
  stats (packets, bytes, video/key/audio frames, last-seen). Captures genuine
  streams; it does not fabricate or transcode video.
- `internal/jt808/video.go` — `0x9101` (real-time A/V request), `0x9102` (A/V
  control), `0x9201` (playback request) builders + a `0x9101` parser.
- `internal/server/control.go` — internal, token-guarded HTTP control API the web
  API calls to issue those commands to a connected device and to read gateway
  stats; `session.go` gains `Send`/`Identity` so commands reach the device's live
  socket.
- `cmd/ingestion-server` wires the gateway + control API alongside JT/T 808;
  `cmd/simulator` now answers `0x9101` by dialing the gateway and streaming
  labelled 1078 packets (and a standalone `-video-addr` mode).

**Python API (`services/api`):**
- `app/control_client.py` — client for the ingestion control API.
- `app/routers/video.py` — `GET /api/devices/{id}/cameras`,
  `POST /api/devices/{id}/video/live`, `POST /api/devices/{id}/video/playback`,
  `POST /api/video/sessions/{id}/stop`, `GET /api/video/sessions`,
  `GET /api/video/streams` (proxies live gateway stats). Read-only users are
  denied video access; all endpoints are organization-scoped and audited.
- Store methods for camera channels + video sessions (memory + asyncpg).
- Dashboard camera panel: per-channel "Live" buttons, an honest placeholder
  ("No live picture — JT/T 1078 relay pending hardware") and a live
  received-stream stats line.

## 2. Verification status (read carefully)

- **Python video control plane: VERIFIED.** `pytest` → **32 passed** (5 new video
  tests: camera list, live command dispatch, failure → failed session, gateway
  stats proxy, read-only denial), plus all Stage 1-3 tests.
- **JT/T 1078 packet format: INDEPENDENTLY VERIFIED** via
  `tools/verify_jt1078.py` (standard-library reference cross-check): header
  lengths (video 30 / audio 26 / transparent 18), field offsets, SIM/channel,
  body framing and concatenated-packet splitting all pass. This mirrors the Go
  parser's logic.
- **Go build / `go test` / live end-to-end loop: VERIFIED (2026-11-04).** After the
  Go toolchain finally downloaded, `go build ./...`, `go vet ./...` and
  `go test ./...` all pass (incl. the new `jt1078` package tests). The full live
  loop was run: ingestion (`:7808` + gateway `:7078` + control `:7900`) + the
  device simulator → the control API sent `0x9101` → the simulator dialed the
  gateway and streamed labelled 1078 packets → the gateway metered genuine packets
  (**122 packets, 122 video frames, 9 key frames, ~123 KB** for sim
  `100000000001` ch 1). This exercises the entire video command + capture path end
  to end (everything except browser playback, below).

### To verify the Go side + the live loop (on any machine with Go 1.23+ or Docker)

```bash
cd services/ingestion && go test ./... && go build ./...
# Terminal A: start ingestion (JT808 :7808, media gateway :7078, control :7900)
INGEST_CONTROL_TOKEN=dev go run ./cmd/ingestion-server
# Terminal B: start the API pointed at the control API
CONTROL_URL=http://127.0.0.1:7900 CONTROL_TOKEN=dev \
  python -m uvicorn app.main:app --port 8080   # (from services/api)
# Terminal C: a simulated device that answers 0x9101 and streams 1078
go run ./cmd/simulator -id 100000000001
# Then in the dashboard: select the device -> Cameras -> CH1 Live.
# The API sends 0x9101, the simulator dials the gateway and streams labelled
# 1078 packets, and the camera panel shows the received-stream stats growing.
```

## 3. What still requires a physical XV-900-8

- Confirm the device's real `0x9101`/`0x1205` behaviour and 1078 header variant
  (2016 vs 2019 SIM length) — the parser is 2016 (6-byte BCD SIM); add an adapter
  if your units use 2019.
- **Browser playback**: relaying/transcoding the 1078 H.264/H.265 payload into a
  browser-playable stream (fMP4 over WebSocket, or WebRTC/HLS) is deliberately not
  built — it must be designed against a real stream. The gateway already captures
  the frames needed to feed such a pipeline.
- Two-way intercom, PTZ, and stored-file (resource list) workflows.

## 4. Next (Stage 5)

Load testing, security hardening, automated backups and the full deployment
runbook — plus, once hardware is available, completing the video playback pipeline.
