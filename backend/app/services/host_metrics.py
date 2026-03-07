from __future__ import annotations

import psutil

from app.models.schemas import HostMetrics


class HostMetricsService:
    def __init__(self, storage_path: str = "/") -> None:
        self.storage_path = storage_path
        # Prime cpu_percent so the first visible sample is meaningful.
        psutil.cpu_percent(interval=None)

    @staticmethod
    def _to_gb(raw_bytes: int) -> float:
        return round(raw_bytes / (1024**3), 2)

    def collect(self) -> HostMetrics:
        cpu = round(psutil.cpu_percent(interval=None), 1)

        mem = psutil.virtual_memory()
        disk = psutil.disk_usage(self.storage_path)

        return HostMetrics(
            cpu_percent=cpu,
            memory_percent=round(mem.percent, 1),
            memory_used_gb=self._to_gb(mem.used),
            memory_total_gb=self._to_gb(mem.total),
            storage_percent=round(disk.percent, 1),
            storage_used_gb=self._to_gb(disk.used),
            storage_total_gb=self._to_gb(disk.total),
        )
