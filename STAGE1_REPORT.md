# Stage 1 Completion Report

Device-communication core for the XV-900-8 / ZH900 tracking platform.
Date: 2026-11-03. Toolchain used for verification: Go 1.27.3, Python 3.13.

## 1. Files and services created

- **`services/ingestion`** — standalone Go service (module `tracking/ingestion`):
  - `cmd/ingestion-server` — JT/T 808 TCP ingestion server (process entrypoint).
  - `cmd/simulator` — labelled JT/T 808 device simulator.
  - `internal/jt808` — framing (`frame.go`), BCD (`bcd.go`), header (`header.go`),
    message IDs (`message.go`), decoder (`decoder.go`), location (`location.go`),
    registration (`registration.go`), frame/response builders (`builders.go`).
  - `internal/inspector` — raw-packet hex/ASCII/boundary inspection.
  - `internal/server` — TCP listener (`server.go`), per-connection read loop +
    reassembly (`connection.go`), session registry (`session.go`), message
    handlers (`handler.go`).
  - `internal/store` — `Store` interface + models (`store.go`), in-memory store
    (`memory.go`), PostgreSQL/PostGIS store (`postgres.go`).
  - `internal/config` — environment-driven configuration.
  - `Dockerfile`, `Makefile`, `go.mod`, `go.sum`.
- **`migrations/`** — `0001_init.up.sql`, `0001_init.down.sql`.
- **`tools/verify_protocol.py`** — independent protocol cross-check.
- **Root** — `README.md`, `ARCHITECTURE.md`, `HARDWARE_PROTOCOL_FINDINGS.md`,
  `docker-compose.yml`, `.env.example`, `.gitignore`, this report.

## 2. Database tables and migrations

Migration `0001_init` (PostgreSQL + PostGIS) creates: `organizations`, `roles`
(seeded with the 6 roles), `users`, `fleets`, `vehicles`, `device_protocols`
(seeded JT808/JT1078), `tracking_devices`, `device_connections`, `raw_packets`,
`gps_positions` (PostGIS `geometry(Point,4326)`, GiST + BRIN + btree indexes),
`trips`, `geofences`, `alarms`, `events`, `camera_channels`, `video_sessions`,
`audit_logs`. Timestamps are `timestamptz` (UTC); positions keep both device and
server time, and a `valid` flag separating fresh from stale/no-fix reports.

## 3. TCP server listening status

VERIFIED. The server binds and logs e.g.
`{"msg":"jt808 ingestion listening","addr":"127.0.0.1:7808"}`.
Listen address is configurable via `INGEST_JT808_ADDR` (default `:7808`).

## 4. Supported protocol messages

Decoded and handled: `0x0100` registration (→ `0x8100` + auth code), `0x0102`
auth (→ `0x8001`), `0x0002` heartbeat (→ `0x8001`), `0x0200` location (decoded,
stored, → `0x8001`), `0x0003` logout, `0x0001`/`0x8001` general responses.
Any other message ID is **recorded and acknowledged as unsupported, never
discarded**. Version-aware (JT/T 808-2013 and -2019 headers auto-detected).

## 5. Unit and integration test results

`go vet ./...` → clean. `gofmt -l` → clean. `go test ./... -count=1` → PASS:

```
ok  tracking/ingestion/internal/inspector
ok  tracking/ingestion/internal/jt808
ok  tracking/ingestion/internal/server   (integration: full flow, unknown-frame, partial-frame)
```

Coverage includes: escape/unescape round trips, canonical checksum vector
(`0xce`), frame extraction (single/multiple/shared-delimiter/partial), header
parse, location decode incl. south/west signs and invalid-fix handling,
register round trip, unknown-message handling, and a full server integration
flow asserting reporting-id ≠ serial-number. The Python cross-check
(`tools/verify_protocol.py`) independently passes all checks.

## 6. Simulator test results

VERIFIED end-to-end against the running server. The simulator registered
(reporting_id `100000000001`, serial truncated to `SIMSERI` per the 2013 7-byte
field — distinct from the reporting id), authenticated, and sent 3 heartbeat +
location pairs. Server decoded all and stored positions
(lat 22.5726 → 22.5744, lon ~88.3639, speed 42.5, acc=true, valid=true), with
`decoded:8 unknown:0` and a clean EOF disconnect. All positions are **SIMULATED**
and labelled as such in logs.

## 7. Docker deployment status

`docker-compose.yml` defines db (postgis/postgis:16-3.4, auto-applies the
migrations), redis (reserved for Stage 2+) and the ingestion server (built from
`services/ingestion/Dockerfile`, port 7808). **Not executed in the build
environment** because Docker Desktop here has no container-registry network
access (cannot pull images). The compose/Dockerfile are complete and standard;
run `docker compose up --build` on a host with registry access.

## 8. What still requires a physical XV-900-8 device

- Confirm the actual protocol **version** (2013 vs 2019) and registration field
  contents your units emit.
- Confirm **transport is TCP** (UDP not yet implemented) and the real additional-
  info item set in `0x0200`.
- Capture any **vendor-specific message IDs** (they will appear in `raw_packets`
  with `decoded=false`).
- **JT/T 1078 video** (live/playback control, stream transport) — deferred to the
  Stage 4 media gateway and must be validated against the device.
- License-plate GBK decoding (kept raw for now).

Until a real device connects and sends a decoded message, hardware compatibility
is **not** claimed — only simulator- and spec-level validation is done.

## 9. Exact steps to point one physical device to the server

1. Deploy on a host with a public IP/domain; open inbound **TCP 7808** in the firewall.
2. Terminal settings → **mobile phone number** = the device reporting ID; set the **license plate**.
3. Network settings → **ministry-standard server** = your public IP + port 7808 (main server).
4. Set the **ministry protocol to 1078** (manual §6.1.4).
5. Ensure SIM/4G or WiFi data; INFO → Network shows "dialing successfully", Positioning shows a fix.
6. Watch the server logs and the `raw_packets` / `gps_positions` tables for the first real frames.
