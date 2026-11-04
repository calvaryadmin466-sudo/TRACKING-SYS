-- Device text message distribution (JT/T 808 0x8300).
BEGIN;

CREATE TABLE IF NOT EXISTS device_messages (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    organization_id BIGINT REFERENCES organizations(id) ON DELETE CASCADE,
    device_id       BIGINT REFERENCES tracking_devices(id) ON DELETE CASCADE,
    user_id         BIGINT REFERENCES users(id) ON DELETE SET NULL,
    flag            INT NOT NULL DEFAULT 12,
    text            TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'sent',  -- sent|failed|delivered
    detail          TEXT NOT NULL DEFAULT '',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_devmsg_device ON device_messages(device_id);
CREATE INDEX IF NOT EXISTS idx_devmsg_org ON device_messages(organization_id);
CREATE INDEX IF NOT EXISTS idx_devmsg_created ON device_messages(created_at DESC);

COMMIT;
