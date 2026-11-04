# Architecture

An independent, multi-tenant GPS + video vehicle tracking platform for XV-900-8 /
ZH900 terminals. The platform owns its own device-communication server and
protocol decoder (no Traccar).

## System overview

```
  XV-900-8 / ZH900 terminal
        │  TCP (JT/T 808 signalling + GPS)         ┌──────────────┐
        ├─────────────────────────────────────────►│  ingestion   │
        │  TCP (JT/T 1078 video, future stage)      │  server (Go) │
        └───────────────────────────────┐          └──────┬───────┘
                                         │                 │ store.Store
                                   ┌─────▼──────┐   ┌──────▼─────────────┐
                                   │ media-gw   │   │ PostgreSQL+PostGIS │
                                   │ (Stage 4)  │   └──────┬─────────────┘
                                   └────────────┘          │
                                                    ┌──────▼──────┐   ┌───────────┐
                                                    │  API (TS)   │──►│ dashboard │
                                                    │  Stage 2    │   │ Next.js+  │
                                                    └─────────────┘   │ Leaflet   │
                                                           ▲          └───────────┘
                                                    ┌──────┴──────┐
                                                    │   Redis     │  live sessions / cache (Stage 2+)
                                                    └─────────────┘
```

**Key principle:** the ingestion server is a **separate process** from the web
application. Devices keep connecting and reporting even when no dashboard is open.

## Stage 1 scope (this delivery)

Implemented and tested:

- **TCP ingestion server** (`services/ingestion`, Go) — accepts device
  connections, reassembles frames, inspects raw packets, decodes JT/T 808,
  persists results, replies with the correct acknowledgements.
- **Raw packet inspector** — hex/ASCII dumps, frame-boundary detection, partial
  and concatenated frame handling; unidentified packets are always stored.
- **Modular JT/T 808 decoder** — version-aware (2013/2019) header, registration,
  heartbeat, auth and location decoding; unknown message IDs surfaced, not dropped.
- **Device identity** — reporting ID, serial number and DB id kept separate.
- **Session registry + heartbeat/timeout handling**.
- **PostgreSQL/PostGIS schema + migrations** for the full data model.
- **Labelled device simulator** and **unit + integration tests**.
- **Docker Compose** deployment.

## Ingestion server internals

```
cmd/ingestion-server   process entrypoint, config, store selection, signals
cmd/simulator          labelled JT/T 808 device simulator
internal/config        env-driven configuration (no hardcoded IDs/ports)
internal/inspector     raw packet hex/ASCII/boundary inspection
internal/jt808         framing, header, decoder, location, registration, builders
internal/server        TCP listener, connection read loop, session registry, handlers
internal/store         Store interface + MemoryStore (tests) + PostgresStore (prod)
```

### Data flow for one frame

1. `connection.go` reads bytes, `inspector.Capture` records a hex/ASCII view.
2. `jt808.ExtractFrames` reassembles complete frames (partial/concatenated safe).
3. `handler.go` calls `jt808.DecodeFrame`: unescape → verify checksum → parse
   header → decode body.
4. A `raw_packets` diagnostic row is written for **every** frame (decoded or not).
5. Recognised messages update the device registry / positions / events.
6. The server writes the correct JT/T 808 acknowledgement back to the device.

### Why Go for ingestion

High-concurrency TCP with cheap goroutines per connection, a strong standard
library (`net`, `log/slog`), static binaries for simple deployment, and
predictable latency — the right fit for thousands of long-lived device sockets.

## Persistence model

- All timestamps stored in UTC (`timestamptz`).
- `gps_positions` preserves **both** the device-reported time and the server
  reception time, and marks each fix `valid` (fresh) vs not (stale/no-fix).
- High-volume position storage uses a `(device_id, device_time desc)` btree, a
  BRIN index on `server_time`, and a GiST index on the PostGIS geometry.
- `raw_packets` keeps a partial index on undecoded packets for fast diagnostics.

## Store abstraction

`store.Store` is an interface. `MemoryStore` (stdlib only) powers unit and
integration tests and the no-database dev mode; `PostgresStore` (pgx) is the
production backend. The server code depends only on the interface.

## Multi-tenancy & RBAC (schema ready; enforcement in Stage 2)

`organizations`, `fleets`, `users`, `roles` and the FKs on devices/vehicles model
company-scoped isolation and the six roles (super_admin, company_admin,
fleet_manager, dispatcher, operator, readonly). The API layer (Stage 2) enforces
access; `audit_logs` records sensitive admin actions.

## Later stages

- **Stage 2:** API (auth, device/vehicle CRUD, live locations), RBAC enforcement,
  WebSocket live map (Leaflet + OSM), online/offline + fresh/stale display.
- **Stage 3:** trip detection & playback, geofencing, alert/event engine.
- **Stage 4 (done):** JT/T 1078 media gateway in the Go ingestion server (captures
  and meters genuine device streams), an internal token-guarded control API, and
  the Python video control plane (`0x9101`/`0x9102`/`0x9201`) + dashboard camera
  panel. Browser playback of the 1078 stream is deliberately deferred until it can
  be validated against a physical device. See [STAGE4_REPORT.md](STAGE4_REPORT.md).
- **Stage 5:** load testing, hardening, backups, full deployment runbook.

### Video command path (Stage 4)

The Go ingestion server owns the device TCP sockets, so video-control commands go:
dashboard → Python API → ingestion internal control API (`:7900`) → `0x9101` on the
device's live JT/T 808 socket → device dials the media gateway (`:7078`) → gateway
reassembles 1078 packets and reports per-(SIM, channel) stream stats, which the API
proxies back to the dashboard.
