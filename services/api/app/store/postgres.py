"""PostgreSQL/PostGIS Store (asyncpg). Reads the schema created by /migrations;
the Go ingestion server writes devices and positions, the API reads them.
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Optional

import asyncpg

from .base import (
    AuditEntry, CameraChannel, DevicePatch, DeviceStatus, Event, Geofence, LivePosition,
    MaintenanceItem, NotificationLogEntry, NotificationRule, Organization, Position,
    RawPacketView, Role, Store, Trip, User, Vehicle, VideoSession,
)

_DEVICE_SELECT = """
SELECT d.id, d.reporting_id, d.serial_number, d.model, d.manufacturer, d.plate, d.protocol,
       d.simulated, d.is_active, d.organization_id, d.vehicle_id, COALESCE(v.registration,''),
       d.first_seen, d.last_seen,
       p.lat, p.lon, p.speed, p.heading, p.altitude, p.acc, p.positioned, p.valid,
       p.device_time, p.server_time, p.mileage_km, (p.server_time IS NOT NULL) AS has_pos
FROM tracking_devices d
LEFT JOIN vehicles v ON v.id = d.vehicle_id
LEFT JOIN LATERAL (
    SELECT ST_Y(gp.geom) AS lat, ST_X(gp.geom) AS lon, gp.speed, gp.heading, gp.altitude,
           gp.acc, gp.positioned, gp.valid, gp.device_time, gp.server_time, gp.mileage_km
    FROM gps_positions gp WHERE gp.device_id = d.id
    ORDER BY gp.server_time DESC LIMIT 1
) p ON true
"""


def _device_from_row(r: asyncpg.Record) -> DeviceStatus:
    d = DeviceStatus(
        id=r[0], reporting_id=r[1], serial_number=r[2], model=r[3], manufacturer=r[4],
        plate=r[5], protocol=r[6], simulated=r[7], active=r[8],
        organization_id=r[9], vehicle_id=r[10], vehicle_registration=r[11],
        first_seen=r[12], last_seen=r[13], has_position=r[25],
    )
    if d.has_position:
        d.latitude = r[14] or 0.0
        d.longitude = r[15] or 0.0
        d.speed = r[16] or 0.0
        d.heading = r[17] or 0
        d.altitude = r[18] or 0
        d.acc = bool(r[19])
        d.positioned = bool(r[20])
        d.valid = bool(r[21])
        d.device_time = r[22]
        d.server_time = r[23]
        d.mileage_km = r[24] or 0.0
    return d


class PostgresStore(Store):
    def __init__(self, dsn: str) -> None:
        self._dsn = dsn
        self._pool: Optional[asyncpg.Pool] = None

    async def startup(self) -> None:
        self._pool = await asyncpg.create_pool(self._dsn, min_size=1, max_size=10)

    async def close(self) -> None:
        if self._pool:
            await self._pool.close()

    @property
    def pool(self) -> asyncpg.Pool:
        assert self._pool is not None, "store not started"
        return self._pool

    # --- auth & tenancy ---
    async def get_user_by_email(self, email: str) -> Optional[User]:
        r = await self.pool.fetchrow("""
            SELECT u.id, u.organization_id, u.role_id, r.name, u.email, u.password_hash,
                   u.full_name, u.is_active, u.created_at, u.last_login_at
            FROM users u JOIN roles r ON r.id = u.role_id
            WHERE lower(u.email) = lower($1)""", email)
        if not r:
            return None
        return User(id=r[0], organization_id=r[1], role_id=r[2], role_name=r[3],
                    email=r[4], password_hash=r[5], full_name=r[6], is_active=r[7],
                    created_at=r[8], last_login_at=r[9])

    async def create_user(self, u: User) -> int:
        return await self.pool.fetchval("""
            INSERT INTO users (organization_id, role_id, email, password_hash, full_name, is_active)
            VALUES ($1,$2,lower($3),$4,$5,$6) RETURNING id""",
            u.organization_id, u.role_id, u.email, u.password_hash, u.full_name, u.is_active)

    async def update_user_last_login(self, user_id: int, at: datetime) -> None:
        await self.pool.execute("UPDATE users SET last_login_at=$2 WHERE id=$1", user_id, at)

    async def count_users(self) -> int:
        return await self.pool.fetchval("SELECT count(*) FROM users")

    async def create_organization(self, name: str, slug: str) -> int:
        return await self.pool.fetchval("""
            INSERT INTO organizations (name, slug) VALUES ($1,$2)
            ON CONFLICT (slug) DO UPDATE SET name=EXCLUDED.name RETURNING id""", name, slug)

    async def role_id_by_name(self, name: str) -> Optional[int]:
        return await self.pool.fetchval("SELECT id FROM roles WHERE name=$1", name)

    # --- devices ---
    async def list_devices(self, org_id: Optional[int]) -> list[DeviceStatus]:
        rows = await self.pool.fetch(
            _DEVICE_SELECT + " WHERE ($1::bigint IS NULL OR d.organization_id=$1) ORDER BY d.id",
            org_id)
        return [_device_from_row(r) for r in rows]

    async def get_device(self, device_id: int) -> Optional[DeviceStatus]:
        r = await self.pool.fetchrow(_DEVICE_SELECT + " WHERE d.id=$1", device_id)
        return _device_from_row(r) if r else None

    async def update_device(self, device_id: int, patch: DevicePatch) -> None:
        await self.pool.execute("""
            UPDATE tracking_devices SET
                vehicle_id      = COALESCE($2, vehicle_id),
                organization_id = COALESCE($3, organization_id),
                is_active       = COALESCE($4, is_active),
                plate           = COALESCE($5, plate)
            WHERE id=$1""",
            device_id, patch.vehicle_id, patch.organization_id, patch.active, patch.plate)

    # --- vehicles ---
    async def list_vehicles(self, org_id: Optional[int]) -> list[Vehicle]:
        rows = await self.pool.fetch("""
            SELECT id, organization_id, fleet_id, registration, vehicle_type, driver_name, created_at
            FROM vehicles WHERE ($1::bigint IS NULL OR organization_id=$1) ORDER BY id""", org_id)
        return [Vehicle(id=r[0], organization_id=r[1], fleet_id=r[2], registration=r[3],
                        vehicle_type=r[4], driver_name=r[5], created_at=r[6]) for r in rows]

    async def get_vehicle(self, vehicle_id: int) -> Optional[Vehicle]:
        r = await self.pool.fetchrow("""
            SELECT id, organization_id, fleet_id, registration, vehicle_type, driver_name, created_at
            FROM vehicles WHERE id=$1""", vehicle_id)
        if not r:
            return None
        return Vehicle(id=r[0], organization_id=r[1], fleet_id=r[2], registration=r[3],
                       vehicle_type=r[4], driver_name=r[5], created_at=r[6])

    async def create_vehicle(self, v: Vehicle) -> int:
        return await self.pool.fetchval("""
            INSERT INTO vehicles (organization_id, fleet_id, registration, vehicle_type, driver_name)
            VALUES ($1,$2,$3,$4,$5) RETURNING id""",
            v.organization_id, v.fleet_id, v.registration, v.vehicle_type, v.driver_name)

    async def update_vehicle(self, v: Vehicle) -> None:
        await self.pool.execute("""
            UPDATE vehicles SET registration=$2, vehicle_type=$3, driver_name=$4, fleet_id=$5
            WHERE id=$1""", v.id, v.registration, v.vehicle_type, v.driver_name, v.fleet_id)

    # --- positions ---
    async def list_positions(self, device_id, frm, to, limit) -> list[Position]:
        limit = limit if 0 < limit <= 50000 else 5000
        rows = await self.pool.fetch("""
            SELECT device_id, reporting_id, device_time, server_time, ST_Y(geom), ST_X(geom),
                   altitude, speed, heading, acc, positioned, valid, satellites, simulated
            FROM gps_positions
            WHERE device_id=$1
              AND ($2::timestamptz IS NULL OR COALESCE(device_time, server_time) >= $2)
              AND ($3::timestamptz IS NULL OR COALESCE(device_time, server_time) <= $3)
            ORDER BY server_time ASC LIMIT $4""", device_id, frm, to, limit)
        return [Position(device_id=r[0], reporting_id=r[1], device_time=r[2], server_time=r[3],
                         latitude=r[4], longitude=r[5], altitude=r[6], speed=r[7], heading=r[8],
                         acc=r[9], positioned=r[10], valid=r[11], satellites=r[12], simulated=r[13])
                for r in rows]

    async def latest_positions(self, org_id, since) -> list[LivePosition]:
        rows = await self.pool.fetch("""
            SELECT DISTINCT ON (gp.device_id)
                   gp.device_id, gp.reporting_id, ST_Y(gp.geom), ST_X(gp.geom),
                   gp.speed, gp.heading, gp.acc, gp.valid, gp.device_time, gp.server_time
            FROM gps_positions gp JOIN tracking_devices d ON d.id=gp.device_id
            WHERE gp.server_time > $1 AND ($2::bigint IS NULL OR d.organization_id=$2)
            ORDER BY gp.device_id, gp.server_time DESC""", since, org_id)
        return [LivePosition(device_id=r[0], reporting_id=r[1], latitude=r[2], longitude=r[3],
                             speed=r[4], heading=r[5], acc=r[6], valid=r[7],
                             device_time=r[8], server_time=r[9]) for r in rows]

    # --- audit ---
    async def save_audit(self, entry: AuditEntry) -> None:
        await self.pool.execute("""
            INSERT INTO audit_logs (user_id, action, entity, entity_id, detail, at)
            VALUES ($1,$2,$3,$4, jsonb_build_object('message', $5::text), COALESCE($6, now()))""",
            entry.user_id, entry.action, entry.entity, entry.entity_id, entry.detail, entry.at)

    # --- Stage 3: positions feed, events, geofences, trips ---

    async def positions_since(self, since, org_id) -> list[Position]:
        rows = await self.pool.fetch("""
            SELECT gp.device_id, gp.reporting_id, gp.device_time, gp.server_time,
                   ST_Y(gp.geom), ST_X(gp.geom), gp.altitude, gp.speed, gp.heading,
                   gp.acc, gp.positioned, gp.valid, gp.satellites, gp.simulated
            FROM gps_positions gp JOIN tracking_devices d ON d.id = gp.device_id
            WHERE gp.server_time > $1 AND ($2::bigint IS NULL OR d.organization_id = $2)
            ORDER BY gp.server_time ASC LIMIT 20000""", since, org_id)
        return [Position(device_id=r[0], reporting_id=r[1], device_time=r[2], server_time=r[3],
                         latitude=r[4], longitude=r[5], altitude=r[6], speed=r[7], heading=r[8],
                         acc=r[9], positioned=r[10], valid=r[11], satellites=r[12], simulated=r[13])
                for r in rows]

    async def save_event(self, e: Event) -> int:
        return await self.pool.fetchval("""
            INSERT INTO events (device_id, reporting_id, type, severity, value, detail, at,
                                latitude, longitude)
            VALUES ($1,$2,$3,$4,$5,$6, COALESCE($7, now()), $8, $9) RETURNING id""",
            e.device_id, e.reporting_id, e.type, e.severity, e.value, e.detail, e.at,
            e.latitude, e.longitude)

    @staticmethod
    def _event_from_row(r) -> Event:
        return Event(id=r[0], device_id=r[1], reporting_id=r[2], type=r[3], severity=r[4],
                     value=r[5], detail=r[6], at=r[7], latitude=r[8], longitude=r[9],
                     acknowledged=r[10], acknowledged_by=r[11], acknowledged_at=r[12],
                     resolved=r[13], resolved_at=r[14])

    _EVENT_COLS = ("e.id, e.device_id, e.reporting_id, e.type, e.severity, e.value, e.detail, "
                   "e.at, e.latitude, e.longitude, e.acknowledged, e.acknowledged_by, "
                   "e.acknowledged_at, e.resolved, e.resolved_at")

    async def list_events(self, org_id, device_id, since, types, limit) -> list[Event]:
        rows = await self.pool.fetch(f"""
            SELECT {self._EVENT_COLS}
            FROM events e
            LEFT JOIN tracking_devices d ON d.id = e.device_id
            WHERE ($1::bigint IS NULL OR d.organization_id = $1)
              AND ($2::bigint IS NULL OR e.device_id = $2)
              AND ($3::timestamptz IS NULL OR e.at > $3)
              AND ($4::text[] IS NULL OR e.type = ANY($4))
            ORDER BY e.at DESC LIMIT $5""",
            org_id, device_id, since, types, limit or 200)
        return [self._event_from_row(r) for r in rows]

    async def get_event(self, eid) -> Optional[Event]:
        r = await self.pool.fetchrow(f"SELECT {self._EVENT_COLS} FROM events e WHERE e.id=$1", eid)
        return self._event_from_row(r) if r else None

    async def ack_event(self, eid, user_id) -> None:
        await self.pool.execute("""
            UPDATE events SET acknowledged=TRUE, acknowledged_by=$2, acknowledged_at=now()
            WHERE id=$1""", eid, user_id)

    async def resolve_event(self, eid) -> None:
        await self.pool.execute(
            "UPDATE events SET resolved=TRUE, resolved_at=now() WHERE id=$1", eid)

    async def list_users(self, org_id) -> list[User]:
        rows = await self.pool.fetch("""
            SELECT u.id, u.organization_id, u.role_id, r.name, u.email, '', u.full_name,
                   u.is_active, u.created_at, u.last_login_at
            FROM users u JOIN roles r ON r.id = u.role_id
            WHERE $1::bigint IS NULL OR u.organization_id = $1
            ORDER BY u.id""", org_id)
        return [User(id=r[0], organization_id=r[1], role_id=r[2], role_name=r[3], email=r[4],
                     password_hash=r[5], full_name=r[6], is_active=r[7], created_at=r[8],
                     last_login_at=r[9]) for r in rows]

    async def list_roles(self) -> list[Role]:
        rows = await self.pool.fetch("SELECT id, name FROM roles ORDER BY id")
        return [Role(id=r[0], name=r[1]) for r in rows]

    async def list_organizations(self) -> list[Organization]:
        rows = await self.pool.fetch("SELECT id, name FROM organizations ORDER BY id")
        return [Organization(id=r[0], name=r[1]) for r in rows]

    async def list_audit(self, org_id, limit) -> list[AuditEntry]:
        rows = await self.pool.fetch("""
            SELECT a.id, a.user_id, a.action, a.entity, a.entity_id,
                   COALESCE(a.detail->>'message',''), a.at
            FROM audit_logs a
            LEFT JOIN users u ON u.id = a.user_id
            WHERE $1::bigint IS NULL OR u.organization_id = $1
            ORDER BY a.at DESC LIMIT $2""", org_id, limit or 200)
        return [AuditEntry(id=r[0], user_id=r[1], action=r[2], entity=r[3], entity_id=r[4],
                           detail=r[5], at=r[6]) for r in rows]

    async def list_raw_packets(self, reporting_id, limit) -> list[RawPacketView]:
        rows = await self.pool.fetch("""
            SELECT id, reporting_id, received_at, length, message_name, decoded, checksum_ok,
                   hex, ascii, note
            FROM raw_packets WHERE reporting_id=$1 ORDER BY received_at DESC LIMIT $2""",
            reporting_id, limit or 100)
        return [RawPacketView(id=r[0], reporting_id=r[1] or "", received_at=r[2], length=r[3],
                              message_name=r[4], decoded=r[5], checksum_ok=r[6], hex=r[7],
                              ascii=r[8], note=r[9]) for r in rows]

    # --- Fleet ops: maintenance, notification rules, notification log ---

    @staticmethod
    def _maint_from_row(r) -> MaintenanceItem:
        return MaintenanceItem(id=r[0], organization_id=r[1], device_id=r[2], title=r[3],
                               kind=r[4], due_date=r[5], due_odometer_km=r[6],
                               odometer_at_create=r[7] or 0.0, status=r[8], completed_at=r[9],
                               notes=r[10] or "", created_at=r[11], device_label=r[12] or "")

    _MAINT_COLS = ("m.id, m.organization_id, m.device_id, m.title, m.kind, m.due_date, "
                   "m.due_odometer_km, m.odometer_at_create, m.status, m.completed_at, m.notes, "
                   "m.created_at, COALESCE(v.registration, d.plate, d.reporting_id, '')")
    _MAINT_FROM = ("FROM maintenance_items m LEFT JOIN tracking_devices d ON d.id=m.device_id "
                   "LEFT JOIN vehicles v ON v.id=d.vehicle_id")

    async def create_maintenance(self, m: MaintenanceItem) -> int:
        return await self.pool.fetchval("""
            INSERT INTO maintenance_items
                (organization_id, device_id, title, kind, due_date, due_odometer_km,
                 odometer_at_create, status, notes)
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9) RETURNING id""",
            m.organization_id, m.device_id, m.title, m.kind, m.due_date, m.due_odometer_km,
            m.odometer_at_create, m.status, m.notes)

    async def list_maintenance(self, org_id, device_id) -> list[MaintenanceItem]:
        rows = await self.pool.fetch(f"""
            SELECT {self._MAINT_COLS} {self._MAINT_FROM}
            WHERE ($1::bigint IS NULL OR m.organization_id=$1)
              AND ($2::bigint IS NULL OR m.device_id=$2)
            ORDER BY (m.status='open') DESC, m.due_date NULLS LAST""", org_id, device_id)
        return [self._maint_from_row(r) for r in rows]

    async def get_maintenance(self, mid) -> Optional[MaintenanceItem]:
        r = await self.pool.fetchrow(f"SELECT {self._MAINT_COLS} {self._MAINT_FROM} WHERE m.id=$1", mid)
        return self._maint_from_row(r) if r else None

    async def update_maintenance(self, m: MaintenanceItem) -> None:
        await self.pool.execute("""
            UPDATE maintenance_items SET title=$2, kind=$3, due_date=$4, due_odometer_km=$5,
                status=$6, completed_at=$7, notes=$8 WHERE id=$1""",
            m.id, m.title, m.kind, m.due_date, m.due_odometer_km, m.status, m.completed_at, m.notes)

    async def delete_maintenance(self, mid) -> None:
        await self.pool.execute("DELETE FROM maintenance_items WHERE id=$1", mid)

    @staticmethod
    def _rule_from_row(r) -> NotificationRule:
        return NotificationRule(id=r[0], organization_id=r[1], name=r[2],
                                event_types=list(r[3] or []), min_severity=r[4], channel=r[5],
                                target=r[6], active=r[7], created_at=r[8])

    async def create_rule(self, r: NotificationRule) -> int:
        return await self.pool.fetchval("""
            INSERT INTO notification_rules (organization_id, name, event_types, min_severity, channel, target, active)
            VALUES ($1,$2,$3,$4,$5,$6,$7) RETURNING id""",
            r.organization_id, r.name, r.event_types or None, r.min_severity, r.channel, r.target, r.active)

    async def list_rules(self, org_id) -> list[NotificationRule]:
        rows = await self.pool.fetch("""
            SELECT id, organization_id, name, event_types, min_severity, channel, target, active, created_at
            FROM notification_rules WHERE $1::bigint IS NULL OR organization_id=$1 OR organization_id IS NULL
            ORDER BY id""", org_id)
        return [self._rule_from_row(r) for r in rows]

    async def all_active_rules(self) -> list[NotificationRule]:
        rows = await self.pool.fetch("""
            SELECT id, organization_id, name, event_types, min_severity, channel, target, active, created_at
            FROM notification_rules WHERE active = TRUE""")
        return [self._rule_from_row(r) for r in rows]

    async def get_rule(self, rid) -> Optional[NotificationRule]:
        r = await self.pool.fetchrow("""
            SELECT id, organization_id, name, event_types, min_severity, channel, target, active, created_at
            FROM notification_rules WHERE id=$1""", rid)
        return self._rule_from_row(r) if r else None

    async def update_rule(self, r: NotificationRule) -> None:
        await self.pool.execute("""
            UPDATE notification_rules SET name=$2, event_types=$3, min_severity=$4, channel=$5,
                target=$6, active=$7 WHERE id=$1""",
            r.id, r.name, r.event_types or None, r.min_severity, r.channel, r.target, r.active)

    async def delete_rule(self, rid) -> None:
        await self.pool.execute("DELETE FROM notification_rules WHERE id=$1", rid)

    async def save_notification(self, e: NotificationLogEntry) -> None:
        await self.pool.execute("""
            INSERT INTO notification_log (rule_id, event_id, event_type, channel, target, status, detail)
            VALUES ($1,$2,$3,$4,$5,$6,$7)""",
            e.rule_id, e.event_id, e.event_type, e.channel, e.target, e.status, e.detail)

    async def list_notifications(self, org_id, limit) -> list[NotificationLogEntry]:
        rows = await self.pool.fetch("""
            SELECT n.id, n.rule_id, n.event_id, n.event_type, n.channel, n.target, n.status, n.detail, n.at
            FROM notification_log n LEFT JOIN notification_rules r ON r.id=n.rule_id
            WHERE $1::bigint IS NULL OR r.organization_id=$1 OR r.organization_id IS NULL
            ORDER BY n.at DESC LIMIT $2""", org_id, limit or 200)
        return [NotificationLogEntry(id=r[0], rule_id=r[1], event_id=r[2], event_type=r[3],
                                     channel=r[4], target=r[5], status=r[6], detail=r[7], at=r[8])
                for r in rows]

    async def create_geofence(self, g: Geofence) -> int:
        ring = list(g.ring)
        if ring and ring[0] != ring[-1]:
            ring = ring + [ring[0]]
        wkt = "POLYGON((" + ",".join(f"{lon} {lat}" for (lat, lon) in ring) + "))"
        return await self.pool.fetchval("""
            INSERT INTO geofences (organization_id, name, area)
            VALUES ($1,$2, ST_GeomFromText($3,4326)) RETURNING id""",
            g.organization_id, g.name, wkt)

    @staticmethod
    def _ring_from_geojson(gj: str):
        coords = json.loads(gj)["coordinates"][0]
        return [(lat, lon) for lon, lat in coords]

    async def list_geofences(self, org_id) -> list[Geofence]:
        rows = await self.pool.fetch("""
            SELECT id, organization_id, name, ST_AsGeoJSON(area)
            FROM geofences WHERE $1::bigint IS NULL OR organization_id = $1 OR organization_id IS NULL""",
            org_id)
        return [Geofence(id=r[0], organization_id=r[1], name=r[2],
                         ring=self._ring_from_geojson(r[3])) for r in rows]

    async def get_geofence(self, gid) -> Optional[Geofence]:
        r = await self.pool.fetchrow("""
            SELECT id, organization_id, name, ST_AsGeoJSON(area) FROM geofences WHERE id=$1""", gid)
        if not r:
            return None
        return Geofence(id=r[0], organization_id=r[1], name=r[2], ring=self._ring_from_geojson(r[3]))

    async def delete_geofence(self, gid) -> None:
        await self.pool.execute("DELETE FROM geofences WHERE id=$1", gid)

    async def save_trip(self, t: Trip) -> int:
        line = None
        if len(t.path) >= 2:
            line = "LINESTRING(" + ",".join(f"{lon} {lat}" for (lat, lon) in t.path) + ")"
        return await self.pool.fetchval("""
            INSERT INTO trips (device_id, started_at, ended_at, distance_km, max_speed, path)
            VALUES ($1,$2,$3,$4,$5, CASE WHEN $6::text IS NULL THEN NULL
                                         ELSE ST_GeomFromText($6,4326) END)
            RETURNING id""",
            t.device_id, t.started_at, t.ended_at, t.distance_km, t.max_speed, line)

    @staticmethod
    def _path_from_geojson(gj: Optional[str]):
        if not gj:
            return []
        return [(lat, lon) for lon, lat in json.loads(gj)["coordinates"]]

    async def list_trips(self, device_id, limit) -> list[Trip]:
        rows = await self.pool.fetch("""
            SELECT id, device_id, started_at, ended_at, distance_km, max_speed, ST_AsGeoJSON(path)
            FROM trips WHERE device_id=$1 ORDER BY started_at DESC LIMIT $2""",
            device_id, limit or 100)
        return [Trip(id=r[0], device_id=r[1], reporting_id="", started_at=r[2], ended_at=r[3],
                     distance_km=r[4], max_speed=r[5], path=self._path_from_geojson(r[6]))
                for r in rows]

    async def get_trip(self, tid) -> Optional[Trip]:
        r = await self.pool.fetchrow("""
            SELECT id, device_id, started_at, ended_at, distance_km, max_speed, ST_AsGeoJSON(path)
            FROM trips WHERE id=$1""", tid)
        if not r:
            return None
        return Trip(id=r[0], device_id=r[1], reporting_id="", started_at=r[2], ended_at=r[3],
                    distance_km=r[4], max_speed=r[5], path=self._path_from_geojson(r[6]))

    # --- Stage 4: video ---

    async def list_camera_channels(self, device_id) -> list[CameraChannel]:
        rows = await self.pool.fetch("""
            SELECT device_id, channel_no, name, enabled FROM camera_channels
            WHERE device_id=$1 ORDER BY channel_no""", device_id)
        if rows:
            return [CameraChannel(device_id=r[0], channel_no=r[1], name=r[2], enabled=r[3]) for r in rows]
        # Default to the XV-900-8's 8 channels until the device reports otherwise.
        return [CameraChannel(device_id=device_id, channel_no=i, name=f"CH{i}") for i in range(1, 9)]

    async def create_video_session(self, v: VideoSession) -> int:
        return await self.pool.fetchval("""
            INSERT INTO video_sessions (device_id, channel_no, kind, started_at, status)
            VALUES ($1,$2,$3, COALESCE($4, now()), $5) RETURNING id""",
            v.device_id, v.channel, v.kind, v.started_at, v.status)

    async def list_video_sessions(self, org_id, device_id, limit) -> list[VideoSession]:
        rows = await self.pool.fetch("""
            SELECT vs.id, vs.device_id, vs.channel_no, vs.kind, vs.status, vs.started_at, vs.ended_at,
                   COALESCE(d.reporting_id,'')
            FROM video_sessions vs
            LEFT JOIN tracking_devices d ON d.id = vs.device_id
            WHERE ($1::bigint IS NULL OR d.organization_id=$1)
              AND ($2::bigint IS NULL OR vs.device_id=$2)
            ORDER BY vs.started_at DESC LIMIT $3""", org_id, device_id, limit or 100)
        return [VideoSession(id=r[0], device_id=r[1], channel=r[2], kind=r[3], status=r[4],
                             started_at=r[5], ended_at=r[6], reporting_id=r[7]) for r in rows]

    async def get_video_session(self, sid) -> Optional[VideoSession]:
        r = await self.pool.fetchrow("""
            SELECT vs.id, vs.device_id, vs.channel_no, vs.kind, vs.status, vs.started_at, vs.ended_at,
                   COALESCE(d.reporting_id,'')
            FROM video_sessions vs LEFT JOIN tracking_devices d ON d.id = vs.device_id
            WHERE vs.id=$1""", sid)
        if not r:
            return None
        return VideoSession(id=r[0], device_id=r[1], channel=r[2], kind=r[3], status=r[4],
                            started_at=r[5], ended_at=r[6], reporting_id=r[7])

    async def end_video_session(self, sid, status) -> None:
        await self.pool.execute(
            "UPDATE video_sessions SET status=$2, ended_at=now() WHERE id=$1", sid, status)
