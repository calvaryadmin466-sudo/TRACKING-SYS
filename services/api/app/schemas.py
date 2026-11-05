"""Pydantic request bodies for the API."""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    email: str = Field(min_length=3)
    password: str = Field(min_length=1)


class VehicleIn(BaseModel):
    registration: str = Field(min_length=1, max_length=64)
    vehicle_type: str = ""
    driver_name: str = ""
    fleet_id: Optional[int] = None


class DeviceUpdate(BaseModel):
    vehicle_id: Optional[int] = None
    active: Optional[bool] = None
    plate: Optional[str] = None
    ip_address: Optional[str] = Field(default=None, max_length=64)


class DeviceCreate(BaseModel):
    """Admin device provisioning: register a unit by its identifiers before it
    connects. device_id is the JT/T 808 reporting ID (the terminal phone number)."""
    device_id: str = Field(min_length=1, max_length=64, description="JT/T 808 reporting ID / terminal phone number")
    plate: str = Field(default="", max_length=64)
    ip_address: str = Field(default="", max_length=64, description="MDVR decoder IP address")
    model: str = Field(default="", max_length=64)
