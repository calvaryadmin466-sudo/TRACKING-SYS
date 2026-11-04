// Command ingestion-server runs the JT/T 808 TCP ingestion service for XV-900-8
// / ZH900 terminals. It is a standalone process: it keeps receiving device
// messages independently of the web application and dashboard.
package main

import (
	"context"
	"log/slog"
	"os"
	"os/signal"
	"syscall"

	"tracking/ingestion/internal/config"
	"tracking/ingestion/internal/mediagw"
	"tracking/ingestion/internal/server"
	"tracking/ingestion/internal/store"
)

func main() {
	cfg := config.Load()
	log := newLogger(cfg.LogLevel)

	st, closeStore := openStore(cfg, log)
	defer closeStore()

	srv := server.New(cfg, st, log)
	if err := srv.Listen(); err != nil {
		log.Error("failed to start", "err", err)
		os.Exit(1)
	}

	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer stop()

	// JT/T 1078 media gateway (captures genuine device video streams).
	var gw *mediagw.Gateway
	if cfg.JT1078Addr != "" {
		gw = mediagw.New(cfg.JT1078Addr, log)
		if err := gw.Listen(); err != nil {
			log.Error("media gateway failed to start", "err", err)
			os.Exit(1)
		}
		go func() { _ = gw.Serve(ctx) }()

		// Internal control API lets the web API drive video commands.
		if cfg.ControlAddr != "" {
			cs := srv.NewControlServer(gw)
			if cfg.ControlToken == "" {
				log.Warn("INGEST_CONTROL_TOKEN not set: internal control API is unauthenticated (bind to localhost only)")
			}
			go func() {
				if err := cs.Serve(ctx); err != nil {
					log.Error("control api error", "err", err)
				}
			}()
		}
	}

	log.Info("ingestion server started", "jt808_addr", cfg.JT808Addr,
		"jt1078_addr", cfg.JT1078Addr, "control_addr", cfg.ControlAddr,
		"store", storeKind(cfg), "read_timeout", cfg.ReadTimeout.String())

	if err := srv.Serve(ctx); err != nil {
		log.Error("serve error", "err", err)
		os.Exit(1)
	}
	log.Info("ingestion server stopped")
}

func openStore(cfg config.Config, log *slog.Logger) (store.Store, func()) {
	if cfg.DatabaseURL == "" {
		log.Warn("DATABASE_URL not set: using in-memory store (NO PERSISTENCE). " +
			"Set DATABASE_URL to persist to PostgreSQL/PostGIS.")
		m := store.NewMemoryStore()
		return m, func() { _ = m.Close() }
	}
	ps, err := store.NewPostgresStore(context.Background(), cfg.DatabaseURL)
	if err != nil {
		log.Error("cannot connect to database; refusing to start with silent data loss", "err", err)
		os.Exit(1)
	}
	log.Info("connected to PostgreSQL store")
	return ps, func() { _ = ps.Close() }
}

func storeKind(cfg config.Config) string {
	if cfg.DatabaseURL == "" {
		return "memory"
	}
	return "postgres"
}

func newLogger(level string) *slog.Logger {
	var lv slog.Level
	switch level {
	case "debug":
		lv = slog.LevelDebug
	case "warn":
		lv = slog.LevelWarn
	case "error":
		lv = slog.LevelError
	default:
		lv = slog.LevelInfo
	}
	return slog.New(slog.NewJSONHandler(os.Stdout, &slog.HandlerOptions{Level: lv}))
}
