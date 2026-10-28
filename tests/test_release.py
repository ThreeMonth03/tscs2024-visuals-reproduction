"""Negative tests for publication gates, using only temporary synthetic files."""
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

from ci.check_release import validate


class ReleaseInventoryTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        (self.root / "ci").mkdir()
        (self.root / "references").mkdir()
        self.write_json("manifest.json", {"data_included": False, "files": {"result.csv": {}}})
        self.write_json("references/publication_manifest.json", {"files": []})
        self.write_json("ci/release_files.json", {"schema_version": 1, "support_files": ["ci/release_files.json"]})
        (self.root / "result.csv").write_text("group,estimate\nall,0.5\n", encoding="utf-8")
        subprocess.run(["git", "init", "--quiet"], cwd=self.root, check=True)
        self.stage()

    def write_json(self, relative, value):
        (self.root / relative).write_text(json.dumps(value), encoding="utf-8")

    def stage(self):
        subprocess.run(["git", "add", "."], cwd=self.root, check=True)

    def test_reviewed_aggregate_files_pass(self):
        self.assertEqual(validate(self.root)["status"], "pass")

    def test_extra_tracked_file_is_rejected(self):
        (self.root / "unreviewed.csv").write_text("sample,value\n1,2\n", encoding="utf-8")
        self.stage()
        with self.assertRaisesRegex(ValueError, "unreviewed.csv"):
            validate(self.root)

    def test_individual_columns_are_rejected_even_in_known_path(self):
        (self.root / "result.csv").write_text("respondent_id,value\n1,2\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "Individual-data columns"):
            validate(self.root)

    def test_raw_format_cannot_be_added_to_allowlist(self):
        (self.root / "records.sav").write_bytes(b"$FL2synthetic test")
        self.write_json("ci/release_files.json", {"schema_version": 1, "support_files": ["ci/release_files.json", "records.sav"]})
        self.stage()
        with self.assertRaisesRegex(ValueError, "format is not permitted"):
            validate(self.root)

    def test_path_escape_is_rejected(self):
        self.write_json("manifest.json", {"data_included": False, "files": {"../outside.csv": {}}})
        with self.assertRaises(ValueError):
            validate(self.root)

    def test_symlink_is_rejected(self):
        target = self.root / "result.csv"
        target.unlink()
        target.symlink_to(self.root / "manifest.json")
        with self.assertRaisesRegex(ValueError, "symlink"):
            validate(self.root)

    def test_untracked_local_file_is_not_read(self):
        (self.root / "local.csv").write_text("respondent_id,value\n1,2\n", encoding="utf-8")
        self.assertEqual(validate(self.root)["status"], "pass")

    def test_executed_notebook_cannot_be_published(self):
        self.write_json("ci/release_files.json", {"schema_version": 1, "support_files": ["ci/release_files.json", "example.ipynb"]})
        for extra in ({"outputs": [{"text": "private output"}]}, {"execution_count": 1},
                      {"attachments": {"image": {"image/png": "test"}}}):
            self.write_json("example.ipynb", {"cells": [{"cell_type": "code", "outputs": [], "execution_count": None, **extra}]})
            self.stage()
            with self.subTest(extra=extra), self.assertRaisesRegex(ValueError, "Notebook execution output"):
                validate(self.root)

    def test_clean_notebook_can_be_published(self):
        self.write_json("ci/release_files.json", {"schema_version": 1, "support_files": ["ci/release_files.json", "example.ipynb"]})
        self.write_json("example.ipynb", {"cells": [{"cell_type": "code", "source": ["print('hello')"], "outputs": [], "execution_count": None}]})
        self.stage()
        self.assertEqual(validate(self.root)["status"], "pass")


if __name__ == "__main__":
    unittest.main()
