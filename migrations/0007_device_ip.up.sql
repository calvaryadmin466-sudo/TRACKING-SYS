-- Device provisioning: record the MDVR decoder's IP address so an admin can
-- pre-register a unit (plate number + device ID + decoder IP) in the platform
-- before it dials in over JT/T 808. The ingestion upsert never clears it.
ALTER TABLE tracking_devices ADD COLUMN IF NOT EXISTS ip_address TEXT NOT NULL DEFAULT '';
