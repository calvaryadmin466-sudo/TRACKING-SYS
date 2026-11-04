# Project Summary — Vehicle GPS + Video Tracking Platform

An independent, production-oriented fleet tracking platform for **XV-900-8 / ZH900**
MDVR terminals. It owns its own device-communication server and protocol decoder
(no Traccar): terminals connect over their configured server IP/port, the platform
decodes genuine GPS + video, stores it, and shows vehicles live on its own
dashboard. Multi-tenant; designed for hundreds–thousands of vehicles.

Repo: https://github.com/calvaryadmin466-sudo/TRACKING-SYS

## Architecture

```
 XV-900-8 / ZH900 ──TCP JT/T 808 (GPS/signalling)──►  ingestion (Go)  ─┐
                  ──TCP JT/T 1078 (video)──────────►  media gateway    │ store
                                                       control API :7900│
                                                            ▲           ▼
 users ──HTTPS──► Caddy ──► API (Python/FastAPI) ───────────┘   PostgreSQL + PostGIS
                              │  │                                    ▲
                     Leaflet dashboard  WebSocket (live)              │ Redis (scale)
```

The **Go ingestion server** and the **Python API** are separate processes that
share the database (ingestion writes, API reads), so devices keep reporting even
when the dashboard is closed. The Go server owns device sockets; the API issues
video commands through its internal control API.

## Components

| Layer | Tech | What it does |
|---|---|---|
| Ingestion | **Go** | JT/T 808 TCP server, raw-packet inspector, modular decoder (register/auth/heartbeat/0x0200 location), session registry, distinct device identity (reporting-id ≠ serial ≠ db-id) |
| Media gateway | **Go** | JT/T 1078 stream capture + per-(SIM, channel) metering; 0x9101/0x9102/0x9201 video commands; token-guarded control API |
| API | **Python / FastAPI** | JWT auth + bcrypt, 6-role RBAC with org isolation, device/vehicle/history/geofence/event/trip/video endpoints, live WebSocket, audit logs, security hardening |
| Engine | **Python** | Overspeed, ignition, harsh accel/brake, GPS loss, geofence enter/exit, offline/online, trip detection |
| Dashboard | **Leaflet + OSM** (build-free) | Live map, search/filter, info panel, alerts feed, geofence drawing, trip playback, camera panel (no fake video) |
| Data | **PostgreSQL + PostGIS** | 18-table schema + migrations; UTC timestamps; device + server time preserved |
| Ops | **Docker Compose + Caddy** | Prod overlay (TLS, log rotation, restart policies, internal-only DB/control), backup/restore/migrate scripts, load-test tools, device simulator |

## Repository layout

```
services/ingestion/   Go: JT/T 808 + 1078, media gateway, control API, simulator, loadtest
services/api/         Python FastAPI: API, engine, dashboard (app/web), tests
migrations/           PostgreSQL + PostGIS schema (0001 init, 0002 stage3)
deploy/               Caddyfile, nginx.conf
scripts/              backup.sh, restore.sh, migrate.sh
tools/                verify_protocol.py, verify_jt1078.py, loadtest_api.py
docker-compose.yml + docker-compose.prod.yml, .env.example
README.md, ARCHITECTURE.md, DEPLOYMENT.md, HARDWARE_PROTOCOL_FINDINGS.md, STAGE1-5_REPORT.md
```

## Status — verified vs pending

| Area | Status |
|---|---|
| JT/T 808 decode (framing, checksum, location, signs) | ✅ Go unit tests + Python cross-check |
| Ingestion server + simulator (register→auth→heartbeat→location) | ✅ live run, `go test ./...` green |
| JT/T 1078 parser + media gateway + video commands | ✅ `go test`, format cross-check, **live loop metered 122 real packets** |
| API: auth, RBAC, org isolation, devices/vehicles/history | ✅ 36 pytest passing |
| Event/trip engine + geofencing + alerts | ✅ unit + API tests, verified live in browser |
| Video control plane (API → control → 0x9101) | ✅ tests + live Go loop |
| Dashboard (live map, alerts, geofence, trips, cameras) | ✅ verified in browser (incl. under CSP) |
| Security hardening (CSP/headers, login rate limit, prod guards, non-root) | ✅ tested |
| Deployment (prod compose + Caddy), backups, load tests | ✅ API load test ran (4000 req, 0 errors); configs complete |
| **PostgreSQL/Docker stack running** | ⏳ not launched in dev env (no registry) — run on the VPS |
| **Physical XV-900-8 validation** | ⏳ awaits hardware (see HARDWARE_PROTOCOL_FINDINGS.md) |
| **Browser video playback** (1078 → fMP4/WebRTC/HLS) | ⏳ deferred until validated against a real stream |

## VPS bring-up checklist

1. Install Docker + Docker Compose v2 on a host with a public IP/domain.
2. `cp .env.example .env`; set strong `JWT_SECRET`, `CONTROL_TOKEN`,
   `POSTGRES_PASSWORD`, `ADMIN_PASSWORD`, `PUBLIC_HOST` (your IP/domain), `DOMAIN`.
3. `docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build`.
4. Open firewall: `443`, `80`, `7808` (JT808), `7078` (JT1078). Keep `5432`,
   `6379`, `7900` internal only.
5. Browse to `https://<domain>`, sign in (`ADMIN_EMAIL` / `ADMIN_PASSWORD`), then
   change the admin password.
6. For schema upgrades later: `DATABASE_URL=... ./scripts/migrate.sh`.
7. Schedule backups: cron → `scripts/backup.sh` (see DEPLOYMENT.md §6).

## Device onboarding checklist (per terminal)

1. Insert SIM; confirm 4G/WiFi data (INFO → Network = "dialing successfully").
2. Terminal settings → **mobile phone number** = unique reporting ID; set **license plate**.
3. Network settings → **ministry-standard server** = `PUBLIC_HOST:7808` (main server).
4. Set **ministry protocol = 1078**.
5. Confirm GPS fix (INFO → Positioning).
6. Watch the dashboard / `raw_packets` table for the first genuine frames; compare
   against `HARDWARE_PROTOCOL_FINDINGS.md` and register/assign the device + vehicle.

## Verify locally (dev)

```bash
# Go ingestion
cd services/ingestion && go test ./... && go build ./...
# Python API
cd services/api && python -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python -m pytest -q
# Run API + dashboard with a labelled demo feed (no DB):
ADMIN_EMAIL=admin@example.com ADMIN_PASSWORD=admin12345 \
  .venv/bin/python -m uvicorn app.main:app --port 8080    # http://localhost:8080
```

## Security must-dos before production
Strong secrets in `.env` (never committed) · `APP_ENV=production` · change admin +
all **device default passwords** · only 443/80/7808/7078 public · TLS on · backups
tested. Full checklist in DEPLOYMENT.md §9.
