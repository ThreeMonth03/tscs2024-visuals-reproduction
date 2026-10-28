"""Download bundles contain only verified aggregate tables and figure files."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

from helpers.notebook_exports import FIGURES, TABLES, export_results


class NotebookExportTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        base = Path(self.temporary.name).resolve()
        self.root, self.output = base / "repo", base / "analysis-run"
        self.downloads = self.root / "notebooks/downloads"
        self.root.mkdir()
        self.output.mkdir()
        self.profiles = ("estimate_id,estimate\n"
                         + "".join(f"group-{i},0.2\n" for i in range(258))).encode()
        for relative in TABLES:
            content = self.profiles if relative == TABLES[0] else b"estimate_id,estimate\nall,0.2\n"
            self.write(self.root / "aggregates" / relative, content)
        inventory = {}
        for name in FIGURES:
            hashes = {}
            for suffix, signature in (("png", b"\x89PNG\r\n\x1a\n"), ("pdf", b"%PDF-1.4\n")):
                content = signature + name.encode()
                self.write(self.output / f"figures/{name}.{suffix}", content)
                hashes[f"{name}.{suffix}"] = hashlib.sha256(content).hexdigest()
            inventory[name] = {"files": hashes}
        self.write(self.output / "figures/selected_profiles.csv", self.profiles)
        self.manifest = {"status": "pass", "figures": inventory, "figure_count": 9,
                         "selected_rows": 258, "font": {"resolved_file": "/private/font.otf"},
                         "selected_profiles_sha256": hashlib.sha256(self.profiles).hexdigest()}
        self.write_json(self.output / "figures/figures_manifest.json", self.manifest)
        self.report = {"status": "pass", "mode": "aggregate",
                       "statistical_reestimation": False, "input_estimates": "published_aggregates",
                       "figure_count": 9, "figure_files": [f"figures/{name}.png" for name in FIGURES]}
        self.write_json(self.output / "notebook_report.json", self.report)
        self.inventory = {"files": {
            "aggregates/" + relative: {"sha256": hashlib.sha256(
                (self.root / "aggregates" / relative).read_bytes()).hexdigest()}
            for relative in TABLES}}
        self.write_json(self.root / "manifest.json", self.inventory)

    @staticmethod
    def write(path, content):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)

    def write_json(self, path, value):
        self.write(path, json.dumps(value).encode())

    def test_exports_fixed_inventory_and_excludes_extra_files(self):
        self.write(self.output / "unlisted/people.csv", b"respondent_id\n123\n")
        self.write(self.output / "figures/extra.csv", b"respondent_id\n123\n")
        self.write(self.output / "raw.sav", b"$FL2private")
        self.write(self.output / "logs/private.log", b"secret path /private/input.sav")
        result = export_results(self.root, self.output, self.downloads)
        with zipfile.ZipFile(result["zip_path"]) as archive:
            names = archive.namelist()
            self.assertEqual(set(names), set(result["files"]))
            self.assertEqual(len(names), 32)
            self.assertEqual(sum(name.endswith(".png") for name in names), 9)
            self.assertEqual(sum(name.endswith(".pdf") for name in names), 9)
            self.assertEqual(sum(name.startswith("tables/") for name in names), 10)
            self.assertFalse(any("unlisted/" in name or "logs/" in name for name in names))
            self.assertNotIn("figures/figures_manifest.json", names)
            self.assertNotIn("notebook_report.json", names)
            self.assertTrue(all(b"/private/" not in archive.read(name) for name in names))
            summary = json.loads(archive.read("summary.json"))
            self.assertEqual(summary["mode"], "aggregate")
            self.assertFalse(summary["statistical_reestimation"])
            self.assertEqual(archive.read("figures/selected_profiles.csv"), self.profiles)
            self.assertEqual(archive.read("index.html"), result["index_path"].read_bytes())
            self.assertIn(b'<html lang="en">', archive.read("index.html"))
            self.assertIn(b"Generational Differences in Sharing Visuals by Phone", archive.read("README.txt"))
            self.assertIn(b"refers to photos and videos", archive.read("README.txt"))
            self.assertNotRegex(archive.read("README.txt").decode(), r"[\u4e00-\u9fff]")
            self.assertNotRegex(archive.read("index.html").decode(), r"[\u4e00-\u9fff]")
        self.assertIn('src="figures/age_frequency.png"', result["index_path"].read_text())

    def test_survey_export_uses_fresh_tables_and_excludes_input_material(self):
        fresh_inventory = {}
        for relative in TABLES:
            data = (self.root / "aggregates" / relative).read_bytes().replace(b"0.2", b"0.4")
            self.write(self.output / "analysis/aggregates" / relative, data)
            fresh_inventory[relative] = {"sha256": hashlib.sha256(data).hexdigest(),
                                         "rows": 258 if relative == TABLES[0] else 1}
        self.write_json(self.output / "aggregate_manifest.json", {"status": "pass", "tables": fresh_inventory})
        selected = self.profiles.replace(b"0.2", b"0.4")
        self.write(self.output / "figures/selected_profiles.csv", selected)
        self.manifest["selected_profiles_sha256"] = hashlib.sha256(selected).hexdigest()
        self.write_json(self.output / "figures/figures_manifest.json", self.manifest)
        self.write_json(self.output / "notebook_report.json", {
            **self.report, "mode": "survey", "statistical_reestimation": True,
            "input_estimates": "uploaded_survey", "artificial_data": True, "calibration_available": False})
        self.write(self.output / "analysis/survey.sav", b"$FL2private")
        self.write(self.output / "analysis/profile.json", b'{"private": "mapping"}')
        result = export_results(self.root, self.output, self.downloads)
        with zipfile.ZipFile(result["zip_path"]) as archive:
            self.assertEqual(len(archive.namelist()), 32)
            self.assertEqual(archive.read("tables/" + TABLES[0]), selected)
            self.assertNotIn(b"0.2", archive.read("tables/" + TABLES[0]))
            self.assertFalse(any(name.endswith(".sav") or "profile.json" in name for name in archive.namelist()))
            self.assertTrue(json.loads(archive.read("summary.json"))["statistical_reestimation"])
            self.assertIn(b"recalculated from the user-selected survey file", archive.read("index.html"))
            self.assertIn(b"Artificial demonstration data", archive.read("index.html"))
            self.assertIn(b"targets were not supplied", archive.read("index.html"))
            self.assertTrue(json.loads(archive.read("summary.json"))["artificial_data"])
            self.assertFalse(json.loads(archive.read("summary.json"))["calibration_available"])

    def test_partial_or_inconsistent_notebook_run_is_rejected(self):
        for change in ({"status": "partial"}, {"statistical_reestimation": True},
                       {"mode": "unknown"}, {"figure_files": []}, {"input_estimates": "unverified_results"}):
            with self.subTest(change=change):
                self.write_json(self.output / "notebook_report.json", {**self.report, **change})
                with self.assertRaisesRegex(ValueError, "completed, consistent"):
                    export_results(self.root, self.output, self.downloads)
                self.assertFalse(self.downloads.exists())

    def test_figure_content_or_signature_changes_are_rejected(self):
        path = self.output / "figures/age_frequency.png"
        self.write(path, b"\x89PNG\r\n\x1a\nchanged")
        with self.assertRaisesRegex(ValueError, "changed figure"):
            export_results(self.root, self.output, self.downloads)
        self.write(path, b"$FL2private")
        self.manifest["figures"]["age_frequency"]["files"]["age_frequency.png"] = hashlib.sha256(path.read_bytes()).hexdigest()
        self.write_json(self.output / "figures/figures_manifest.json", self.manifest)
        with self.assertRaisesRegex(ValueError, "Invalid or changed figure"):
            export_results(self.root, self.output, self.downloads)
        self.assertFalse(self.downloads.exists())

    def test_individual_columns_are_rejected_even_at_an_allowed_name(self):
        self.write(self.root / "aggregates" / TABLES[-1], b"respondent_id,estimate\n123,0.2\n")
        with self.assertRaisesRegex(ValueError, "Individual-data columns"):
            export_results(self.root, self.output, self.downloads)
        self.assertFalse(self.downloads.exists())

    def test_aggregate_changes_are_rejected(self):
        target = self.root / "aggregates" / TABLES[-1]
        for content in (b"group,estimate\nall,0.2\n", b"estimate_id,estimate\nall,0.3\n"):
            with self.subTest(content=content):
                self.write(target, content)
                with self.assertRaisesRegex(ValueError, "differs from the published inventory"):
                    export_results(self.root, self.output, self.downloads)
        self.assertFalse(self.downloads.exists())

    def test_selected_profiles_must_have_expected_rows_and_hash(self):
        self.write(self.output / "figures/selected_profiles.csv", b"estimate_id,estimate\nall,0.2\n")
        with self.assertRaisesRegex(ValueError, "selected aggregate profiles"):
            export_results(self.root, self.output, self.downloads)
        self.assertFalse(self.downloads.exists())

    def test_missing_figure_is_rejected_before_creating_downloads(self):
        (self.output / "figures/age_frequency.pdf").unlink()
        with self.assertRaises(FileNotFoundError):
            export_results(self.root, self.output, self.downloads)
        self.assertFalse(self.downloads.exists())

    def test_symlink_source_or_destination_is_rejected(self):
        source = self.output / "figures/age_frequency.png"
        other = self.output / "real-image.png"
        source.rename(other)
        source.symlink_to(other)
        with self.assertRaisesRegex(ValueError, "symlinks"):
            export_results(self.root, self.output, self.downloads)
        source.unlink()
        other.rename(source)
        external = self.output.parent / "elsewhere"
        external.mkdir()
        self.downloads.parent.mkdir(parents=True)
        self.downloads.symlink_to(external, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "symlinks"):
            export_results(self.root, self.output, self.downloads)
        self.assertEqual(list(external.iterdir()), [])

    def test_parent_traversal_and_overlapping_directories_are_rejected(self):
        for destination in (self.downloads / ".." / "other", self.output / "downloads"):
            with self.subTest(destination=destination):
                with self.assertRaises(ValueError):
                    export_results(self.root, self.output, destination)

    def test_repeated_exports_preserve_earlier_bundle(self):
        first = export_results(self.root, self.output, self.downloads)
        original = first["zip_path"].read_bytes()
        second = export_results(self.root, self.output, self.downloads)
        self.assertNotEqual(first["directory"], second["directory"])
        self.assertEqual(first["zip_path"].read_bytes(), original)
        self.assertTrue(second["zip_path"].is_file())


if __name__ == "__main__":
    unittest.main()
