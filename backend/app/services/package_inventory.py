from __future__ import annotations

import json
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Optional, Sequence

from app.models.schemas import PackageInventory, PackageManagerInventory, PackageRecord


class PackageInventoryService:
    def collect(self) -> PackageInventory:
        managers = [
            self._collect_npm(),
            self._collect_brew(),
            self._collect_pip(),
            self._collect_uv(),
        ]
        total_packages = sum(manager.package_count for manager in managers)
        return PackageInventory(timestamp=time.time(), total_packages=total_packages, managers=managers)

    def _collect_npm(self) -> PackageManagerInventory:
        command = self._resolve_command("npm", ["/opt/homebrew/bin/npm", "/usr/local/bin/npm", "/usr/bin/npm"])
        if not command:
            return self._missing_manager("npm")

        payload, error = self._run_json([command, "list", "-g", "--depth=0", "--json"])
        if error:
            return self._failed_manager("npm", command, error)

        raw_dependencies = payload.get("dependencies")
        if not isinstance(raw_dependencies, dict):
            return self._failed_manager("npm", command, "Unexpected npm output: dependencies map missing.")

        packages = [
            PackageRecord(
                manager="npm",
                name=name,
                version=str(details.get("version", "unknown")) if isinstance(details, dict) else "unknown",
                source="global",
            )
            for name, details in raw_dependencies.items()
        ]
        packages.sort(key=lambda package: package.name.lower())
        return self._ready_manager("npm", command, packages)

    def _collect_brew(self) -> PackageManagerInventory:
        command = self._resolve_command("brew", ["/opt/homebrew/bin/brew", "/usr/local/bin/brew"])
        if not command:
            return self._missing_manager("brew")

        formula_lines, formula_error = self._run_lines([command, "list", "--formula", "--versions"])
        if formula_error:
            return self._failed_manager("brew", command, formula_error)

        cask_lines, cask_error = self._run_lines([command, "list", "--cask", "--versions"])
        if cask_error:
            return self._failed_manager("brew", command, cask_error)

        packages = [
            *self._parse_brew_lines(formula_lines, source="formula"),
            *self._parse_brew_lines(cask_lines, source="cask"),
        ]
        packages.sort(key=lambda package: (package.source, package.name.lower()))
        return self._ready_manager("brew", command, packages)

    def _collect_pip(self) -> PackageManagerInventory:
        command = self._resolve_python_command()
        if not command:
            return self._missing_manager("pip")

        payload, error = self._run_json([command, "-m", "pip", "list", "--format=json"])
        if error:
            return self._failed_manager("pip", f"{command} -m pip", error)

        packages = self._parse_python_packages(payload, manager="pip", source="environment")
        if packages is None:
            return self._failed_manager("pip", f"{command} -m pip", "Unexpected pip output: expected a JSON array.")
        return self._ready_manager("pip", f"{command} -m pip", packages)

    def _collect_uv(self) -> PackageManagerInventory:
        command = self._resolve_command("uv", ["/opt/homebrew/bin/uv", "/usr/local/bin/uv"])
        if not command:
            return self._missing_manager("uv")

        payload, error = self._run_json([command, "pip", "list", "--format", "json"])
        if error:
            return self._failed_manager("uv", command, error)

        packages = self._parse_python_packages(payload, manager="uv", source="environment")
        if packages is None:
            return self._failed_manager("uv", command, "Unexpected uv output: expected a JSON array.")
        return self._ready_manager("uv", command, packages)

    @staticmethod
    def _missing_manager(manager: str) -> PackageManagerInventory:
        return PackageManagerInventory(
            manager=manager,
            available=False,
            error=f"{manager} is not available on the host PATH.",
        )

    @staticmethod
    def _failed_manager(manager: str, command: Optional[str], error: str) -> PackageManagerInventory:
        return PackageManagerInventory(
            manager=manager,
            available=False,
            command=command,
            error=error,
        )

    @staticmethod
    def _ready_manager(
        manager: str,
        command: Optional[str],
        packages: list[PackageRecord],
    ) -> PackageManagerInventory:
        return PackageManagerInventory(
            manager=manager,
            available=True,
            command=command,
            package_count=len(packages),
            packages=packages,
        )

    @staticmethod
    def _resolve_command(command: str, fallbacks: Sequence[str]) -> Optional[str]:
        direct = shutil.which(command)
        if direct:
            return direct

        for path in fallbacks:
            candidate = Path(path)
            if candidate.exists() and candidate.is_file():
                return str(candidate)
        return None

    @staticmethod
    def _resolve_python_command() -> Optional[str]:
        current = Path(sys.executable)
        if current.exists() and current.is_file():
            return str(current)

        fallback = shutil.which("python3")
        if fallback:
            return fallback
        return shutil.which("python")

    @staticmethod
    def _run_json(command: list[str]) -> tuple[Any, Optional[str]]:
        try:
            result = subprocess.run(command, capture_output=True, text=True, check=False)
        except OSError as exc:
            return None, str(exc)

        if result.returncode != 0:
            stderr = result.stderr.strip()
            stdout = result.stdout.strip()
            return None, stderr or stdout or f"Command exited with status {result.returncode}."

        try:
            return json.loads(result.stdout), None
        except json.JSONDecodeError as exc:
            return None, f"Failed to parse JSON output: {exc}"

    @staticmethod
    def _run_lines(command: list[str]) -> tuple[list[str], Optional[str]]:
        try:
            result = subprocess.run(command, capture_output=True, text=True, check=False)
        except OSError as exc:
            return [], str(exc)

        if result.returncode != 0:
            stderr = result.stderr.strip()
            stdout = result.stdout.strip()
            return [], stderr or stdout or f"Command exited with status {result.returncode}."

        return [line.strip() for line in result.stdout.splitlines() if line.strip()], None

    @staticmethod
    def _parse_brew_lines(lines: list[str], source: str) -> list[PackageRecord]:
        packages: list[PackageRecord] = []
        for line in lines:
            name, _, versions = line.partition(" ")
            packages.append(
                PackageRecord(
                    manager="brew",
                    name=name,
                    version=versions.strip() or "installed",
                    source=source,
                )
            )
        return packages

    @staticmethod
    def _parse_python_packages(payload: Any, manager: str, source: str) -> Optional[list[PackageRecord]]:
        if not isinstance(payload, list):
            return None

        packages: list[PackageRecord] = []
        for item in payload:
            if not isinstance(item, dict):
                continue

            name = item.get("name")
            version = item.get("version")
            if not isinstance(name, str) or not name:
                continue

            packages.append(
                PackageRecord(
                    manager=manager,
                    name=name,
                    version=str(version) if version is not None else "unknown",
                    source=source,
                )
            )

        packages.sort(key=lambda package: package.name.lower())
        return packages
