"""FastAPI application factory, startup/seeding and routing."""
from __future__ import annotations

import asyncio
import contextlib
import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .config import DEFAULT_JWT_SECRET, Settings, load_settings
from .control_client import ControlClient
from .hardening import RateLimiter, SecurityHeadersMiddleware
from .demo_feed import run_demo_feed
from .engine_runner import run_engine
from .live import router as live_router
from .routers import (
    admin, auth, devices, events, geofences, health, positions, reports, trips, vehicles, video,
)
from .security import hash_password
from .store.base import Geofence, Store, User
from .store.memory import MemoryStore
from .store.postgres import PostgresStore

log = logging.getLogger("api")
WEB_DIR = Path(__file__).parent / "web"


def build_store(settings: Settings) -> Store:
    if settings.use_postgres:
        return PostgresStore(settings.database_url)
    log.warning("DATABASE_URL not set: using in-memory store (dev only, no persistence).")
    return MemoryStore()


async def seed(store: Store, settings: Settings) -> int | None:
    """Idempotently ensure a default organization and an admin user exist.
    Returns the default organization id (used to scope the demo feed)."""
    org_id = await store.create_organization(settings.org_name, "default")
    if await store.count_users() == 0:
        role_id = await store.role_id_by_name("super_admin")
        if role_id is None:
            role_id = 1
        await store.create_user(User(
            id=0, role_id=role_id, role_name="super_admin",
            email=settings.admin_email,
            password_hash=hash_password(settings.admin_password),
            full_name="Platform Administrator", is_active=True,
            organization_id=None,  # super admin sees every organization
        ))
        log.info("seeded super admin user: %s", settings.admin_email)
    return org_id


async def _seed_demo_geofence(store: Store, org_id) -> None:
    """A demo zone over part of the simulated area so enter/exit events fire."""
    if await store.list_geofences(org_id):
        return
    ring = [(22.55, 88.35), (22.55, 88.42), (22.62, 88.42), (22.62, 88.35)]
    await store.create_geofence(Geofence(id=0, organization_id=org_id,
                                         name="Central Depot Zone", ring=ring))


def create_app() -> FastAPI:
    settings = load_settings()

    # Production safety: refuse to start with the insecure default JWT secret.
    if settings.is_production and settings.jwt_secret == DEFAULT_JWT_SECRET:
        raise RuntimeError(
            "APP_ENV=production but JWT_SECRET is the insecure default; set a strong JWT_SECRET.")
    if settings.is_production and settings.demo_feed:
        raise RuntimeError("APP_ENV=production but DEMO_FEED is enabled; disable it.")

    store = build_store(settings)

    @contextlib.asynccontextmanager
    async def lifespan(app: FastAPI):
        await store.startup()
        org_id = await seed(store, settings)
        tasks = []
        if settings.demo_feed and isinstance(store, MemoryStore):
            log.warning("starting LABELLED demo feed (simulated vehicles) - dev mode only")
            await _seed_demo_geofence(store, org_id)
            tasks.append(asyncio.create_task(run_demo_feed(store, org_id)))
        if settings.engine_enabled:
            tasks.append(asyncio.create_task(run_engine(store, settings)))
        try:
            yield
        finally:
            for t in tasks:
                t.cancel()
            for t in tasks:
                with contextlib.suppress(asyncio.CancelledError):
                    await t
            await store.close()

    app = FastAPI(title="Tracking Platform API", version="4.0", lifespan=lifespan)
    app.state.settings = settings
    app.state.store = store
    app.state.control = ControlClient(settings)
    app.state.login_limiter = RateLimiter(settings.login_max_attempts, settings.login_window_s)

    if settings.security_headers:
        app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins or ["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health.router)
    app.include_router(auth.router)
    app.include_router(devices.router)
    app.include_router(positions.router)
    app.include_router(vehicles.router)
    app.include_router(geofences.router)
    app.include_router(events.router)
    app.include_router(trips.router)
    app.include_router(video.router)
    app.include_router(reports.router)
    app.include_router(admin.router)
    app.include_router(live_router)

    # Dashboard (build-free static assets) served at the root, after API routes.
    if WEB_DIR.is_dir():
        app.mount("/", StaticFiles(directory=str(WEB_DIR), html=True), name="web")

    return app


app = create_app()
