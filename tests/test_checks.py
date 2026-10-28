"""Regression tests for bad aggregate data and incomplete reference records."""
from contextlib import redirect_stdout
import copy
import hashlib
import importlib.util
import io
import json
import math
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


def load_check(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "ci" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


aggregates = load_check("check_aggregates")
references = load_check("check_references")


class FamilyTests(unittest.TestCase):
    def family(self):
        # For three tests, m*H_m=5.5. Missing tests still occupy a family slot.
        return [
            {"id": "one", "status": "estimated", "p_value": ".01", "q": ".055"},
            {"id": "two", "status": "estimated", "p_value": ".03", "q": ".0825"},
            {"id": "three", "status": "unestimable", "p_value": "nan", "q": "nan"},
        ]

    def test_fixed_family_retains_unestimable_slot(self):
        self.assertLess(aggregates.check_family(self.family(), 3, "id", "q"), 1e-14)

    def test_wrong_by_adjustment_is_rejected(self):
        rows = self.family()
        rows[0]["q"] = ".06"
        with self.assertRaisesRegex(ValueError, "Numeric mismatch"):
            aggregates.check_family(rows, 3, "id", "q")

    def test_estimated_p_must_be_finite_probability(self):
        for value in ("nan", "inf", "-inf", "1.1", "-.1"):
            with self.subTest(value=value):
                rows = self.family()
                rows[0]["p_value"], rows[0]["q"] = value, "1"
                with self.assertRaisesRegex(ValueError, "finite p"):
                    aggregates.check_family(rows, 3, "id", "q")

    def test_failed_test_cannot_contribute_finite_p(self):
        rows = self.family()
        rows[2]["p_value"] = ".001"
        with self.assertRaisesRegex(ValueError, "Unestimable p and q"):
            aggregates.check_family(rows, 3, "id", "q")

    def test_infinity_does_not_pass_numeric_comparison(self):
        with self.assertRaisesRegex(ValueError, "Nonfinite"):
            aggregates.near(math.inf, math.inf, "invalid estimate")


class ProfileTests(unittest.TestCase):
    def profiles(self):
        common = {"outcome": "example", "area": "0", "factor": "all", "level": "0", "n": "10"}
        return [
            {**common, "estimate_id": "a", "category": "0", "event_n": "4", "estimate": ".4"},
            {**common, "estimate_id": "b", "category": "1", "event_n": "6", "estimate": ".6"},
        ]

    def test_complete_categories_pass(self):
        aggregates.check_profiles(self.profiles(), expected_count=2)

    def test_event_count_cannot_exceed_denominator(self):
        rows = self.profiles()
        rows[0]["event_n"] = "11"
        with self.assertRaisesRegex(ValueError, "Invalid event count"):
            aggregates.check_profiles(rows, expected_count=2)

    def test_category_denominators_must_match(self):
        rows = self.profiles()
        rows[0]["n"] = "11"
        with self.assertRaisesRegex(ValueError, "Category denominators differ"):
            aggregates.check_profiles(rows, expected_count=2)

    def test_categories_must_cover_denominator(self):
        rows = self.profiles()
        rows[0]["event_n"] = "3"
        with self.assertRaisesRegex(ValueError, "do not sum"):
            aggregates.check_profiles(rows, expected_count=2)


class SensitivityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        directory = ROOT / "aggregates/contrasts"
        cls.scenarios = aggregates.read_csv(directory / "all_scenarios.csv")
        cls.summary = aggregates.read_csv(directory / "contrast_summary.csv")

    def test_published_summary_passes(self):
        aggregates.check_sensitivity(self.scenarios, self.summary)

    def test_changed_support_flag_is_rejected(self):
        summary = copy.deepcopy(self.summary)
        summary[0]["supported_all_checks"] = str(summary[0]["supported_all_checks"] != "True")
        with self.assertRaisesRegex(ValueError, "support flag mismatch"):
            aggregates.check_sensitivity(self.scenarios, summary)

    def test_changed_deletion_count_is_rejected(self):
        summary = copy.deepcopy(self.summary)
        summary[0]["deletion_significant"] = str(int(summary[0]["deletion_significant"]) + 1)
        with self.assertRaisesRegex(ValueError, "Deletion significance mismatch"):
            aggregates.check_sensitivity(self.scenarios, summary)

    def test_duplicate_summary_id_is_rejected(self):
        summary = copy.deepcopy(self.summary)
        summary[1]["contrast_id"] = summary[0]["contrast_id"]
        with self.assertRaisesRegex(ValueError, "summary count"):
            aggregates.check_sensitivity(self.scenarios, summary)


class ReferenceTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        (self.root / "pdfs").mkdir()
        self.pdf = b"%PDF-1.7\nsynthetic integrity-test fixture\n"
        (self.root / "pdfs/test.pdf").write_bytes(self.pdf)
        self.catalog = [{"key": f"ref{index}", "official_url": "https://example.org/article"}
                        for index in range(23)]
        self.catalog[0].update(local_pdf="pdfs/test.pdf", redistribution_license="CC-BY-4.0",
                               license_evidence_url="https://example.org/license",
                               sha256=hashlib.sha256(self.pdf).hexdigest())
        self.bibliography = "\n".join(f"@article{{ref{index},\n title={{Test}},\n}}" for index in range(23))
        self.write_fixture()

    def write_fixture(self):
        (self.root / "references.json").write_text(json.dumps({"references": self.catalog}), encoding="utf-8")
        (self.root / "cited_references.bib").write_text(self.bibliography, encoding="utf-8")
        entries = []
        for relative in ("references.json", "cited_references.bib", "pdfs/test.pdf"):
            data = (self.root / relative).read_bytes()
            entries.append({"path": relative, "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)})
        (self.root / "publication_manifest.json").write_text(json.dumps({"files": entries}), encoding="utf-8")

    def test_import_has_no_filesystem_validation_or_output(self):
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            module = load_check("check_references")
        self.assertEqual(buffer.getvalue(), "")
        self.assertTrue(callable(module.validate))

    def test_complete_attributed_fixture_passes(self):
        self.assertEqual(references.validate(self.root)["redistributable_pdfs"], 1)

    def test_pdf_without_redistribution_evidence_is_rejected(self):
        del self.catalog[0]["license_evidence_url"]
        self.write_fixture()
        with self.assertRaisesRegex(ValueError, "redistribution evidence"):
            references.validate(self.root)

    def test_catalog_pdf_hash_mismatch_is_rejected(self):
        (self.root / "pdfs/test.pdf").write_bytes(self.pdf + b"changed")
        self.write_fixture()  # Inventory matches the file; citation-specific hash must still catch this.
        with self.assertRaisesRegex(ValueError, "catalog hash mismatch"):
            references.validate(self.root)

    def test_bibliography_and_catalog_must_agree(self):
        self.bibliography = self.bibliography.replace("ref22,", "other,")
        self.write_fixture()
        with self.assertRaisesRegex(ValueError, "catalog keys differ"):
            references.validate(self.root)

    def test_unlisted_file_is_rejected(self):
        (self.root / "unreviewed.pdf").write_bytes(self.pdf)
        with self.assertRaisesRegex(ValueError, "publication allowlist"):
            references.validate(self.root)

    def test_traversal_and_symlink_are_rejected(self):
        for relative in ("../outside.pdf", str(self.root / "pdfs/test.pdf")):
            with self.subTest(relative=relative), self.assertRaisesRegex(ValueError, "Invalid reference path"):
                references.local_path(self.root, relative)
        (self.root / "linked.pdf").symlink_to(self.root / "pdfs/test.pdf")
        with self.assertRaisesRegex(ValueError, "Invalid reference path"):
            references.local_path(self.root, "linked.pdf")


if __name__ == "__main__":
    unittest.main()
