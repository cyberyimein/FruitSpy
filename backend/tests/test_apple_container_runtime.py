from __future__ import annotations

import json
import subprocess
import unittest

from app.services.apple_container_runtime import AppleContainerRuntime


class SequenceRunner:
    def __init__(self, results: list[subprocess.CompletedProcess[str]]) -> None:
        self.results = list(results)
        self.calls: list[list[str]] = []

    def __call__(self, command: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        self.calls.append(command)
        if not self.results:
            raise AssertionError(f"unexpected command: {command}")
        return self.results.pop(0)


def completed(stdout: str = "", stderr: str = "", returncode: int = 0) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr=stderr)


def container_list_payload() -> str:
    return json.dumps(
        [
            {
                "id": "web",
                "configuration": {
                    "id": "web",
                    "image": {"reference": "docker.io/library/nginx:latest"},
                    "resources": {"cpus": 2, "memoryInBytes": 1_073_741_824},
                },
                "status": {"state": "running"},
            },
            {
                "id": "worker",
                "configuration": {
                    "id": "worker",
                    "image": {"reference": "example/worker:latest"},
                    "resources": {"cpus": 1, "memoryInBytes": 536_870_912},
                },
                "status": {"state": "stopped"},
            },
        ]
    )


class AppleContainerRuntimeTests(unittest.TestCase):
    def test_collects_containers_and_calculates_cpu_from_consecutive_samples(self) -> None:
        runner = SequenceRunner(
            [
                completed(container_list_payload()),
                completed(
                    json.dumps(
                        [
                            {
                                "id": "web",
                                "cpuUsageUsec": 1_000_000,
                                "memoryUsageBytes": 134_217_728,
                                "memoryLimitBytes": 1_073_741_824,
                            }
                        ]
                    )
                ),
                completed(container_list_payload()),
                completed(
                    json.dumps(
                        [
                            {
                                "id": "web",
                                "cpuUsageUsec": 2_000_000,
                                "memoryUsageBytes": 268_435_456,
                                "memoryLimitBytes": 1_073_741_824,
                            }
                        ]
                    )
                ),
            ]
        )
        clock_values = iter([10.0, 12.0])
        runtime = AppleContainerRuntime(
            cli_path="/usr/bin/true",
            auto_start=False,
            runner=runner,
            clock=lambda: next(clock_values),
        )

        first, available, error = runtime.collect()
        second, second_available, second_error = runtime.collect()

        self.assertTrue(available)
        self.assertTrue(second_available)
        self.assertIsNone(error)
        self.assertIsNone(second_error)
        self.assertEqual([container.id for container in first], ["web", "worker"])
        self.assertEqual(first[0].cpu_percent, 0.0)
        self.assertEqual(second[0].cpu_percent, 50.0)
        self.assertEqual(second[0].cpu_limit, 2.0)
        self.assertEqual(second[0].memory_percent, 25.0)
        self.assertEqual(second[0].memory_used_mb, 256.0)
        self.assertEqual(second[0].memory_limit_mb, 1024.0)
        self.assertEqual(second[1].status, "stopped")
        self.assertEqual(second[1].cpu_limit, 1.0)
        self.assertEqual(second[1].memory_limit_mb, 512.0)

    def test_starts_system_service_and_retries_list(self) -> None:
        runner = SequenceRunner(
            [
                completed(stderr="service unavailable", returncode=1),
                completed(),
                completed("[]"),
            ]
        )
        runtime = AppleContainerRuntime(
            cli_path="/usr/bin/true",
            auto_start=True,
            runner=runner,
        )

        containers, available, error = runtime.collect()

        self.assertEqual(containers, [])
        self.assertTrue(available)
        self.assertIsNone(error)
        self.assertEqual(runner.calls[1][1:], ["system", "start"])

    def test_hides_internal_builder_containers(self) -> None:
        payload = json.loads(container_list_payload())
        payload.append(
            {
                "id": "buildkit",
                "configuration": {
                    "id": "buildkit",
                    "image": {"reference": "ghcr.io/apple/container-builder-shim/builder:0.12.0"},
                    "labels": {
                        "com.apple.container.plugin": "builder",
                        "com.apple.container.resource.role": "builder",
                    },
                },
                "status": {"state": "stopped"},
            }
        )
        runner = SequenceRunner([completed(json.dumps(payload)), completed("[]")])
        runtime = AppleContainerRuntime(
            cli_path="/usr/bin/true",
            auto_start=False,
            runner=runner,
        )

        containers, available, error = runtime.collect()

        self.assertTrue(available)
        self.assertIsNone(error)
        self.assertEqual([container.id for container in containers], ["web", "worker"])

    def test_logs_and_control_use_apple_container_commands(self) -> None:
        runner = SequenceRunner(
            [
                completed("first line\nsecond line\n"),
                completed(),
                completed(),
            ]
        )
        runtime = AppleContainerRuntime(
            cli_path="/usr/bin/true",
            auto_start=False,
            runner=runner,
        )

        logs = runtime.logs("web", lines=50)
        result = runtime.control("web", "restart")

        self.assertEqual(logs["lines"], ["first line", "second line"])
        self.assertTrue(result["ok"])
        self.assertEqual(runner.calls[0][1:], ["logs", "-n", "50", "web"])
        self.assertEqual(runner.calls[1][1:], ["stop", "web"])
        self.assertEqual(runner.calls[2][1:], ["start", "web"])

    def test_rejects_invalid_container_ids_before_running_commands(self) -> None:
        runner = SequenceRunner([])
        runtime = AppleContainerRuntime(
            cli_path="/usr/bin/true",
            auto_start=False,
            runner=runner,
        )

        logs = runtime.logs("--debug")
        with self.assertRaisesRegex(ValueError, "invalid container ID"):
            runtime.control("../web", "stop")
        internal_logs = runtime.logs("buildkit")
        with self.assertRaisesRegex(ValueError, "internal containers"):
            runtime.control("buildkit", "start")

        self.assertEqual(logs, {"error": "invalid container ID"})
        self.assertEqual(
            internal_logs,
            {"error": "internal containers are not exposed by FruitSpy"},
        )
        self.assertEqual(runner.calls, [])

    def test_reports_missing_cli_without_raising(self) -> None:
        runtime = AppleContainerRuntime(
            cli_path="/path/that/does/not/exist",
            auto_start=False,
        )

        containers, available, error = runtime.collect()

        self.assertEqual(containers, [])
        self.assertFalse(available)
        self.assertIn("CLI was not found", error or "")


if __name__ == "__main__":
    unittest.main()
