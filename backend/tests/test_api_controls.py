from __future__ import annotations

import unittest
from unittest.mock import patch

from fastapi import HTTPException

from app import main


class FakeContainerService:
    def control(self, container_id: str, action: str) -> dict:
        return {"ok": True, "container": container_id, "action": action}


class FailingContainerService:
    def __init__(self, error: Exception) -> None:
        self.error = error

    def control(self, container_id: str, action: str) -> dict:
        raise self.error


class ContainerControlApiTests(unittest.TestCase):
    def test_control_is_disabled_by_default(self) -> None:
        with patch.object(main.RUNTIME_CONFIG, "container_control_enabled", False):
            with self.assertRaises(HTTPException) as raised:
                main.control_container("web", "start", x_fruitspy_control="1")

        self.assertEqual(raised.exception.status_code, 403)
        self.assertEqual(raised.exception.detail, "Container controls are disabled")

    def test_control_requires_fruitspy_header(self) -> None:
        with patch.object(main.RUNTIME_CONFIG, "container_control_enabled", True):
            with self.assertRaises(HTTPException) as raised:
                main.control_container("web", "start", x_fruitspy_control="")

        self.assertEqual(raised.exception.status_code, 403)
        self.assertEqual(raised.exception.detail, "Missing FruitSpy control header")

    def test_control_dispatches_when_enabled_and_header_is_present(self) -> None:
        with (
            patch.object(main.RUNTIME_CONFIG, "container_control_enabled", True),
            patch.object(main, "container_service", FakeContainerService()),
        ):
            result = main.control_container("web", "restart", x_fruitspy_control="1")

        self.assertEqual(result, {"ok": True, "container": "web", "action": "restart"})

    def test_control_maps_validation_and_runtime_errors(self) -> None:
        with (
            patch.object(main.RUNTIME_CONFIG, "container_control_enabled", True),
            patch.object(main, "container_service", FailingContainerService(ValueError("invalid"))),
        ):
            with self.assertRaises(HTTPException) as validation_error:
                main.control_container("web", "restart", x_fruitspy_control="1")

        with (
            patch.object(main.RUNTIME_CONFIG, "container_control_enabled", True),
            patch.object(main, "container_service", FailingContainerService(RuntimeError("busy"))),
        ):
            with self.assertRaises(HTTPException) as runtime_error:
                main.control_container("web", "restart", x_fruitspy_control="1")

        self.assertEqual(validation_error.exception.status_code, 400)
        self.assertEqual(runtime_error.exception.status_code, 409)


if __name__ == "__main__":
    unittest.main()
