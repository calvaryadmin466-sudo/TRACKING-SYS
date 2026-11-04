// Package server implements the JT/T 808 TCP ingestion server: accepting device
// connections, reassembling frames from the byte stream, inspecting raw packets,
// decoding recognised messages and persisting results through a store.Store.
package server

import (
	"context"
	"fmt"
	"log/slog"
	"net"
	"sync"
	"sync/atomic"
	"time"

	"tracking/ingestion/internal/config"
	"tracking/ingestion/internal/store"
)

// Server is the TCP ingestion server.
type Server struct {
	cfg      config.Config
	store    store.Store
	log      *slog.Logger
	registry *Registry

	platformSerial atomic.Uint32
	connSeq        atomic.Uint64

	ln     net.Listener
	wg     sync.WaitGroup
	closed atomic.Bool
}

// New constructs a Server.
func New(cfg config.Config, st store.Store, log *slog.Logger) *Server {
	return &Server{
		cfg:      cfg,
		store:    st,
		log:      log,
		registry: NewRegistry(),
	}
}

// Registry exposes the live session registry (used for diagnostics/metrics).
func (s *Server) Registry() *Registry { return s.registry }

// Addr returns the actual bound address (useful when listening on :0 in tests).
func (s *Server) Addr() net.Addr {
	if s.ln == nil {
		return nil
	}
	return s.ln.Addr()
}

// Listen binds the configured TCP address without starting the accept loop.
// Separating Listen from Serve lets tests learn the bound port before serving.
func (s *Server) Listen() error {
	ln, err := net.Listen("tcp", s.cfg.JT808Addr)
	if err != nil {
		return fmt.Errorf("server: listen %s: %w", s.cfg.JT808Addr, err)
	}
	s.ln = ln
	s.log.Info("jt808 ingestion listening", "addr", ln.Addr().String())
	return nil
}

// Serve runs the accept loop until the context is cancelled or Close is called.
func (s *Server) Serve(ctx context.Context) error {
	if s.ln == nil {
		if err := s.Listen(); err != nil {
			return err
		}
	}
	go func() {
		<-ctx.Done()
		_ = s.Close()
	}()
	for {
		conn, err := s.ln.Accept()
		if err != nil {
			if s.closed.Load() {
				break
			}
			s.log.Error("accept error", "err", err)
			continue
		}
		s.wg.Add(1)
		go func() {
			defer s.wg.Done()
			s.handleConn(ctx, conn)
		}()
	}
	s.wg.Wait()
	return nil
}

// Close stops accepting new connections. In-flight connections drain naturally.
func (s *Server) Close() error {
	if s.closed.Swap(true) {
		return nil
	}
	if s.ln != nil {
		return s.ln.Close()
	}
	return nil
}

func (s *Server) nextPlatformSerial() uint16 {
	return uint16(s.platformSerial.Add(1))
}

func (s *Server) newConnID() string {
	return fmt.Sprintf("c%d-%d", s.connSeq.Add(1), time.Now().UnixNano()%100000)
}
