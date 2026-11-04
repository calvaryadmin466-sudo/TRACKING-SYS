"""Tracking platform HTTP API (FastAPI).

This service provides authentication, RBAC, device/vehicle management, position
history and a live WebSocket feed, plus a build-free Leaflet dashboard. It is a
separate process from the Go JT/T 808 ingestion server; in production both talk
to the same PostgreSQL/PostGIS database (ingestion writes, API reads).
"""
