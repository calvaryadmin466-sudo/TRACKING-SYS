-- Reverse of 0001_init.up.sql. Drops all Stage 1 objects.
BEGIN;

DROP TABLE IF EXISTS audit_logs;
DROP TABLE IF EXISTS video_sessions;
DROP TABLE IF EXISTS camera_channels;
DROP TABLE IF EXISTS events;
DROP TABLE IF EXISTS alarms;
DROP TABLE IF EXISTS geofences;
DROP TABLE IF EXISTS trips;
DROP TABLE IF EXISTS gps_positions;
DROP TABLE IF EXISTS raw_packets;
DROP TABLE IF EXISTS device_connections;
DROP TABLE IF EXISTS tracking_devices;
DROP TABLE IF EXISTS device_protocols;
DROP TABLE IF EXISTS vehicles;
DROP TABLE IF EXISTS fleets;
DROP TABLE IF EXISTS users;
DROP TABLE IF EXISTS roles;
DROP TABLE IF EXISTS organizations;

COMMIT;
