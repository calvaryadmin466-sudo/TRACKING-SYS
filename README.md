# Vehicle Tracking Platform (XV-900-8 / ZH900)

An independent, production-oriented GPS + video vehicle tracking platform for
**XV-900-8 / ZH900** MDVR terminals. The platform owns its own device-ingestion
server and JT/T 808 protocol decoder — no Traccar.

> **Stage 1** delivers the foundation and the device-communication core: the
> JT/T 808 TCP ingestion server, raw-packet inspection, a modular decoder,
> PostgreSQL/PostGIS schema, a labelled device simulator, tests and Docker. See
> [`ARCHITECTURE.md`](ARCHITECTURE.md) and
> [`HARDWARE_PROTOCOL_FINDINGS.md`](HARDWARE_PROTOCOL_FINDINGS.md).

## Repository layout

```
migrations/                 PostgreSQL + PostGIS schema (auto-applied by compose)
services/ingestion/         Go JT/T 808 ingestion server + device simulator
services/api/               Python FastAPI service + Leaflet dashboard (Stage 2)
tools/verify_protocol.py    Independent protocol cross-check (no Go needed)
docker-compose.yml          db + redis + ingestion + api
.env.example                configuration template
```

## Quick start (Docker)

```bash
cp .env.example .env
# edit .env: set a real POSTGRES_PASSWORD
docker compose up --build
```

This starts PostgreSQL/PostGIS (schema auto-applied from `migrations/`), Redis,
and the ingestion server listening on TCP `7808`.

Then run the **labelled simulator** against it (from `services/ingestion`):

```bash
go run ./cmd/simulator -addr 127.0.0.1:7808 -count 5
```

You will see registration → auth → heartbeat → location, and the positions land
in the `gps_positions` table (with `simulated = false` for now — the simulator is
clearly labelled in logs; production/simulator separation is enforced via the
`simulated` columns as real devices are onboarded).

## Running without Docker (development)

Requires Go 1.23+.

```bash
cd services/ingestion
go mod download
go test ./...                    # unit + integration tests (in-memory store)
go run ./cmd/ingestion-server    # starts on :7808, in-memory store if no DATABASE_URL
```

To persist to a local PostgreSQL/PostGIS:

```bash
export DATABASE_URL="postgres://tracking:password@localhost:5432/tracking?sslmode=disable"
go run ./cmd/ingestion-server
```

## Configuration (environment)

| Variable               | Default   | Meaning |
|------------------------|-----------|---------|
| `INGEST_JT808_ADDR`    | `:7808`   | TCP listen address for device connections |
| `DATABASE_URL`         | *(empty)* | PostgreSQL DSN; empty → in-memory (no persistence) |
| `INGEST_READ_TIMEOUT`  | `5m`      | Close a connection idle (no heartbeat) this long |
| `INGEST_MAX_FRAME_BYTES` | `65536` | Reassembly buffer cap per connection |
| `INGEST_LOG_LEVEL`     | `info`    | `debug`/`info`/`warn`/`error` |
| `INGEST_LOG_RAW`       | `true`    | Log hex of every received chunk (also always stored) |

Nothing is hardcoded — device IDs, server address and port all come from config
or from the devices themselves.

## Pointing a real XV-900-8 at the server

Per the device manual (§5.2.2–5.2.3, §6.1.4):

1. Deploy this server on a host with a **public IP or domain** and open the
   **inbound TCP port** you chose (default **7808**) in the firewall.
2. On the terminal: **Terminal settings → mobile phone number** — set the unique
   **reporting ID** (this is the JT/T 808 device ID). Set the **license plate**.
3. **Network settings → ministry-standard server** — set the **main server IP/port**
   to your server's public IP and the port from step 1.
4. Set the **ministry protocol to 1078** (manual §6.1.4).
5. Ensure a working SIM / 4G or WiFi data connection; check **INFO → Network**
   shows "dialing successfully" and **Positioning** shows a GPS fix.
6. Watch the ingestion server logs and the `raw_packets` / `gps_positions` tables.
   The first real frames will appear there; compare against
   `HARDWARE_PROTOCOL_FINDINGS.md`.

> The platform does **not** claim a device works until it has actually connected
> and sent a valid, decoded message. Until then its decoding is validated only by
> the simulator and the protocol cross-check.

## API + dashboard (Stage 2, Python/FastAPI)

The API and the live Leaflet dashboard run as a separate process from the Go
ingestion server; in production both share the PostgreSQL/PostGIS database
(ingestion writes, API reads). See [STAGE2_REPORT.md](STAGE2_REPORT.md).

Run locally without a database (labelled simulated feed for UI demo):

```bash
cd services/api
python -m venv .venv
.venv/Scripts/pip install -r requirements.txt   # Linux/macOS: .venv/bin/pip
ADMIN_EMAIL=admin@example.com ADMIN_PASSWORD=admin12345 \
  .venv/Scripts/python -m uvicorn app.main:app --port 8080
```

Open http://localhost:8080 and sign in (`admin@example.com` / `admin12345`).
With `DATABASE_URL` set, the dashboard shows real data from the ingestion server
instead of the demo feed.

### Dashboard (redesigned SPA)

The dashboard is a build-free vanilla-JS single-page app (no framework) with a
dark fleet-operations design system, sidebar navigation and inline SVG icons —
served as static files by the API. Screens: **Fleet Overview**, **Live Tracking**
(Leaflet + OSM, marker clustering, filters, search, follow, detail panel, live
WebSocket with auto-reconnect and stale detection), **Vehicle Details**,
**Device Management** (incl. authorized raw-packet diagnostics), **Trips &
Playback**, **Alerts & Events** (acknowledge / resolve), **Geofences** (draw /
delete on a map), **Reports & Analytics** (per-vehicle metrics, scorecard, trips report + CSV export),
**Maintenance** (service reminders with real date & odometer due states), **Video Monitoring**
(JT/T 1078 control + live gateway stream stats — no fabricated footage),
**Notifications** (rule builder, webhook/email dispatch, delivery log),
**Users & Roles**, **Audit Log** and **Settings**. It is responsive (collapsible
nav, bottom-sheet lists on mobile). Vehicle status is derived from device
communication and GPS timestamps, never from the WebSocket connection alone, and
simulated data is always badged **SIMULATED**.

Run the API tests:

```bash
cd services/api && python -m pytest -q
```

Key endpoints: `POST /api/auth/login`, `GET /api/auth/me`, `GET /api/devices`,
`PATCH /api/devices/{id}`, `GET /api/devices/{id}/history`, `GET/POST /api/vehicles`,
`WS /api/ws/live?token=`.

**Stage 3** adds the event/trip engine and geofencing (see
[STAGE3_REPORT.md](STAGE3_REPORT.md)): a background engine detects overspeed,
ignition on/off, harsh acceleration/braking, GPS loss, geofence entry/exit and
device offline/online, and segments positions into trips. Endpoints:
`GET/POST /api/geofences`, `DELETE /api/geofences/{id}`, `GET /api/events`,
`GET /api/devices/{id}/trips`, `GET /api/trips/{id}`. The dashboard gains a live
alerts panel, geofence drawing, and trip route playback.

**Stage 4** adds JT/T 1078 video (see [STAGE4_REPORT.md](STAGE4_REPORT.md)): the Go
ingestion server runs a **media gateway** (TCP `7078`) that captures and meters
genuine device video streams, plus an internal control API; the Python API drives
video-control commands (`0x9101`/`0x9102`/`0x9201`) through it. Endpoints:
`GET /api/devices/{id}/cameras`, `POST /api/devices/{id}/video/live`,
`POST /api/devices/{id}/video/playback`, `POST /api/video/sessions/{id}/stop`,
`GET /api/video/sessions`, `GET /api/video/streams` (live gateway stats). The
dashboard gains a camera panel. **No fake video is shown**: browser playback of
the 1078 stream is deliberately left until it can be validated against a physical
XV-900-8.

**Fleet Operations (Stage 6)** adds maintenance tracking, notification dispatch,
and trip reports. Due states for maintenance items are computed from real calendar
dates and vehicle odometers (overdue, due soon within 7 days/500 km, ok, done).
Notification rules support severity filtering, wildcard event types (`alarm_*`),
real webhook dispatch, and delivery logging. Endpoints:
`GET/POST /api/maintenance`, `POST /api/maintenance/{id}/complete`,
`DELETE /api/maintenance/{id}`, `GET/POST /api/notifications/rules`,
`PUT /api/notifications/rules/{id}`, `DELETE /api/notifications/rules/{id}`,
`POST /api/notifications/rules/{id}/test`, `GET /api/notifications/log`,
`GET /api/reports/trips`, `GET /api/reports/trips.csv`.

## Production deployment (Stage 5)

See [DEPLOYMENT.md](DEPLOYMENT.md) for the full runbook. In short, on a VPS with
Docker:

```bash
cp .env.example .env   # set strong JWT_SECRET, CONTROL_TOKEN, POSTGRES_PASSWORD, PUBLIC_HOST, DOMAIN
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
```

The production overlay adds a Caddy reverse proxy (TLS + WebSocket), keeps the
database/Redis/control ports internal, enables production security settings, log
rotation and restart policies. Hardening includes a tuned Content-Security-Policy
and other security headers, per-IP login rate limiting, a production guard that
refuses insecure defaults, and non-root containers. Backups/restore/migrations are
in `scripts/`, and load-test tools in `tools/loadtest_api.py` (API) and
`services/ingestion/cmd/loadtest` (devices). See [STAGE5_REPORT.md](STAGE5_REPORT.md).

## Firewall / ports

| Port | Protocol | Purpose | Open to |
|------|----------|---------|---------|
| 7808 | TCP | JT/T 808 device ingestion | the internet (devices) |
| 8080 | TCP | API + dashboard (HTTP/WebSocket) | users (behind a reverse proxy/TLS) |
| 7078 | TCP | JT/T 1078 media gateway (device video) | the internet (devices) |
| 7900 | TCP | internal control API (API → ingestion) | internal only, token-guarded |
| 5432 | TCP | PostgreSQL | internal only |
| 6379 | TCP | Redis | internal only |

## Tests & verification

```bash
cd services/ingestion && go test ./...      # Go unit + integration tests
python tools/verify_protocol.py             # independent protocol cross-check
```
