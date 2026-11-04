"""Geospatial helpers: haversine distance and point-in-polygon (ray casting).

These keep the event engine backend-agnostic: the same logic runs whether
positions come from the in-memory store or PostgreSQL, without requiring PostGIS
at processing time.
"""
from __future__ import annotations

import math
from typing import Sequence, Tuple

EARTH_RADIUS_M = 6371000.0
Ring = Sequence[Tuple[float, float]]  # [(lat, lon), ...]


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in metres between two lat/lon points."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(min(1.0, math.sqrt(a)))


def point_in_ring(lat: float, lon: float, ring: Ring) -> bool:
    """True if (lat, lon) lies inside the polygon ring (ray casting).

    The ring is a sequence of (lat, lon) vertices; it need not be explicitly
    closed. Uses longitude as x and latitude as y.
    """
    n = len(ring)
    if n < 3:
        return False
    inside = False
    j = n - 1
    for i in range(n):
        yi, xi = ring[i][0], ring[i][1]
        yj, xj = ring[j][0], ring[j][1]
        if ((yi > lat) != (yj > lat)) and \
           (lon < (xj - xi) * (lat - yi) / ((yj - yi) or 1e-12) + xi):
            inside = not inside
        j = i
    return inside
