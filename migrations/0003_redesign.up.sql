-- Redesign: event acknowledgement/resolution + event location.
BEGIN;

ALTER TABLE events ADD COLUMN IF NOT EXISTS acknowledged     BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE events ADD COLUMN IF NOT EXISTS acknowledged_by  BIGINT REFERENCES users(id) ON DELETE SET NULL;
ALTER TABLE events ADD COLUMN IF NOT EXISTS acknowledged_at  TIMESTAMPTZ;
ALTER TABLE events ADD COLUMN IF NOT EXISTS resolved         BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE events ADD COLUMN IF NOT EXISTS resolved_at      TIMESTAMPTZ;
ALTER TABLE events ADD COLUMN IF NOT EXISTS latitude         DOUBLE PRECISION;
ALTER TABLE events ADD COLUMN IF NOT EXISTS longitude        DOUBLE PRECISION;

-- Fast lookup of open (unacknowledged) alarms/warnings.
CREATE INDEX IF NOT EXISTS idx_events_open
    ON events(at DESC) WHERE acknowledged = FALSE AND severity <> 'info';

COMMIT;
