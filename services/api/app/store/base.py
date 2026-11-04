"""Store abstraction and the data records exchanged with it.

The three device identifiers are kept strictly separate, mirroring the Go
ingestion side and the database schema:
  - reporting_id : the JT/T 808 "phone number" the terminal reports with
  - serial_number: the hardware serial / terminal id
  - id           : the internal database primary key
"""
from __future__ import annotations

import abc
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class User:
    id: int
    role_id: int
    role_name: str
    email: str
    password_hash: str
    full_name: str = ""
    is_active: bool = True
    organization_id: Optional[int] = None
    created_at: Optional[datetime] = None
    last_login_at: Optional[datetime] = None


@dataclass
class Vehicle:
    id: int
    registration: str
    vehicle_type: str = ""
    driver_name: str = ""
    organization_id: Optional[int] = None
    fleet_id: Optional[int] = None
    created_at: Optional[datetime] = None


@dataclass
class DeviceStatus:
    id: int
    reporting_id: str
    serial_number: str = ""
    model: str = ""
    manufacturer: str = ""
    plate: str = ""
    protocol: str = "JT808"
    simulated: bool = False
    active: bool = True
    organization_id: Optional[int] = None
    vehicle_id: Optional[int] = None
    vehicle_registration: str = ""
    first_seen: Optional[datetime] = None
    last_seen: Optional[datetime] = None
    # latest position (present when has_position)
    has_position: bool = False
    latitude: float = 0.0
    longitude: float = 0.0
    speed: float = 0.0
    heading: int = 0
    altitude: int = 0
    acc: bool = False
    positioned: bool = False
    valid: bool = False
    mileage_km: float = 0.0
    device_time: Optional[datetime] = None
    server_time: Optional[datetime] = None


@dataclass
class Position:
    device_id: int
    reporting_id: str
    latitude: float
    longitude: float
    speed: float = 0.0
    heading: int = 0
    altitude: int = 0
    acc: bool = False
    positioned: bool = False
    valid: bool = False
    satellites: int = 0
    mileage_km: float = 0.0
    simulated: bool = False
    device_time: Optional[datetime] = None
    server_time: Optional[datetime] = None


@dataclass
class LivePosition:
    device_id: int
    reporting_id: str
    latitude: float
    longitude: float
    speed: float = 0.0
    heading: int = 0
    acc: bool = False
    valid: bool = False
    device_time: Optional[datetime] = None
    server_time: Optional[datetime] = None


@dataclass
class DevicePatch:
    vehicle_id: Optional[int] = None
    organization_id: Optional[int] = None
    active: Optional[bool] = None
    plate: Optional[str] = None


@dataclass
class AuditEntry:
    action: str
    entity: str
    entity_id: str = ""
    detail: str = ""
    user_id: Optional[int] = None
    at: Optional[datetime] = None
    id: Optional[int] = None


@dataclass
class Event:
    """An operational/alarm event produced by the event engine."""
    device_id: int
    reporting_id: str
    type: str
    severity: str = "info"      # info | warning | alarm
    detail: str = ""
    value: Optional[float] = None
    at: Optional[datetime] = None
    id: Optional[int] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    acknowledged: bool = False
    acknowledged_by: Optional[int] = None
    acknowledged_at: Optional[datetime] = None
    resolved: bool = False
    resolved_at: Optional[datetime] = None


@dataclass
class Organization:
    id: int
    name: str


@dataclass
class Role:
    id: int
    name: str


@dataclass
class MaintenanceItem:
    id: int
    device_id: Optional[int]
    title: str
    kind: str = "service"           # service|inspection|insurance|license|other
    organization_id: Optional[int] = None
    due_date: Optional[datetime] = None
    due_odometer_km: Optional[float] = None
    odometer_at_create: float = 0.0
    status: str = "open"            # open|done
    completed_at: Optional[datetime] = None
    notes: str = ""
    created_at: Optional[datetime] = None
    # joined/computed (not persisted):
    device_label: str = ""


@dataclass
class NotificationRule:
    id: int
    name: str
    organization_id: Optional[int] = None
    event_types: list = field(default_factory=list)  # empty = any type
    min_severity: str = "warning"  # info|warning|alarm
    channel: str = "webhook"
    target: str = ""
    active: bool = True
    created_at: Optional[datetime] = None


@dataclass
class NotificationLogEntry:
    id: Optional[int]
    rule_id: Optional[int]
    event_id: Optional[int]
    event_type: str
    channel: str
    target: str
    status: str
    detail: str = ""
    at: Optional[datetime] = None


@dataclass
class RawPacketView:
    id: Optional[int]
    reporting_id: str
    received_at: Optional[datetime]
    length: int
    message_name: str
    decoded: bool
    checksum_ok: bool
    hex: str
    ascii: str
    note: str


@dataclass
class Geofence:
    id: int
    organization_id: Optional[int]
    name: str
    ring: list = field(default_factory=list)  # [(lat, lon), ...]


@dataclass
class Trip:
    id: int
    device_id: int
    reporting_id: str
    started_at: datetime
    ended_at: Optional[datetime] = None
    distance_km: float = 0.0
    max_speed: float = 0.0
    path: list = field(default_factory=list)  # [(lat, lon), ...]


@dataclass
class CameraChannel:
    device_id: int
    channel_no: int
    name: str = ""
    enabled: bool = True


@dataclass
class VideoSession:
    id: int
    device_id: int
    reporting_id: str
    channel: int
    kind: str = "live"            # live | playback
    status: str = "requested"     # requested | active | ended | failed
    started_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None
    video_host: str = ""
    video_tcp_port: int = 0
    detail: str = ""


class Store(abc.ABC):
    """Async persistence interface used by the API."""

    # lifecycle
    async def startup(self) -> None:  # optional
        return None

    async def close(self) -> None:  # optional
        return None

    # auth & tenancy
    @abc.abstractmethod
    async def get_user_by_email(self, email: str) -> Optional[User]: ...

    @abc.abstractmethod
    async def create_user(self, u: User) -> int: ...

    @abc.abstractmethod
    async def update_user_last_login(self, user_id: int, at: datetime) -> None: ...

    @abc.abstractmethod
    async def count_users(self) -> int: ...

    @abc.abstractmethod
    async def create_organization(self, name: str, slug: str) -> int: ...

    @abc.abstractmethod
    async def role_id_by_name(self, name: str) -> Optional[int]: ...

    # devices
    @abc.abstractmethod
    async def list_devices(self, org_id: Optional[int]) -> list[DeviceStatus]: ...

    @abc.abstractmethod
    async def get_device(self, device_id: int) -> Optional[DeviceStatus]: ...

    @abc.abstractmethod
    async def update_device(self, device_id: int, patch: DevicePatch) -> None: ...

    # vehicles
    @abc.abstractmethod
    async def list_vehicles(self, org_id: Optional[int]) -> list[Vehicle]: ...

    @abc.abstractmethod
    async def get_vehicle(self, vehicle_id: int) -> Optional[Vehicle]: ...

    @abc.abstractmethod
    async def create_vehicle(self, v: Vehicle) -> int: ...

    @abc.abstractmethod
    async def update_vehicle(self, v: Vehicle) -> None: ...

    # positions
    @abc.abstractmethod
    async def list_positions(self, device_id: int, frm: Optional[datetime],
                             to: Optional[datetime], limit: int) -> list[Position]: ...

    @abc.abstractmethod
    async def latest_positions(self, org_id: Optional[int],
                               since: datetime) -> list[LivePosition]: ...

    # audit
    @abc.abstractmethod
    async def save_audit(self, entry: AuditEntry) -> None: ...

    # --- Stage 3: events, geofences, trips ---

    @abc.abstractmethod
    async def positions_since(self, since: datetime, org_id: Optional[int]) -> list[Position]: ...

    @abc.abstractmethod
    async def save_event(self, e: Event) -> int: ...

    @abc.abstractmethod
    async def list_events(self, org_id: Optional[int], device_id: Optional[int],
                          since: Optional[datetime], types: Optional[list[str]],
                          limit: int) -> list[Event]: ...

    @abc.abstractmethod
    async def create_geofence(self, g: Geofence) -> int: ...

    @abc.abstractmethod
    async def list_geofences(self, org_id: Optional[int]) -> list[Geofence]: ...

    @abc.abstractmethod
    async def get_geofence(self, gid: int) -> Optional[Geofence]: ...

    @abc.abstractmethod
    async def delete_geofence(self, gid: int) -> None: ...

    @abc.abstractmethod
    async def save_trip(self, t: Trip) -> int: ...

    @abc.abstractmethod
    async def list_trips(self, device_id: int, limit: int) -> list[Trip]: ...

    @abc.abstractmethod
    async def get_trip(self, tid: int) -> Optional[Trip]: ...

    # --- Stage 4: video ---

    @abc.abstractmethod
    async def list_camera_channels(self, device_id: int) -> list[CameraChannel]: ...

    @abc.abstractmethod
    async def create_video_session(self, v: VideoSession) -> int: ...

    @abc.abstractmethod
    async def list_video_sessions(self, org_id: Optional[int], device_id: Optional[int],
                                  limit: int) -> list[VideoSession]: ...

    @abc.abstractmethod
    async def get_video_session(self, sid: int) -> Optional[VideoSession]: ...

    @abc.abstractmethod
    async def end_video_session(self, sid: int, status: str) -> None: ...

    # --- Redesign: event ack/resolve, admin, audit, diagnostics ---

    @abc.abstractmethod
    async def get_event(self, eid: int) -> Optional[Event]: ...

    @abc.abstractmethod
    async def ack_event(self, eid: int, user_id: int) -> None: ...

    @abc.abstractmethod
    async def resolve_event(self, eid: int) -> None: ...

    @abc.abstractmethod
    async def list_users(self, org_id: Optional[int]) -> list[User]: ...

    @abc.abstractmethod
    async def list_roles(self) -> list[Role]: ...

    @abc.abstractmethod
    async def list_organizations(self) -> list[Organization]: ...

    @abc.abstractmethod
    async def list_audit(self, org_id: Optional[int], limit: int) -> list[AuditEntry]: ...

    @abc.abstractmethod
    async def list_raw_packets(self, reporting_id: str, limit: int) -> list[RawPacketView]: ...

    # --- Fleet ops: maintenance, notification rules, notification log ---

    @abc.abstractmethod
    async def create_maintenance(self, m: MaintenanceItem) -> int: ...

    @abc.abstractmethod
    async def list_maintenance(self, org_id: Optional[int], device_id: Optional[int]) -> list[MaintenanceItem]: ...

    @abc.abstractmethod
    async def get_maintenance(self, mid: int) -> Optional[MaintenanceItem]: ...

    @abc.abstractmethod
    async def update_maintenance(self, m: MaintenanceItem) -> None: ...

    @abc.abstractmethod
    async def delete_maintenance(self, mid: int) -> None: ...

    @abc.abstractmethod
    async def create_rule(self, r: NotificationRule) -> int: ...

    @abc.abstractmethod
    async def list_rules(self, org_id: Optional[int]) -> list[NotificationRule]: ...

    @abc.abstractmethod
    async def all_active_rules(self) -> list[NotificationRule]: ...

    @abc.abstractmethod
    async def get_rule(self, rid: int) -> Optional[NotificationRule]: ...

    @abc.abstractmethod
    async def update_rule(self, r: NotificationRule) -> None: ...

    @abc.abstractmethod
    async def delete_rule(self, rid: int) -> None: ...

    @abc.abstractmethod
    async def save_notification(self, e: NotificationLogEntry) -> None: ...

    @abc.abstractmethod
    async def list_notifications(self, org_id: Optional[int], limit: int) -> list[NotificationLogEntry]: ...
