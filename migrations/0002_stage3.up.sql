-- Stage 3: event engine needs severity and a numeric value on events.
BEGIN;

ALTER TABLE events ADD COLUMN IF NOT EXISTS severity TEXT NOT NULL DEFAULT 'info';
ALTER TABLE events ADD COLUMN IF NOT EXISTS value DOUBLE PRECISION;

CREATE INDEX IF NOT EXISTS idx_events_type_at ON events(type, at DESC);
CREATE INDEX IF NOT EXISTS idx_events_severity ON events(severity) WHERE severity <> 'info';

COMMIT;
