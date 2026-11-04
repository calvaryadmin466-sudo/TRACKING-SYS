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
