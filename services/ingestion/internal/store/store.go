// Package store defines the persistence boundary for the ingestion server and
// provides an in-memory implementation (for tests and the simulator) plus a
// PostgreSQL/PostGIS implementation (for production).
package store

import (
	"context"
	"time"
)

// Device is a tracking device as stored in the registry. The three identifiers
// are kept strictly separate and are never assumed interchangeable:
//   - ReportingID: the JT/T 808 "phone number" the terminal reports with.
//   - SerialNumber: the hardware serial / terminal ID (from registration).
//   - ID: the internal database primary key.
type Device struct {
	ID           int64
	ReportingID  string
	SerialNumber string
	Model        string
	Manufacturer string
	Plate        string
	Protocol     string
	Simulated    bool
	FirstSeen    time.Time
	LastSeen     time.Time
	AuthCode     string
}

// ConnectionEvent records a TCP connection lifecycle event for diagnostics.
type ConnectionEvent struct {
	ConnID      string
	RemoteAddr  string
	ReportingID string
	Event       string // "connected" | "disconnected"
	Reason      string
	At          time.Time
}

// RawPacket is a diagnostic record of received bytes. Decoded distinguishes
// successfully recognised messages from unidentified traffic; unknown packets
// are stored, never silently discarded.
type RawPacket struct {
	ConnID      string
	RemoteAddr  string
	ReportingID string
	ReceivedAt  time.Time
	Length      int
	Hex         string
	ASCII       string
	MessageID   *uint16
	MessageName string
	Decoded     bool
	ChecksumOK  bool
	Note        string
}

// Position is a decoded GPS position ready for persistence.
type Position struct {
	DeviceID    int64
	ReportingID string
	DeviceTime  time.Time // terminal-reported wall clock
	ServerTime  time.Time // server reception time (UTC)
	Latitude    float64
	Longitude   float64
	Altitude    int
	Speed       float64
	Heading     int
	ACC         bool
	Positioned  bool
	Valid       bool
	AlarmFlag   uint32
	StatusFlag  uint32
	Satellites  int
	MileageKM   float64
	Simulated   bool
	RawHex      string
}

// Event is an operational/alarm event derived from a message.
type Event struct {
	DeviceID    int64
	ReportingID string
	Type        string
	Severity    string // info | warning | alarm
	At          time.Time
	Detail      string
	Latitude    float64
	Longitude   float64
	HasLocation bool
	Simulated   bool
}

// Store is the persistence interface used by the ingestion server.
type Store interface {
	// UpsertDevice registers or updates a device by its reporting ID and returns
	// the internal database ID.
	UpsertDevice(ctx context.Context, d Device) (int64, error)
	// GetDeviceByReportingID returns a device by reporting ID, or ok=false.
	GetDeviceByReportingID(ctx context.Context, reportingID string) (Device, bool, error)
	// TouchDevice updates the last-seen time for a reporting ID.
	TouchDevice(ctx context.Context, reportingID string, at time.Time) error

	SaveConnectionEvent(ctx context.Context, e ConnectionEvent) error
	SaveRawPacket(ctx context.Context, p RawPacket) error
	SavePosition(ctx context.Context, p Position) error
	SaveEvent(ctx context.Context, e Event) error

	Close() error
}
