"""Track playback utilities: speed-tier segmentation and stationary stop detection."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional


def speed_tier(speed: float) -> str:
    """Classify speed into CMSV7-standard tiers:
    L: 0-40 km/h (Low/Normal urban)
    M: 41-80 km/h (Medium/Highway)
    H: 81-120 km/h (High/Expressway)
    S: Over 120 km/h (Overspeed/Critical)
    """
    if speed > 120.0:
        return "S"
    if speed > 80.0:
        return "H"
    if speed > 40.0:
        return "M"
    return "L"


def speed_color(tier: str) -> str:
    palette = {
        "S": "#F06464",  # Red
        "H": "#F7931A",  # Orange
        "M": "#20C997",  # Green
        "L": "#3282F6",  # Blue
    }
    return palette.get(tier, "#3282F6")


def _to_dt(val: Any) -> Optional[datetime]:
    if isinstance(val, datetime):
        return val if val.tzinfo else val.replace(tzinfo=timezone.utc)
    if isinstance(val, str) and val:
        try:
            dt = datetime.fromisoformat(val.replace("Z", "+00:00"))
            return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        except ValueError:
            return None
    return None


def detect_stops(points: list[dict], min_stop_s: int = 300, max_speed_kmh: float = 3.0) -> list[dict]:
    """Detect stationary stops >= min_stop_s (default 300s = 5m).
    points: sorted list of dicts with latitude, longitude, speed, and device_time/server_time.
    """
    if not points:
        return []

    stops = []
    stop_start = None
    stop_points = []

    for p in points:
        speed = float(p.get("speed") or 0.0)
        ts = _to_dt(p.get("device_time") or p.get("server_time"))
        if not ts:
            continue

        is_stopped = speed <= max_speed_kmh

        if is_stopped:
            if stop_start is None:
                stop_start = ts
                stop_points = [p]
            else:
                stop_points.append(p)
        else:
            if stop_start is not None and stop_points:
                last_ts = _to_dt(stop_points[-1].get("device_time") or stop_points[-1].get("server_time"))
                if last_ts:
                    dur_s = (last_ts - stop_start).total_seconds()
                    if dur_s >= min_stop_s:
                        center_lat = sum(float(pt["latitude"]) for pt in stop_points) / len(stop_points)
                        center_lon = sum(float(pt["longitude"]) for pt in stop_points) / len(stop_points)
                        stops.append({
                            "latitude": round(center_lat, 6),
                            "longitude": round(center_lon, 6),
                            "started_at": stop_start.isoformat(),
                            "ended_at": last_ts.isoformat(),
                            "duration_s": round(dur_s),
                            "duration_min": round(dur_s / 60.0, 1),
                        })
            stop_start = None
            stop_points = []

    # Final trailing stop check
    if stop_start is not None and stop_points:
        last_ts = _to_dt(stop_points[-1].get("device_time") or stop_points[-1].get("server_time"))
        if last_ts:
            dur_s = (last_ts - stop_start).total_seconds()
            if dur_s >= min_stop_s:
                center_lat = sum(float(pt["latitude"]) for pt in stop_points) / len(stop_points)
                center_lon = sum(float(pt["longitude"]) for pt in stop_points) / len(stop_points)
                stops.append({
                    "latitude": round(center_lat, 6),
                    "longitude": round(center_lon, 6),
                    "started_at": stop_start.isoformat(),
                    "ended_at": last_ts.isoformat(),
                    "duration_s": round(dur_s),
                    "duration_min": round(dur_s / 60.0, 1),
                })

    return stops


def build_speed_segments(points: list[dict]) -> list[dict]:
    """Segment consecutive points into polylines grouped by speed tier."""
    if len(points) < 2:
        return []

    segments = []
    current_tier = speed_tier(float(points[0].get("speed") or 0.0))
    current_path = [[float(points[0]["latitude"]), float(points[0]["longitude"])]]

    for i in range(1, len(points)):
        pt = points[i]
        tier = speed_tier(float(pt.get("speed") or 0.0))
        coord = [float(pt["latitude"]), float(pt["longitude"])]

        if tier == current_tier:
            current_path.append(coord)
        else:
            # Connect the end of this segment to the start of next for continuous lines
            current_path.append(coord)
            segments.append({
                "tier": current_tier,
                "color": speed_color(current_tier),
                "path": current_path,
            })
            current_tier = tier
            current_path = [coord]

    if len(current_path) >= 2:
        segments.append({
            "tier": current_tier,
            "color": speed_color(current_tier),
            "path": current_path,
        })

    return segments
