# Stage 3 Completion Report

Trip detection, geofencing and the alert/event engine.
Date: 2026-11-03. Verified with Python 3.13 (FastAPI) + the built-in browser.

Built on the Stage 2 Python API. The engine is a backend-agnostic processor that
runs as a background task in the API process: in dev it consumes the in-memory
demo feed; in production it polls new positions written to PostgreSQL by the Go
ingestion server.

## 1. Code added (services/api)

- `app/geo.py` — haversine distance + ray-casting point-in-polygon (no PostGIS
  needed at processing time).
- `app/engine.py` — pure `EventEngine`: per-device state, edge-triggered rules,
  trip accumulation. Fully unit-testable.
- `app/engine_runner.py` — background runner (poll positions → events + trips →
  persist; periodic offline/online sweep).
- `app/routers/geofences.py`, `app/routers/events.py`, `app/routers/trips.py`.
- Store methods (memory + asyncpg): `positions_since`, `save_event`,
  `list_events`, geofence CRUD, `save_trip`/`list_trips`/`get_trip`.
- `migrations/0002_stage3` — adds `severity` + `value` to `events` (+ indexes).
- Dashboard: alerts panel, geofence rendering + click-to-draw, trip list + path.

## 2. Detected events / alarms

`ignition_on` / `ignition_off`, `overspeed` / `overspeed_cleared` (vs configurable
limit, edge-triggered), `harsh_acceleration` / `harsh_braking` (m/s² between
consecutive fixes), `gps_signal_loss` / `gps_restored`, `geofence_enter` /
`geofence_exit`, `device_offline` / `device_online`. Each event carries device,
reporting id, type, severity (info/warning/alarm), detail, value and timestamp.

## 3. Trips

Movement/ignition-based segmentation: a trip opens on movement, accumulates path,
distance (haversine) and max speed, and closes on ignition-off or an idle gap
(configurable). Trips below a minimum distance are discarded. Stored with path for
route playback.

## 4. Geofences

Create (polygon ring), list (org-scoped), delete. Stored as PostGIS `POLYGON` in
production (read back via GeoJSON); point-in-polygon is evaluated in the engine so
it works identically on both stores. Geofences apply to their organization (or
globally when org is null).

## 5. API endpoints added

- `GET/POST /api/geofences`, `DELETE /api/geofences/{id}`
- `GET /api/events?device_id=&types=&since=&limit=`
- `GET /api/devices/{id}/trips`, `GET /api/trips/{id}` (with path)

All organization-scoped; geofence create/delete require a management role.

## 6. Test results

`pytest` → **27 passed** (12 new):
- `test_engine.py` (8): overspeed edge-trigger, ignition transitions, harsh
  acceleration + braking, GPS loss/restore, geofence enter/exit, trip detection,
  offline/online sweep.
- `test_stage3_api.py` (4): geofence CRUD, ring min-points validation, event list
  + type filter, trip list + detail path.
- Plus the 15 Stage 2 tests still passing.

Live run (memory mode, engine + demo feed, ~25s): produced ignition_on/off (12/11),
overspeed (10) + overspeed_cleared (8), harsh_acceleration (28), harsh_braking
(27), geofence_enter, and **3 completed trips**. Browser-verified: alerts panel
populated with live events (with severity dots), the "Central Depot Zone" geofence
rendered on the map, Draw-zone + Alerts controls, and an overspeeding vehicle
(108 km/h) in the list.

## 7. What still needs work

- The **PostGIS path was not run live here** (no Docker registry in this
  environment). The asyncpg queries (incl. `ST_GeomFromText`/`ST_AsGeoJSON`) are
  written; validate with `docker compose up --build` on a host with Postgres.
- Engine state is **in-process/in-memory**; on restart it re-baselines (no
  duplicate historical events, but open trips in flight are lost). For HA, move
  engine state to Redis/DB — later.
- Geofence drawing is a lightweight built-in tool (click points → save); a richer
  editor (circles, edit existing) is a future refinement.
- Notifications (email/push/webhook) for alarms are not built; events are stored
  and surfaced in the dashboard feed.

## 8. Next (Stage 4)

JT/T 1078 video: media gateway, live/playback control messages — only the parts
verified against a physical XV-900-8.
