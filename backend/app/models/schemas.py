from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

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
    cpu_limit: float = 0.0
    memory_percent: float = 0.0
    memory_used_mb: float = 0.0
    memory_limit_mb: float = 0.0


class Snapshot(BaseModel):
    timestamp: float
    host: HostMetrics
    containers: list[ContainerMetrics] = Field(default_factory=list)
    runtime_name: str
    runtime_available: bool = True
    runtime_error: Optional[str] = None


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


class PythonToolLimits(BaseModel):
    cpu_count: float
    memory_mb: int
    timeout_ms: int
    max_code_bytes: int
    max_output_chars: int
    max_concurrency: int
    max_artifacts: int
    max_artifact_bytes: int
    max_artifact_total_bytes: int
    artifact_ttl_seconds: int


class PythonToolLastExecution(BaseModel):
    finished_at: datetime
    status: Literal["succeeded", "failed", "timed_out"]
    duration_ms: int


class PythonToolStatus(BaseModel):
    schema_version: int = 1
    id: str = "python-sandbox"
    enabled: bool
    state: Literal["disabled", "checking", "ready", "busy", "degraded", "disabling"]
    ready: bool
    image: str
    limits: PythonToolLimits
    running_executions: int
    last_execution: Optional[PythonToolLastExecution] = None
    error: Optional[str] = None


class PythonToolEnableRequest(BaseModel):
    enabled: bool


class PythonArtifactRequest(BaseModel):
    path: str = Field(min_length=1, max_length=128)
    media_type: str = Field(default="application/octet-stream", min_length=1, max_length=128)


class PythonExecutionRequest(BaseModel):
    code: str
    timeout_ms: Optional[int] = Field(default=None, ge=1)
    artifacts: list[PythonArtifactRequest] = Field(default_factory=list, max_length=4)


class PythonExecutionTruncation(BaseModel):
    stdout: bool = False
    stderr: bool = False


class PythonArtifactResponse(BaseModel):
    name: str
    media_type: str
    size_bytes: int
    sha256: str
    download_url: str


class PythonArtifactError(BaseModel):
    path: str
    error: str


class PythonExecutionResponse(BaseModel):
    schema_version: int = 1
    request_id: str
    execution_id: str
    ok: bool
    status: Literal["succeeded", "failed", "timed_out"]
    exit_code: Optional[int]
    stdout: str
    stderr: str
    content: str
    truncated: PythonExecutionTruncation
    duration_ms: int
    image: str
    artifacts: list[PythonArtifactResponse] = Field(default_factory=list)
    artifact_errors: list[PythonArtifactError] = Field(default_factory=list)
