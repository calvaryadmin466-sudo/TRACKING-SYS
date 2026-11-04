package store

import (
	"context"
	"errors"
	"fmt"
	"time"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"
)

// PostgresStore is the production Store backed by PostgreSQL + PostGIS.
type PostgresStore struct {
	pool *pgxpool.Pool
}

// NewPostgresStore connects to the database at url (a postgres:// DSN) and
// verifies connectivity. The schema is created by the migrations in /migrations.
func NewPostgresStore(ctx context.Context, url string) (*PostgresStore, error) {
	pool, err := pgxpool.New(ctx, url)
	if err != nil {
		return nil, fmt.Errorf("store: connect: %w", err)
	}
	pingCtx, cancel := context.WithTimeout(ctx, 5*time.Second)
	defer cancel()
	if err := pool.Ping(pingCtx); err != nil {
		pool.Close()
		return nil, fmt.Errorf("store: ping: %w", err)
	}
	return &PostgresStore{pool: pool}, nil
}

func (s *PostgresStore) Close() error {
	s.pool.Close()
	return nil
}

func (s *PostgresStore) UpsertDevice(ctx context.Context, d Device) (int64, error) {
	const q = `
INSERT INTO tracking_devices
    (reporting_id, serial_number, model, manufacturer, plate, protocol, simulated, first_seen, last_seen, auth_code)
VALUES ($1,$2,$3,$4,$5,$6,$7, COALESCE($8, now()), $9, $10)
ON CONFLICT (reporting_id) DO UPDATE SET
    serial_number = COALESCE(NULLIF(EXCLUDED.serial_number,''), tracking_devices.serial_number),
    model         = COALESCE(NULLIF(EXCLUDED.model,''), tracking_devices.model),
    manufacturer  = COALESCE(NULLIF(EXCLUDED.manufacturer,''), tracking_devices.manufacturer),
    plate         = COALESCE(NULLIF(EXCLUDED.plate,''), tracking_devices.plate),
    protocol      = COALESCE(NULLIF(EXCLUDED.protocol,''), tracking_devices.protocol),
    last_seen     = EXCLUDED.last_seen,
    auth_code     = COALESCE(NULLIF(EXCLUDED.auth_code,''), tracking_devices.auth_code)
RETURNING id`
	var firstSeen *time.Time
	if !d.FirstSeen.IsZero() {
		firstSeen = &d.FirstSeen
	}
	var id int64
	err := s.pool.QueryRow(ctx, q,
		d.ReportingID, d.SerialNumber, d.Model, d.Manufacturer, d.Plate,
		d.Protocol, d.Simulated, firstSeen, d.LastSeen, d.AuthCode,
	).Scan(&id)
	if err != nil {
		return 0, fmt.Errorf("store: upsert device: %w", err)
	}
	return id, nil
}

func (s *PostgresStore) GetDeviceByReportingID(ctx context.Context, reportingID string) (Device, bool, error) {
	const q = `
SELECT id, reporting_id, serial_number, model, manufacturer, plate, protocol, simulated,
       first_seen, last_seen, auth_code
FROM tracking_devices WHERE reporting_id = $1`
	var d Device
	err := s.pool.QueryRow(ctx, q, reportingID).Scan(
		&d.ID, &d.ReportingID, &d.SerialNumber, &d.Model, &d.Manufacturer, &d.Plate,
		&d.Protocol, &d.Simulated, &d.FirstSeen, &d.LastSeen, &d.AuthCode,
	)
	if err != nil {
		// No rows is a normal "not found"; callers treat ok=false.
		if errors.Is(err, pgx.ErrNoRows) {
			return Device{}, false, nil
		}
		return Device{}, false, fmt.Errorf("store: get device: %w", err)
	}
	return d, true, nil
}

func (s *PostgresStore) TouchDevice(ctx context.Context, reportingID string, at time.Time) error {
	_, err := s.pool.Exec(ctx,
		`UPDATE tracking_devices SET last_seen = $2 WHERE reporting_id = $1`, reportingID, at)
	return err
}

func (s *PostgresStore) SaveConnectionEvent(ctx context.Context, e ConnectionEvent) error {
	_, err := s.pool.Exec(ctx, `
INSERT INTO device_connections (conn_id, remote_addr, reporting_id, event, reason, at)
VALUES ($1,$2,NULLIF($3,''),$4,$5,$6)`,
		e.ConnID, e.RemoteAddr, e.ReportingID, e.Event, e.Reason, e.At)
	return err
}

func (s *PostgresStore) SaveRawPacket(ctx context.Context, p RawPacket) error {
	var msgID *int32
	if p.MessageID != nil {
		v := int32(*p.MessageID)
		msgID = &v
	}
	_, err := s.pool.Exec(ctx, `
INSERT INTO raw_packets
    (conn_id, remote_addr, reporting_id, received_at, length, hex, ascii, message_id, message_name, decoded, checksum_ok, note)
VALUES ($1,$2,NULLIF($3,''),$4,$5,$6,$7,$8,$9,$10,$11,$12)`,
		p.ConnID, p.RemoteAddr, p.ReportingID, p.ReceivedAt, p.Length, p.Hex, p.ASCII,
		msgID, p.MessageName, p.Decoded, p.ChecksumOK, p.Note)
	return err
}

func (s *PostgresStore) SavePosition(ctx context.Context, p Position) error {
	_, err := s.pool.Exec(ctx, `
INSERT INTO gps_positions
    (device_id, reporting_id, device_time, server_time, geom, altitude, speed, heading,
     acc, positioned, valid, alarm_flag, status_flag, satellites, mileage_km, simulated, raw_hex)
VALUES ($1,$2,$3,$4, ST_SetSRID(ST_MakePoint($5,$6),4326), $7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18)`,
		p.DeviceID, p.ReportingID, p.DeviceTime, p.ServerTime,
		p.Longitude, p.Latitude, p.Altitude, p.Speed, p.Heading,
		p.ACC, p.Positioned, p.Valid, int64(p.AlarmFlag), int64(p.StatusFlag),
		p.Satellites, p.MileageKM, p.Simulated, p.RawHex)
	return err
}

func (s *PostgresStore) SaveEvent(ctx context.Context, e Event) error {
	_, err := s.pool.Exec(ctx, `
INSERT INTO events (device_id, reporting_id, type, at, detail, simulated)
VALUES (NULLIF($1,0)::bigint, NULLIF($2,''), $3, $4, $5, $6)`,
		e.DeviceID, e.ReportingID, e.Type, e.At, e.Detail, e.Simulated)
	return err
}
