package server

import (
	"errors"
	"net"
	"sync"
	"sync/atomic"
	"time"
)

// Session tracks the state of one device TCP connection.
type Session struct {
	ConnID     string
	RemoteAddr string

	mu            sync.Mutex
	conn          net.Conn
	reportingID   string
	phoneBCD      []byte
	serialNumber  string
	hasVersion    bool
	version       byte
	authenticated bool
	simulated     bool
	deviceDBID    int64
	connectedAt   time.Time
	lastSeen      time.Time

	BytesIn   atomic.Int64
	PacketsIn atomic.Int64
	Decoded   atomic.Int64
	Unknown   atomic.Int64
}

func (s *Session) ReportingID() string {
	s.mu.Lock()
	defer s.mu.Unlock()
	return s.reportingID
}

func (s *Session) setIdentity(reportingID string, phoneBCD []byte, hasVersion bool, version byte) {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.reportingID = reportingID
	s.phoneBCD = append([]byte(nil), phoneBCD...)
	s.hasVersion = hasVersion
	s.version = version
}

func (s *Session) setConn(c net.Conn) {
	s.mu.Lock()
	s.conn = c
	s.mu.Unlock()
}

// Send writes a prebuilt frame to the device's live connection.
func (s *Session) Send(frame []byte) error {
	s.mu.Lock()
	c := s.conn
	s.mu.Unlock()
	if c == nil {
		return errors.New("session has no active connection")
	}
	_, err := c.Write(frame)
	return err
}

// Identity returns the fields needed to address this device in outbound commands.
func (s *Session) Identity() (phoneBCD []byte, hasVersion bool, version byte) {
	s.mu.Lock()
	defer s.mu.Unlock()
	return append([]byte(nil), s.phoneBCD...), s.hasVersion, s.version
}

func (s *Session) setDBID(id int64) {
	s.mu.Lock()
	s.deviceDBID = id
	s.mu.Unlock()
}

func (s *Session) DBID() int64 {
	s.mu.Lock()
	defer s.mu.Unlock()
	return s.deviceDBID
}

func (s *Session) setSerial(serial string) {
	s.mu.Lock()
	s.serialNumber = serial
	s.mu.Unlock()
}

func (s *Session) setAuthenticated(v bool) {
	s.mu.Lock()
	s.authenticated = v
	s.mu.Unlock()
}

func (s *Session) setSimulated(v bool) {
	s.mu.Lock()
	s.simulated = v
	s.mu.Unlock()
}

// Simulated reports whether this device identified itself as a simulator, so its
// data can be kept distinct from genuine device data throughout the system.
func (s *Session) Simulated() bool {
	s.mu.Lock()
	defer s.mu.Unlock()
	return s.simulated
}

func (s *Session) touch(t time.Time) {
	s.mu.Lock()
	s.lastSeen = t
	s.mu.Unlock()
}

// Registry is the set of live device sessions, indexed by connection id and by
// reporting id once a device has identified itself.
type Registry struct {
	mu      sync.RWMutex
	byConn  map[string]*Session
	byPhone map[string]*Session
}

// NewRegistry returns an empty session registry.
func NewRegistry() *Registry {
	return &Registry{
		byConn:  make(map[string]*Session),
		byPhone: make(map[string]*Session),
	}
}

func (r *Registry) add(s *Session) {
	r.mu.Lock()
	r.byConn[s.ConnID] = s
	r.mu.Unlock()
}

// bind associates a reporting id with a session. If another connection already
// holds the same reporting id, the previous binding is replaced (reconnect).
func (r *Registry) bind(phone string, s *Session) {
	r.mu.Lock()
	r.byPhone[phone] = s
	r.mu.Unlock()
}

func (r *Registry) remove(s *Session) {
	r.mu.Lock()
	delete(r.byConn, s.ConnID)
	if phone := s.ReportingID(); phone != "" {
		if cur, ok := r.byPhone[phone]; ok && cur == s {
			delete(r.byPhone, phone)
		}
	}
	r.mu.Unlock()
}

// Count returns the number of live connections.
func (r *Registry) Count() int {
	r.mu.RLock()
	defer r.mu.RUnlock()
	return len(r.byConn)
}

// GetByPhone returns the live session for a reporting id, if any.
func (r *Registry) GetByPhone(phone string) (*Session, bool) {
	r.mu.RLock()
	defer r.mu.RUnlock()
	s, ok := r.byPhone[phone]
	return s, ok
}
