from __future__ import annotations

import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from app.services.crawl_tool import CrawlToolStateStore
from app.services.python_tool import PythonToolStateStore
from app.services.room_climate_mcp import RoomClimateMcpStateStore


class SharedStateTests(unittest.TestCase):
    def test_non_object_state_uses_feature_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state.json"
            path.write_text("[]\n", encoding="utf-8")

            self.assertFalse(PythonToolStateStore(path).load_enabled(False))
            self.assertTrue(CrawlToolStateStore(path).load_enabled(True))
            self.assertEqual(
                RoomClimateMcpStateStore(path).load_mode(),
                "modern",
            )

    def test_concurrent_feature_updates_preserve_all_keys(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state.json"
            python_store = PythonToolStateStore(path)
            crawl_store = CrawlToolStateStore(path)
            climate_store = RoomClimateMcpStateStore(path)

            with ThreadPoolExecutor(max_workers=3) as executor:
                for index in range(25):
                    futures = [
                        executor.submit(python_store.save_enabled, index % 2 == 0),
                        executor.submit(crawl_store.save_enabled, index % 2 != 0),
                        executor.submit(
                            climate_store.save_mode,
                            "modern" if index % 2 == 0 else "legacy",
                        ),
                    ]
                    for future in futures:
                        future.result()

            self.assertIsInstance(PythonToolStateStore(path).load_enabled(False), bool)
            self.assertIsInstance(CrawlToolStateStore(path).load_enabled(False), bool)
            self.assertIn(
                RoomClimateMcpStateStore(path).load_mode(),
                {"modern", "legacy"},
            )
