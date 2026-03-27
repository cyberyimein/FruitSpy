from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class HostMetrics(BaseModel):
    cpu_percent: float = 0.0
    memory_percent: float = 0.0
    memory_used_gb: float = 0.0
    memory_total_gb: float = 0.0
    storage_percent: float = 0.0
    storage_used_gb: float = 0.0
    storage_total_gb: float = 0.0


class ContainerMetrics(BaseModel):
    id: str
    name: str
    image: str
    status: str
    cpu_percent: float = 0.0
    memory_percent: float = 0.0
    memory_used_mb: float = 0.0
    memory_limit_mb: float = 0.0


class Snapshot(BaseModel):
    timestamp: float
    host: HostMetrics
    containers: list[ContainerMetrics] = Field(default_factory=list)
    docker_available: bool = True
    docker_error: Optional[str] = None


class PackageRecord(BaseModel):
    manager: str
    name: str
    version: str
    source: str


class PackageManagerInventory(BaseModel):
    manager: str
    available: bool = True
    command: Optional[str] = None
    package_count: int = 0
    error: Optional[str] = None
    packages: list[PackageRecord] = Field(default_factory=list)


class PackageInventory(BaseModel):
    timestamp: float
    total_packages: int = 0
    managers: list[PackageManagerInventory] = Field(default_factory=list)
