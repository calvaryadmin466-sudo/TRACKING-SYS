# Stage 2 Completion Report

API, RBAC, live tracking dashboard and history for the tracking platform.
Date: 2026-11-03. Verified with Python 3.13 (FastAPI) + the built-in browser.

Language note: per your direction, the **API is Python (FastAPI)**; the device
ingestion server stays **Go** (Stage 1). Both talk to the same PostgreSQL/PostGIS
database in production (ingestion writes, API reads) — they remain separate
processes.

## 1. Service created

`services/api` — FastAPI application:
- `app/config.py` — env-driven settings (no hardcoded secrets/ports).
- `app/security.py` — bcrypt password hashing + JWT (HS256) issue/verify.
- `app/rbac.py` — 6 roles, organization data-isolation (`Principal.org_scope`).
- `app/deps.py` — auth dependencies (bearer token → `Principal`), role guards.
- `app/routers/` — `auth`, `devices`, `vehicles`, `positions` (history), `health`.
- `app/live.py` — `/api/ws/live` WebSocket (snapshot + incremental updates).
- `app/serialize.py` — computes online/offline and fresh/stale GPS from thresholds.
- `app/store/` — `Store` abstraction with `memory.py` (dev/tests) and
  `postgres.py` (asyncpg, reads the Stage 1 schema).
- `app/demo_feed.py` — LABELLED simulated feed (memory mode only).
- `app/web/` — build-free Leaflet + OpenStreetMap dashboard (`index.html`,
  `app.js`, `style.css`).
- `tests/` — pytest suite; `Dockerfile`, `requirements.txt`, `pytest.ini`.

## 2. Endpoints

- `POST /api/auth/login` → JWT (+ user), `GET /api/auth/me`.
- `GET /api/devices` (org-scoped list + status summary), `GET /api/devices/{id}`,
  `PATCH /api/devices/{id}` (assign vehicle / active / plate — manage roles only).
- `GET /api/vehicles`, `POST /api/vehicles`, `PUT /api/vehicles/{id}`.
- `GET /api/devices/{id}/history?from=&to=&limit=` (trip/route playback data).
- `GET /api/health`, `WS /api/ws/live?token=`.
- Sensitive mutations (login, device/vehicle changes) write to `audit_logs`.

## 3. Security & RBAC

- Passwords stored as **bcrypt** hashes (verified in tests: hash starts `$2`,
  never equals the plaintext).
- **JWT** bearer auth; invalid/missing/expired tokens → 401.
- Roles: super_admin, company_admin, fleet_manager, dispatcher, operator,
  readonly. Management actions limited to the first three.
- **Organization isolation**: non-super-admins only see/modify their own org's
  devices and vehicles; cross-org access → 403. Super admin sees all.

## 4. Live dashboard (build-free, Leaflet + OSM)

- Login screen → live map. Verified in the browser against the running API.
- Features working: live vehicle markers, status summary chips
  (All/Online/Moving/Offline/No GPS), vehicle list with **search/filter**,
  **info panel** (reporting id, serial, model, ignition, speed, heading, GPS
  fix fresh/stale, last comm, SIMULATED source), **online/offline** colouring,
  **fresh-vs-stale** GPS distinction, **history trail** polyline, live updates
  over WebSocket. Simulated devices are badged **SIM**.

## 5. Test results

`pytest` → **15 passed** (`services/api`). Covers: login success/failure,
unknown user, token required, invalid token, password-is-hashed; RBAC org
isolation (company admin sees only own org, super admin sees all, cross-org
403, readonly cannot modify); device list/summary + online/fresh status, vehicle
assignment, 404s; position history ordering + time filtering + auth required.

Browser verification (memory mode + demo feed): logged in as super admin, 8
labelled simulated vehicles rendered and moved live on the Kolkata map; summary
showed 8 online / 6 moving; info panel and history (72 points) confirmed.

## 6. Docker

`docker-compose.yml` now includes the `api` service (built from
`services/api/Dockerfile`, port 8080, `DATABASE_URL` → the shared Postgres,
`DEMO_FEED` off in Postgres mode). Not executed here (Docker cannot pull images
in this environment); run `docker compose up --build` on a host with registry
access.

## 7. How to run locally (no database)

```
cd services/api
python -m venv .venv && .venv/Scripts/pip install -r requirements.txt   # (Linux: .venv/bin/pip)
set ADMIN_EMAIL=admin@example.com & set ADMIN_PASSWORD=admin12345
.venv/Scripts/python -m uvicorn app.main:app --port 8080
# open http://localhost:8080  (login admin@example.com / admin12345)
```
In memory mode a labelled demo feed animates simulated vehicles. With
`DATABASE_URL` set, the API serves real data written by the Go ingestion server.

## 8. What still requires more work

- **Live cross-process path** (Go ingestion → Postgres → Python API → dashboard)
  was not run here because this environment can't run PostGIS (no Docker
  registry). The query layer is unit-tested; validate on a host with Postgres.
- Live WebSocket currently **polls** the store every ~2s (uniform across
  backends, no extra infra). Redis pub/sub is a later optimization for very large
  fleets.
- Minor: device/vehicle **delete** and a full **user-management** UI/endpoints are
  not yet built (create/seed + roles are). Geofencing, alerts/events engine and
  video remain Stage 3/4.

## 9. Next (Stage 3)

Trip detection & storage, geofencing (PostGIS), and the alert/event engine
(overspeed, ignition, offline, geofence in/out), surfaced via API + dashboard.
