# Stage 5 Completion Report

Deployment, security hardening, backups/recovery, and load testing.
Date: 2026-11-03.

Most of Stage 5 is ops/config/docs plus runnable Python hardening and load
testing, so it was verified here despite the Go toolchain being unavailable this
session (see Stage 4 report).

## 1. Security hardening (API) — VERIFIED

- **Security headers** middleware (`app/hardening.py`): `Content-Security-Policy`
  (tuned to the dashboard's real deps — Leaflet via cdnjs, OSM tiles, same-origin
  API/WebSocket), `X-Content-Type-Options`, `X-Frame-Options: DENY`,
  `Referrer-Policy`, `Permissions-Policy`. Confirmed in the browser: the map,
  tiles, markers, geofence and live WebSocket all work under the CSP.
- **Login rate limiting**: per-IP sliding window on `POST /api/auth/login`
  (default 10 / 5 min) → `429` with `Retry-After`. Brute-force protection.
- **Production startup guard**: with `APP_ENV=production`, the API refuses to start
  if `JWT_SECRET` is the insecure default or if the demo feed is enabled.
- **Non-root containers**: the API image now runs as `appuser` (uid 10001); the
  ingestion image already did.
- Secrets stay in env/`.env` (never in code or logs); CORS configurable; audit log
  already records sensitive actions (Stages 2-4).

## 2. Deployment — docs + config

- `docker-compose.prod.yml` overlay: no host-published DB/Redis/API/control ports,
  `APP_ENV=production`, demo feed off, JSON log rotation (10m × 5),
  `restart: unless-stopped`, and a **Caddy** reverse proxy (TLS + WebSocket) on
  80/443 → `api:8080`. nginx alternative in `deploy/nginx.conf`.
- `DEPLOYMENT.md`: full runbook — prerequisites, env, start command, firewall/ufw,
  migrations, backups/restore, logging/monitoring, restart policy, a security
  checklist, load testing, and real-device setup.

## 3. Backups & recovery

- `scripts/backup.sh` — `pg_dump | gzip` with rotation (keeps N, default 14); cron
  example in the runbook.
- `scripts/restore.sh` — confirmed-destructive restore (ensures PostGIS first).
- `scripts/migrate.sh` — applies `migrations/*.up.sql` in order to an existing DB
  (compose only auto-runs them on first init).

## 4. Load testing

- **API load test** `tools/loadtest_api.py` (asyncio + httpx) — **executed live**
  against the running API: **4000 requests, 64 concurrency, 0 errors** on both
  `GET /api/devices` and `GET /api/auth/me`; ~156-160 req/s, p50 ~290 ms, p95
  ~1.1 s. Note: this is a **single uvicorn worker on Windows** (no uvloop) with the
  demo feed + event engine also running; production (Linux, uvloop, multiple
  `--workers` behind the proxy) scales substantially higher. The value proven here
  is correctness under sustained concurrency (zero errors) and a working, reusable
  benchmark.
- **Device load test** `services/ingestion/cmd/loadtest` (Go) — spawns N simulated
  terminals (register → auth → heartbeat/location) with ramp-up and progress
  metrics, for stress-testing ingestion on the VPS. (Not compiled this session —
  Go toolchain unavailable; same caveat as Stage 4.)

## 5. Test results

`pytest` → **36 passed** (4 new hardening tests: security headers present + CSP
allows dashboard deps, login rate limit returns 429, successful login within
limit, production refuses the default secret), plus all Stage 1-4 tests.

## 6. Not done / caveats

- **Go build/`go test`** (ingestion incl. the new `cmd/loadtest`, and Stage 4):
  VERIFIED (2026-11-04) once the toolchain downloaded — `go build`, `go vet` and
  `go test ./...` all pass, and the live video loop ran (see Stage 4 report).
- **Docker/PostGIS stack not launched here** (no container registry access in this
  environment); the compose files + overlay are complete — run
  `docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build`
  on the VPS.
- Multi-instance live feed still polls the store; move to Redis pub/sub for
  horizontal scaling of the WebSocket tier.
- Browser video playback (Stage 4) remains pending hardware.

## 7. Platform status

Stages 1-5 are code-complete. End-to-end verified here (in-memory/dev + browser):
device ingestion decode (Go, Stages 1 earlier), API + RBAC + live map, event/trip
engine + geofencing + alerts, video control plane + gateway metering, and the
Stage 5 hardening/ops. The remaining real-world step is validating against a
physical XV-900-8 and completing the video playback pipeline against a real stream.
