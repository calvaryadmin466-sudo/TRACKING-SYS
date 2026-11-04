-- Fleet ops: maintenance reminders + notification rules + notification log.
BEGIN;

CREATE TABLE IF NOT EXISTS maintenance_items (
    id                  BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    organization_id     BIGINT REFERENCES organizations(id) ON DELETE CASCADE,
    device_id           BIGINT REFERENCES tracking_devices(id) ON DELETE CASCADE,
    title               TEXT NOT NULL,
    kind                TEXT NOT NULL DEFAULT 'service',  -- service|inspection|insurance|license|other
    due_date            TIMESTAMPTZ,
    due_odometer_km     DOUBLE PRECISION,
    odometer_at_create  DOUBLE PRECISION NOT NULL DEFAULT 0,
    status              TEXT NOT NULL DEFAULT 'open',      -- open|done
    completed_at        TIMESTAMPTZ,
    notes               TEXT NOT NULL DEFAULT '',
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_maint_device ON maintenance_items(device_id);
CREATE INDEX IF NOT EXISTS idx_maint_status ON maintenance_items(status);

CREATE TABLE IF NOT EXISTS notification_rules (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    organization_id BIGINT REFERENCES organizations(id) ON DELETE CASCADE,
    name            TEXT NOT NULL,
    event_types     TEXT[],                               -- null/empty = any type
    min_severity    TEXT NOT NULL DEFAULT 'warning',      -- info|warning|alarm
    channel         TEXT NOT NULL DEFAULT 'webhook',      -- webhook (email needs SMTP env)
    target          TEXT NOT NULL DEFAULT '',             -- webhook URL / email address
    active          BOOLEAN NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_rules_org ON notification_rules(organization_id);

CREATE TABLE IF NOT EXISTS notification_log (
    id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    rule_id     BIGINT REFERENCES notification_rules(id) ON DELETE SET NULL,
    event_id    BIGINT,
    event_type  TEXT NOT NULL DEFAULT '',
    channel     TEXT NOT NULL DEFAULT '',
    target      TEXT NOT NULL DEFAULT '',
    status      TEXT NOT NULL DEFAULT '',                 -- delivered|failed
    detail      TEXT NOT NULL DEFAULT '',
    at          TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_notiflog_at ON notification_log USING brin(at);

COMMIT;
