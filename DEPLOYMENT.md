# Deployment Runbook

Deploying the tracking platform on a VPS / dedicated server with a public IP.
The stack: PostgreSQL+PostGIS, Redis, the Go ingestion server (JT/T 808 + JT/T
1078 media gateway), the Python API + dashboard, and a Caddy reverse proxy for
TLS.

## 1. Prerequisites

- Linux host with a public IP (or domain) and Docker + Docker Compose v2.
- Open inbound ports (see §4).
- A domain pointed at the host if you want automatic HTTPS.

## 2. Configure

```bash
cp .env.example .env
# Edit .env and set STRONG values:
#   POSTGRES_PASSWORD   - database password
#   JWT_SECRET          - long random string (e.g. `openssl rand -hex 32`)
#   CONTROL_TOKEN       - long random string (API <-> ingestion control channel)
#   ADMIN_PASSWORD      - initial admin password (change after first login)
#   PUBLIC_HOST         - your server's public IP/domain (sent to devices in 0x9101)
#   DOMAIN              - your domain for TLS (Caddy); omit to use self-signed localhost
```

The API refuses to start with `APP_ENV=production` if `JWT_SECRET` is left at the
insecure default or if the demo feed is enabled.

## 3. Start (production)

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
```

This runs:
- `db` (PostGIS) — schema auto-applied from `migrations/` on first init, data in a
  named volume; **not** published to the host.
- `redis` — internal only (reserved for scaling the live feed/sessions).
- `ingestion` — JT/T 808 on `7808`, JT/T 1078 media gateway on `7078`, internal
  control API on `7900` (not published).
- `api` — FastAPI + dashboard, internal; reached only through the proxy.
- `caddy` — TLS termination + reverse proxy on `80`/`443` → `api:8080`
  (WebSocket upgrade handled automatically). An nginx alternative is in
  `deploy/nginx.conf`.

Open `https://<your-domain>` and sign in with `ADMIN_EMAIL` / `ADMIN_PASSWORD`.

## 4. Firewall / ports

| Port | Proto | Purpose | Expose to |
|------|-------|---------|-----------|
| 443 / 80 | TCP | Dashboard + API via Caddy (TLS) | the internet (users) |
| 7808 | TCP | JT/T 808 device ingestion | the internet (devices) |
| 7078 | TCP | JT/T 1078 media gateway (device video) | the internet (devices) |
| 5432 | TCP | PostgreSQL | **internal only** |
| 6379 | TCP | Redis | **internal only** |
| 7900 | TCP | internal control API | **internal only** (token-guarded) |

Example with ufw:

```bash
ufw allow 80/tcp && ufw allow 443/tcp
ufw allow 7808/tcp && ufw allow 7078/tcp
ufw enable
# Do NOT open 5432/6379/7900.
```

## 5. Database migrations (upgrades)

The compose Postgres runs `migrations/` only on the **first** initialisation of an
empty volume. To apply later migrations (e.g. `0002_stage3`) to an existing DB:

```bash
DATABASE_URL=postgres://tracking:PASS@localhost:5432/tracking ./scripts/migrate.sh
```

## 6. Backups & recovery

Automated nightly backup with rotation (keeps 14 by default):

```bash
# crontab -e
0 2 * * *  DATABASE_URL=postgres://tracking:PASS@localhost:5432/tracking \
           BACKUP_DIR=/var/backups/tracking /opt/app/scripts/backup.sh
```

Restore (destructive, prompts for confirmation):

```bash
DATABASE_URL=postgres://tracking:PASS@localhost:5432/tracking \
  ./scripts/restore.sh /var/backups/tracking/tracking_YYYYMMDDTHHMMSSZ.sql.gz
```

Recovery drill: periodically restore the latest dump into a scratch database and
run `GET /api/health` + a spot query to confirm integrity.

## 7. Logging & monitoring

- Containers log as JSON with rotation (`max-size 10m`, `max-file 5`) — view with
  `docker compose logs -f <service>`. Ship to a central collector (Loki, ELK,
  CloudWatch) via a logging driver if desired.
- Health: `GET /api/health` (API) and `GET /internal/health` (ingestion control,
  internal). Add an uptime monitor against the public `/api/health`.
- The ingestion server records every device frame in `raw_packets` and connection
  lifecycle in `device_connections` for diagnostics.

## 8. Service restart policies

All services use `restart: unless-stopped`; `db` has a healthcheck and the API/
ingestion `depends_on` it. Docker restarts crashed containers automatically; the
host should run Docker on boot (`systemctl enable docker`).

## 9. Security checklist

- [ ] Strong `JWT_SECRET`, `CONTROL_TOKEN`, `POSTGRES_PASSWORD` set; `.env` not committed.
- [ ] `APP_ENV=production` (set by the API image; refuses insecure defaults).
- [ ] Admin password changed after first login.
- [ ] Only 443/80/7808/7078 open to the internet.
- [ ] TLS active (Caddy auto-HTTPS with a real `DOMAIN`).
- [ ] **Change the default device passwords** on each terminal before deployment.
- [ ] Containers run as non-root (api + ingestion images do).
- [ ] Backups scheduled and a restore tested.

## 10. Load testing

- **API tier** (runnable anywhere with the venv):
  ```bash
  python tools/loadtest_api.py --url https://<host> --requests 4000 --concurrency 64
  ```
  Reports throughput + p50/p95/p99 latency. Scale by raising uvicorn workers
  (`--workers N`, Linux uses uvloop) behind the proxy.
- **Device tier** (Go): spawn many simulated terminals against ingestion:
  ```bash
  cd services/ingestion
  go run ./cmd/loadtest -addr <host>:7808 -devices 1000 -interval 10s -duration 5m
  ```
  All simulated devices are clearly labelled; never run this against a server
  carrying real fleets.

## 11. Pointing a real XV-900-8 at the server

See README → "Pointing a real XV-900-8 at the server" and
`HARDWARE_PROTOCOL_FINDINGS.md`. In short: set the terminal's mobile-phone-number
(reporting ID) and license plate, set the ministry-standard server IP/port to your
`PUBLIC_HOST:7808`, set the ministry protocol to 1078, and watch `raw_packets` /
the dashboard for the first genuine frames.
