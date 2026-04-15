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

from palace_format_detector import (  # type: ignore
    CLASS_CHROMA_0_6,
    CLASS_CHROMA_1_X,
    CLASS_UNKNOWN,
    MANIFEST_FILENAME,
    detect_palace_format,
)


class PalaceFormatDetectorTests(unittest.TestCase):
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

    def test_manifest_compatibility_line_detects_chroma_0_6(self) -> None:
        palace = self.root / "palace"
        self._write_manifest(
            palace,
            {
                "compatibility_line": "chromadb-0.6.x",
                "chromadb_version": "0.6.3",
            },
        )

        result = detect_palace_format(palace)

        self.assertEqual(result.classification, CLASS_CHROMA_0_6)
        self.assertEqual(result.confidence, "high")
        self.assertEqual(result.evidence[0].source, "manifest")

    def test_manifest_version_detects_chroma_1_x(self) -> None:
        palace = self.root / "palace"
        self._write_manifest(
            palace,
            {
                "compatibility_line": "custom-exploration-line",
                "chromadb_version": "1.5.7",
            },
        )

        result = detect_palace_format(palace)

        self.assertEqual(result.classification, CLASS_CHROMA_1_X)
        self.assertEqual(result.confidence, "high")

    def test_manifest_conflict_resolves_to_unknown(self) -> None:
        palace = self.root / "palace"
        self._write_manifest(
            palace,
            {
                "compatibility_line": "chromadb-0.6.x",
                "chromadb_version": "1.5.7",
            },
        )

        result = detect_palace_format(palace)

        self.assertEqual(result.classification, CLASS_UNKNOWN)
        self.assertIn("conflict", result.evidence[0].detail)

    def test_structural_typed_configs_detect_chroma_0_6(self) -> None:
        palace = self.root / "palace"
        self._write_sqlite(
            palace,
            [
                json.dumps({"_type": "CollectionConfigurationInternal"}),
                json.dumps({"_type": "CollectionConfigurationInternal"}),
            ],
        )

        result = detect_palace_format(palace)

        self.assertEqual(result.classification, CLASS_CHROMA_0_6)
        self.assertEqual(result.confidence, "medium")
        self.assertEqual(result.evidence[0].source, "structure")

    def test_structural_untyped_configs_stay_unknown(self) -> None:
        palace = self.root / "palace"
        self._write_sqlite(palace, ["{}", "{}"])

        result = detect_palace_format(palace)

        self.assertEqual(result.classification, CLASS_UNKNOWN)
        self.assertIn("ambiguous", result.evidence[0].detail)

    def test_structural_mixed_configs_stay_unknown(self) -> None:
        palace = self.root / "palace"
        self._write_sqlite(
            palace,
            [
                json.dumps({"_type": "CollectionConfigurationInternal"}),
                "{}",
            ],
        )

        result = detect_palace_format(palace)

        self.assertEqual(result.classification, CLASS_UNKNOWN)
        self.assertIn("mix", result.evidence[0].detail)


if __name__ == "__main__":
    unittest.main()
