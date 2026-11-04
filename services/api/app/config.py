"""Environment-driven configuration. Nothing is hardcoded; safe dev defaults."""
from __future__ import annotations

import os
from dataclasses import dataclass


def _bool(key: str, default: bool) -> bool:
    v = os.getenv(key)
    if v is None:
        return default
    return v.strip().lower() in ("1", "true", "yes", "on")


def _int(key: str, default: int) -> int:
    try:
        return int(os.getenv(key, ""))
    except ValueError:
        return default


def _float(key: str, default: float) -> float:
    try:
        return float(os.getenv(key, ""))
    except ValueError:
        return default


@dataclass(frozen=True)
class Settings:
    host: str
    port: int
    database_url: str          # empty -> in-memory store (dev)
    jwt_secret: str
    jwt_expire_minutes: int
    admin_email: str
    admin_password: str
    org_name: str
    online_threshold_s: int    # device online if last_seen within this
    stale_threshold_s: int     # position fresh if server_time within this
    live_poll_s: int
    demo_feed: bool            # inject labelled simulated movement (memory mode)
    cors_origins: list[str]
    # Stage 3 event/trip engine
    engine_enabled: bool
    engine_poll_s: int
    speed_limit_kmh: float
    harsh_accel_ms2: float
    trip_idle_gap_s: float
    min_trip_distance_m: float
    # Stage 4 video: internal control API of the Go ingestion server
    control_url: str
    control_token: str
    # Stage 5 hardening
    app_env: str               # development | production
    login_max_attempts: int
    login_window_s: int
    security_headers: bool

    @property
    def use_postgres(self) -> bool:
        return bool(self.database_url)

    @property
    def is_production(self) -> bool:
        return self.app_env.lower() in ("production", "prod")


def load_settings() -> Settings:
    database_url = os.getenv("DATABASE_URL", "").strip()
    use_pg = bool(database_url)
    return Settings(
        host=os.getenv("API_HOST", "0.0.0.0"),
        port=_int("API_PORT", 8080),
        database_url=database_url,
        jwt_secret=os.getenv("JWT_SECRET", "dev-insecure-change-me"),
        jwt_expire_minutes=_int("JWT_EXPIRE_MINUTES", 720),
        admin_email=os.getenv("ADMIN_EMAIL", "admin@example.com"),
        admin_password=os.getenv("ADMIN_PASSWORD", "admin12345"),
        org_name=os.getenv("ORG_NAME", "Default Organization"),
        online_threshold_s=_int("ONLINE_THRESHOLD_SECONDS", 120),
        stale_threshold_s=_int("STALE_THRESHOLD_SECONDS", 120),
        live_poll_s=_int("LIVE_POLL_SECONDS", 2),
        # Demo feed is strictly opt-in (default OFF) so the platform never shows
        # simulated data unless explicitly requested with DEMO_FEED=true. It is
        # always refused in production regardless.
        demo_feed=_bool("DEMO_FEED", default=False),
        cors_origins=[o for o in os.getenv("CORS_ORIGINS", "*").split(",") if o],
        engine_enabled=_bool("ENGINE_ENABLED", default=True),
        engine_poll_s=_int("ENGINE_POLL_SECONDS", 2),
        speed_limit_kmh=_float("SPEED_LIMIT_KMH", 80.0),
        harsh_accel_ms2=_float("HARSH_ACCEL_MS2", 3.5),
        trip_idle_gap_s=_float("TRIP_IDLE_GAP_SECONDS", 300.0),
        min_trip_distance_m=_float("MIN_TRIP_DISTANCE_M", 200.0),
        control_url=os.getenv("CONTROL_URL", "http://127.0.0.1:7900").rstrip("/"),
        control_token=os.getenv("CONTROL_TOKEN", ""),
        app_env=os.getenv("APP_ENV", "development"),
        login_max_attempts=_int("LOGIN_MAX_ATTEMPTS", 10),
        login_window_s=_int("LOGIN_WINDOW_SECONDS", 300),
        security_headers=_bool("SECURITY_HEADERS", default=True),
    )


# The insecure default that must never be used in production.
DEFAULT_JWT_SECRET = "dev-insecure-change-me"
