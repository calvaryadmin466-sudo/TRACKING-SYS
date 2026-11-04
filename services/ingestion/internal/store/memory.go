package store

import (
	"context"
	"sync"
	"time"
)

// MemoryStore is a thread-safe in-memory Store used by tests, the simulator and
// as a safe default when no database is configured. It never touches a network
// so unit and integration tests run fully offline.
type MemoryStore struct {
	mu          sync.Mutex
	nextID      int64
	devices     map[string]Device // keyed by reporting ID
	Connections []ConnectionEvent
	Packets     []RawPacket
	Positions   []Position
	Events      []Event
}

// NewMemoryStore returns an empty MemoryStore.
func NewMemoryStore() *MemoryStore {
	return &MemoryStore{
		nextID:  0,
		devices: make(map[string]Device),
	}
}

func (m *MemoryStore) UpsertDevice(_ context.Context, d Device) (int64, error) {
	m.mu.Lock()
	defer m.mu.Unlock()
	if existing, ok := m.devices[d.ReportingID]; ok {
		d.ID = existing.ID
		if d.FirstSeen.IsZero() {
			d.FirstSeen = existing.FirstSeen
		}
		if d.SerialNumber == "" {
			d.SerialNumber = existing.SerialNumber
		}
		if d.AuthCode == "" {
			d.AuthCode = existing.AuthCode
		}
		m.devices[d.ReportingID] = d
		return d.ID, nil
	}
	m.nextID++
	d.ID = m.nextID
	if d.FirstSeen.IsZero() {
		d.FirstSeen = time.Now().UTC()
	}
	m.devices[d.ReportingID] = d
	return d.ID, nil
}

func (m *MemoryStore) GetDeviceByReportingID(_ context.Context, reportingID string) (Device, bool, error) {
	m.mu.Lock()
	defer m.mu.Unlock()
	d, ok := m.devices[reportingID]
	return d, ok, nil
}

func (m *MemoryStore) TouchDevice(_ context.Context, reportingID string, at time.Time) error {
	m.mu.Lock()
	defer m.mu.Unlock()
	if d, ok := m.devices[reportingID]; ok {
		d.LastSeen = at
		m.devices[reportingID] = d
	}
	return nil
}

func (m *MemoryStore) SaveConnectionEvent(_ context.Context, e ConnectionEvent) error {
	m.mu.Lock()
	defer m.mu.Unlock()
	m.Connections = append(m.Connections, e)
	return nil
}

func (m *MemoryStore) SaveRawPacket(_ context.Context, p RawPacket) error {
	m.mu.Lock()
	defer m.mu.Unlock()
	m.Packets = append(m.Packets, p)
	return nil
}

func (m *MemoryStore) SavePosition(_ context.Context, p Position) error {
	m.mu.Lock()
	defer m.mu.Unlock()
	m.Positions = append(m.Positions, p)
	return nil
}

func (m *MemoryStore) SaveEvent(_ context.Context, e Event) error {
	m.mu.Lock()
	defer m.mu.Unlock()
	m.Events = append(m.Events, e)
	return nil
}

// Close is a no-op for the in-memory store.
func (m *MemoryStore) Close() error { return nil }

// Snapshot helpers for tests (return copies under lock).

func (m *MemoryStore) PositionCount() int {
	m.mu.Lock()
	defer m.mu.Unlock()
	return len(m.Positions)
}

func (m *MemoryStore) PacketCount() int {
	m.mu.Lock()
	defer m.mu.Unlock()
	return len(m.Packets)
}

func (m *MemoryStore) LastPosition() (Position, bool) {
	m.mu.Lock()
	defer m.mu.Unlock()
	if len(m.Positions) == 0 {
		return Position{}, false
	}
	return m.Positions[len(m.Positions)-1], true
}

// UnknownPackets returns copies of raw packets that were not recognised.
func (m *MemoryStore) UnknownPackets() []RawPacket {
	m.mu.Lock()
	defer m.mu.Unlock()
	var out []RawPacket
	for _, p := range m.Packets {
		if !p.Decoded {
			out = append(out, p)
		}
	}
	return out
}
