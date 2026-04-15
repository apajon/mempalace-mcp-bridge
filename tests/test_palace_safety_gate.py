from __future__ import annotations

import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from palace_format_detector import MANIFEST_FILENAME  # type: ignore
from palace_safety_gate import evaluate_palace_safety  # type: ignore


class PalaceSafetyGateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def _write_manifest(self, palace: Path, payload: dict[str, object]) -> None:
        palace.mkdir(parents=True, exist_ok=True)
        (palace / MANIFEST_FILENAME).write_text(json.dumps(payload), encoding="utf-8")

    def _write_sqlite(self, palace: Path, config_values: list[str]) -> None:
        palace.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(palace / "chroma.sqlite3")
        cur = conn.cursor()
        cur.execute("CREATE TABLE collections (config_json_str TEXT)")
        cur.executemany(
            "INSERT INTO collections (config_json_str) VALUES (?)",
            [(value,) for value in config_values],
        )
        conn.commit()
        conn.close()

    def test_supported_0_6_palace_is_allowed(self) -> None:
        palace = self.root / "palace"
        self._write_manifest(
            palace,
            {"compatibility_line": "chromadb-0.6.x", "chromadb_version": "0.6.3"},
        )
        self._write_sqlite(
            palace,
            [json.dumps({"_type": "CollectionConfigurationInternal"})],
        )

        result = evaluate_palace_safety(palace, "read")

        self.assertTrue(result.allowed)
        self.assertEqual(result.classification, "chroma_0_6")

    def test_explicit_1_x_palace_is_blocked(self) -> None:
        palace = self.root / "palace"
        self._write_manifest(
            palace,
            {"compatibility_line": "chromadb-1.x", "chromadb_version": "1.5.7"},
        )
        self._write_sqlite(palace, ["{}"])

        result = evaluate_palace_safety(palace, "write")

        self.assertFalse(result.allowed)
        self.assertEqual(result.classification, "chroma_1_x")
        self.assertIn("stable bridge only opens chroma_0_6", result.message)

    def test_unknown_existing_palace_is_blocked(self) -> None:
        palace = self.root / "palace"
        self._write_sqlite(palace, ["{}"])

        result = evaluate_palace_safety(palace, "repair")

        self.assertFalse(result.allowed)
        self.assertEqual(result.classification, "unknown")
        self.assertIn("Refusing to repair", result.message)

    def test_missing_palace_database_is_allowed(self) -> None:
        palace = self.root / "palace"
        palace.mkdir(parents=True, exist_ok=True)

        result = evaluate_palace_safety(palace, "create")

        self.assertTrue(result.allowed)
        self.assertEqual(result.classification, "unknown")
        self.assertIn("No existing palace database detected", result.message)


if __name__ == "__main__":
    unittest.main()
