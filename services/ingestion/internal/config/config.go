// Package config loads ingestion-server configuration from the environment.
// Nothing is hardcoded: listen address, database URL and timeouts are all
// overridable, with safe development defaults.
package config

import (
	"os"
	"strconv"
	"time"
)

// Config holds ingestion-server settings.
type Config struct {
	// JT808Addr is the TCP listen address for JT/T 808 device connections,
	// e.g. ":7808". The same port must be configured in the device's
	// ministry-standard server menu.
	JT808Addr string
	// DatabaseURL is the PostgreSQL DSN. When empty the server falls back to the
	// in-memory store and logs a clear warning (no persistence).
	DatabaseURL string
	// ReadTimeout closes a connection that sends nothing (not even a heartbeat)
	// within this window.
	ReadTimeout time.Duration
	// MaxFrameBytes bounds the per-connection reassembly buffer to guard against
	// a device that never sends a frame delimiter.
	MaxFrameBytes int
	// LogLevel is "debug", "info", "warn" or "error".
	LogLevel string
	// LogRawPackets controls whether full hex dumps are written to the log for
	// every received chunk (always stored, this only affects log verbosity).
	LogRawPackets bool

	// --- Stage 4: JT/T 1078 video ---
	// JT1078Addr is the TCP listen address for the media gateway (device video
	// stream connections). Empty disables the gateway.
	JT1078Addr string
	// ControlAddr is the internal HTTP control API (used by the web API to send
	// video-control commands to connected devices). Bind to localhost only.
	ControlAddr string
	// ControlToken guards the internal control API (Bearer token).
	ControlToken string
	// VideoPublicHost/Port are advertised to the device in the 0x9101 command as
	// the media server it should dial. Defaults to the gateway's own port.
	VideoPublicHost    string
	VideoPublicTCPPort int
	VideoPublicUDPPort int
}

// Load builds a Config from environment variables with defaults.
func Load() Config {
	return Config{
		JT808Addr:     env("INGEST_JT808_ADDR", ":7808"),
		DatabaseURL:   env("DATABASE_URL", ""),
		ReadTimeout:   envDuration("INGEST_READ_TIMEOUT", 5*time.Minute),
		MaxFrameBytes: envInt("INGEST_MAX_FRAME_BYTES", 64*1024),
		LogLevel:      env("INGEST_LOG_LEVEL", "info"),
		LogRawPackets: envBool("INGEST_LOG_RAW", true),

		JT1078Addr:         env("INGEST_JT1078_ADDR", ":7078"),
		ControlAddr:        env("INGEST_CONTROL_ADDR", "127.0.0.1:7900"),
		ControlToken:       env("INGEST_CONTROL_TOKEN", ""),
		VideoPublicHost:    env("INGEST_VIDEO_PUBLIC_HOST", "127.0.0.1"),
		VideoPublicTCPPort: envInt("INGEST_VIDEO_PUBLIC_TCP_PORT", 7078),
		VideoPublicUDPPort: envInt("INGEST_VIDEO_PUBLIC_UDP_PORT", 0),
	}
}

func env(key, def string) string {
	if v, ok := os.LookupEnv(key); ok && v != "" {
		return v
	}
	return def
}

func envInt(key string, def int) int {
	if v, ok := os.LookupEnv(key); ok {
		if n, err := strconv.Atoi(v); err == nil {
			return n
		}
	}
	return def
}

func envBool(key string, def bool) bool {
	if v, ok := os.LookupEnv(key); ok {
		if b, err := strconv.ParseBool(v); err == nil {
			return b
		}
	}
	return def
}

func envDuration(key string, def time.Duration) time.Duration {
	if v, ok := os.LookupEnv(key); ok {
		if d, err := time.ParseDuration(v); err == nil {
			return d
		}
	}
	return def
}
