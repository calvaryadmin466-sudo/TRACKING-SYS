-- Tracking platform core schema (Stage 1).
-- PostgreSQL + PostGIS. Timestamps are stored in UTC (timestamptz).
-- Device reporting ID, hardware serial number and internal DB id are kept
-- strictly separate and are never assumed interchangeable.

BEGIN;

CREATE EXTENSION IF NOT EXISTS postgis;

-- ---------------------------------------------------------------------------
-- Tenancy, people and access control
-- ---------------------------------------------------------------------------
CREATE TABLE organizations (
    id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name        TEXT NOT NULL,
    slug        TEXT NOT NULL UNIQUE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE roles (
    id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name        TEXT NOT NULL UNIQUE,     -- super_admin, company_admin, fleet_manager, dispatcher, operator, readonly
    description TEXT NOT NULL DEFAULT ''
);

INSERT INTO roles (name, description) VALUES
    ('super_admin',    'Platform-wide administrator'),
    ('company_admin',  'Administrator for a single organization'),
    ('fleet_manager',  'Manages fleets within an organization'),
    ('dispatcher',     'Operational dispatch user'),
    ('operator',       'Monitoring operator'),
    ('readonly',       'Read-only user');

CREATE TABLE users (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    organization_id BIGINT REFERENCES organizations(id) ON DELETE CASCADE,
    role_id         BIGINT NOT NULL REFERENCES roles(id),
    email           TEXT NOT NULL UNIQUE,
    password_hash   TEXT NOT NULL,        -- argon2id/bcrypt hash, never plaintext
    full_name       TEXT NOT NULL DEFAULT '',
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_login_at   TIMESTAMPTZ
);
CREATE INDEX idx_users_org ON users(organization_id);

-- ---------------------------------------------------------------------------
-- Fleets and vehicles
-- ---------------------------------------------------------------------------
CREATE TABLE fleets (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    organization_id BIGINT NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    name            TEXT NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_fleets_org ON fleets(organization_id);

CREATE TABLE vehicles (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    organization_id BIGINT REFERENCES organizations(id) ON DELETE CASCADE,
    fleet_id        BIGINT REFERENCES fleets(id) ON DELETE SET NULL,
    registration    TEXT NOT NULL,        -- license plate / registration number
    vehicle_type    TEXT NOT NULL DEFAULT '',
    driver_name     TEXT NOT NULL DEFAULT '',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_vehicles_org ON vehicles(organization_id);
CREATE INDEX idx_vehicles_fleet ON vehicles(fleet_id);

-- ---------------------------------------------------------------------------
-- Protocols and devices
-- ---------------------------------------------------------------------------
CREATE TABLE device_protocols (
    id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name        TEXT NOT NULL UNIQUE,     -- e.g. JT808, JT1078
    version     TEXT NOT NULL DEFAULT '',
    description TEXT NOT NULL DEFAULT ''
);
INSERT INTO device_protocols (name, version, description) VALUES
    ('JT808', '2013/2019', 'JT/T 808 vehicle terminal signalling / GPS protocol'),
    ('JT1078','2016',      'JT/T 1078 video transmission protocol (media gateway, future stage)');

CREATE TABLE tracking_devices (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    organization_id BIGINT REFERENCES organizations(id) ON DELETE SET NULL,
    vehicle_id      BIGINT REFERENCES vehicles(id) ON DELETE SET NULL,
    reporting_id    TEXT NOT NULL UNIQUE,     -- JT808 "phone number" / unique reporting ID
    serial_number   TEXT NOT NULL DEFAULT '', -- hardware serial / terminal ID (distinct!)
    model           TEXT NOT NULL DEFAULT '',
    manufacturer    TEXT NOT NULL DEFAULT '',
    firmware        TEXT NOT NULL DEFAULT '',
    plate           TEXT NOT NULL DEFAULT '',
    protocol        TEXT NOT NULL DEFAULT 'JT808',
    sim_number      TEXT NOT NULL DEFAULT '',
    simulated       BOOLEAN NOT NULL DEFAULT FALSE,  -- clearly separates simulator devices
    auth_code       TEXT NOT NULL DEFAULT '',
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    first_seen      TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_seen       TIMESTAMPTZ NOT NULL DEFAULT now(),
    config          JSONB NOT NULL DEFAULT '{}'::jsonb
);
CREATE INDEX idx_devices_vehicle ON tracking_devices(vehicle_id);
CREATE INDEX idx_devices_org ON tracking_devices(organization_id);
CREATE INDEX idx_devices_simulated ON tracking_devices(simulated);

-- ---------------------------------------------------------------------------
-- Connection lifecycle and raw packet diagnostics
-- ---------------------------------------------------------------------------
CREATE TABLE device_connections (
    id           BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    conn_id      TEXT NOT NULL,
    remote_addr  TEXT NOT NULL,
    reporting_id TEXT,
    event        TEXT NOT NULL,           -- connected | disconnected
    reason       TEXT NOT NULL DEFAULT '',
    at           TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_connections_reporting ON device_connections(reporting_id);
CREATE INDEX idx_connections_at ON device_connections USING brin(at);

-- Every received frame is recorded here, decoded or not. Unidentified packets
-- are never silently discarded; they are stored with decoded = FALSE.
CREATE TABLE raw_packets (
    id           BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    conn_id      TEXT NOT NULL,
    remote_addr  TEXT NOT NULL,
    reporting_id TEXT,
    received_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    length       INTEGER NOT NULL,
    hex          TEXT NOT NULL,
    ascii        TEXT NOT NULL DEFAULT '',
    message_id   INTEGER,
    message_name TEXT NOT NULL DEFAULT '',
    decoded      BOOLEAN NOT NULL DEFAULT FALSE,
    checksum_ok  BOOLEAN NOT NULL DEFAULT FALSE,
    note         TEXT NOT NULL DEFAULT ''
);
CREATE INDEX idx_rawpackets_reporting ON raw_packets(reporting_id);
CREATE INDEX idx_rawpackets_received ON raw_packets USING brin(received_at);
CREATE INDEX idx_rawpackets_undecoded ON raw_packets(decoded) WHERE decoded = FALSE;

-- ---------------------------------------------------------------------------
-- GPS positions (high-volume) and trips
-- ---------------------------------------------------------------------------
CREATE TABLE gps_positions (
    id           BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    device_id    BIGINT REFERENCES tracking_devices(id) ON DELETE SET NULL,
    reporting_id TEXT NOT NULL,
    device_time  TIMESTAMPTZ,             -- terminal-reported wall clock (preserved)
    server_time  TIMESTAMPTZ NOT NULL DEFAULT now(),  -- server reception time
    geom         geometry(Point, 4326) NOT NULL,
    altitude     INTEGER NOT NULL DEFAULT 0,
    speed        DOUBLE PRECISION NOT NULL DEFAULT 0,  -- km/h
    heading      INTEGER NOT NULL DEFAULT 0,
    acc          BOOLEAN NOT NULL DEFAULT FALSE,       -- ignition
    positioned   BOOLEAN NOT NULL DEFAULT FALSE,
    valid        BOOLEAN NOT NULL DEFAULT FALSE,       -- fresh vs stale/invalid fix
    alarm_flag   BIGINT NOT NULL DEFAULT 0,
    status_flag  BIGINT NOT NULL DEFAULT 0,
    satellites   INTEGER NOT NULL DEFAULT 0,
    mileage_km   DOUBLE PRECISION NOT NULL DEFAULT 0,
    simulated    BOOLEAN NOT NULL DEFAULT FALSE,
    raw_hex      TEXT NOT NULL DEFAULT ''
);
CREATE INDEX idx_positions_device_time ON gps_positions(device_id, device_time DESC);
CREATE INDEX idx_positions_reporting_time ON gps_positions(reporting_id, server_time DESC);
CREATE INDEX idx_positions_server_time ON gps_positions USING brin(server_time);
CREATE INDEX idx_positions_geom ON gps_positions USING gist(geom);

CREATE TABLE trips (
    id             BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    device_id      BIGINT REFERENCES tracking_devices(id) ON DELETE SET NULL,
    vehicle_id     BIGINT REFERENCES vehicles(id) ON DELETE SET NULL,
    started_at     TIMESTAMPTZ NOT NULL,
    ended_at       TIMESTAMPTZ,
    distance_km    DOUBLE PRECISION NOT NULL DEFAULT 0,
    max_speed      DOUBLE PRECISION NOT NULL DEFAULT 0,
    path           geometry(LineString, 4326),
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_trips_device ON trips(device_id, started_at DESC);

-- ---------------------------------------------------------------------------
-- Geofences, alarms and events
-- ---------------------------------------------------------------------------
CREATE TABLE geofences (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    organization_id BIGINT REFERENCES organizations(id) ON DELETE CASCADE,
    name            TEXT NOT NULL,
    area            geometry(Polygon, 4326) NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_geofences_area ON geofences USING gist(area);

CREATE TABLE alarms (
    id           BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    device_id    BIGINT REFERENCES tracking_devices(id) ON DELETE SET NULL,
    reporting_id TEXT NOT NULL,
    type         TEXT NOT NULL,           -- overspeed, acceleration, voltage, temperature, io, video_loss, ...
    severity     TEXT NOT NULL DEFAULT 'info',
    at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    geom         geometry(Point, 4326),
    detail       JSONB NOT NULL DEFAULT '{}'::jsonb,
    simulated    BOOLEAN NOT NULL DEFAULT FALSE
);
CREATE INDEX idx_alarms_device_at ON alarms(device_id, at DESC);

CREATE TABLE events (
    id           BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    device_id    BIGINT REFERENCES tracking_devices(id) ON DELETE SET NULL,
    reporting_id TEXT,
    type         TEXT NOT NULL,           -- register, auth, offline, ignition_on, ...
    at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    detail       TEXT NOT NULL DEFAULT '',
    simulated    BOOLEAN NOT NULL DEFAULT FALSE
);
CREATE INDEX idx_events_device_at ON events(device_id, at DESC);
CREATE INDEX idx_events_reporting ON events(reporting_id);

-- ---------------------------------------------------------------------------
-- Video (metadata only in Stage 1; media gateway is a future service)
-- ---------------------------------------------------------------------------
CREATE TABLE camera_channels (
    id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    device_id   BIGINT NOT NULL REFERENCES tracking_devices(id) ON DELETE CASCADE,
    channel_no  INTEGER NOT NULL,
    name        TEXT NOT NULL DEFAULT '',
    enabled     BOOLEAN NOT NULL DEFAULT TRUE,
    UNIQUE (device_id, channel_no)
);

CREATE TABLE video_sessions (
    id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    device_id   BIGINT NOT NULL REFERENCES tracking_devices(id) ON DELETE CASCADE,
    channel_no  INTEGER NOT NULL,
    kind        TEXT NOT NULL DEFAULT 'live',   -- live | playback
    started_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    ended_at    TIMESTAMPTZ,
    status      TEXT NOT NULL DEFAULT 'pending'
);
CREATE INDEX idx_video_sessions_device ON video_sessions(device_id, started_at DESC);

-- ---------------------------------------------------------------------------
-- Audit log for sensitive administrative operations
-- ---------------------------------------------------------------------------
CREATE TABLE audit_logs (
    id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id     BIGINT REFERENCES users(id) ON DELETE SET NULL,
    action      TEXT NOT NULL,
    entity      TEXT NOT NULL,
    entity_id   TEXT NOT NULL DEFAULT '',
    detail      JSONB NOT NULL DEFAULT '{}'::jsonb,
    at          TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_audit_at ON audit_logs USING brin(at);

COMMIT;
