-- Driver management and vehicle assignment.
BEGIN;

CREATE TABLE IF NOT EXISTS drivers (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    organization_id BIGINT REFERENCES organizations(id) ON DELETE CASCADE,
    name            TEXT NOT NULL,
    license_number  TEXT NOT NULL DEFAULT '',
    license_class   TEXT NOT NULL DEFAULT '',
    phone           TEXT NOT NULL DEFAULT '',
    employee_id     TEXT NOT NULL DEFAULT '',
    license_expiry  DATE,
    status          TEXT NOT NULL DEFAULT 'active',
    notes           TEXT NOT NULL DEFAULT '',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_drivers_org ON drivers(organization_id);

ALTER TABLE vehicles ADD COLUMN IF NOT EXISTS driver_id BIGINT REFERENCES drivers(id) ON DELETE SET NULL;

COMMIT;
