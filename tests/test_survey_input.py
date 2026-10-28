"""Exercise actual SAV input handling with artificial, non-study observations."""
from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd
import pyreadstat

from helpers import survey_input
from helpers.survey_demo import make_demo


class SurveyInputTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = tempfile.TemporaryDirectory()
        cls.paths = make_demo(Path(cls.directory.name) / "demo")
        cls.raw, cls.metadata = pyreadstat.read_sav(cls.paths["data_file"])
        cls.profile = json.loads(cls.paths["profile_file"].read_text())

    @classmethod
    def tearDownClass(cls):
        cls.directory.cleanup()

    def setUp(self):
        self.case_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.case_directory.cleanup)
        self.root = Path(self.case_directory.name)

    def load_variant(self, frame=None, profile=None, **sav_options):
        data_file, profile_file = self.root / "input.sav", self.root / "profile.json"
        pyreadstat.write_sav(self.raw if frame is None else frame, data_file, **sav_options)
        profile_file.write_text(json.dumps(self.profile if profile is None else profile))
        return survey_input.load_survey(data_file, profile_file)

    def copied_profile(self):
        return json.loads(json.dumps(self.profile))

    def test_demo_roundtrip_has_complete_background_crossings(self):
        data, receipt = survey_input.load_survey(self.paths["data_file"], self.paths["profile_file"])
        self.assertIs(self.profile["artificial_data"], True)
        self.assertEqual(receipt["observations"], 1728)
        self.assertEqual(receipt["strata"], 4)
        self.assertEqual(receipt["variance_clusters"], 36)
        self.assertEqual(set(data.age_group), set(range(1, 7)))
        self.assertEqual(set(data.education_group), set(range(1, 5)))
        self.assertEqual(set(data.phone_holder), {0.0, 1.0})
        self.assertEqual(len(data.groupby(["cluster", "age_group", "education_group", "sex_group"])), 1728)
        self.assertEqual(len(data.groupby(["area", "age_group", "education_group", "sex_group"])), 96)
        self.assertTrue((data[["primary_weight", "alternative_weight"]] > 0).all().all())
        self.assertTrue(all(name.startswith("demo_") for name in self.metadata.column_names))

    def test_artificial_data_and_targets_are_deterministic(self):
        other = make_demo(self.root / "second")
        other_raw, _ = pyreadstat.read_sav(other["data_file"])
        pd.testing.assert_frame_equal(self.raw, other_raw)
        self.assertEqual(self.paths["profile_file"].read_bytes(), other["profile_file"].read_bytes())
        self.assertEqual(self.paths["calibration_file"].read_bytes(), other["calibration_file"].read_bytes())
        targets = json.loads(other["calibration_file"].read_text())
        for factor, source in [("sex", "demo_sex"), ("age", "demo_age"),
                               ("education", "demo_education"), ("stratum", "demo_stratum")]:
            self.assertAlmostEqual(sum(targets[factor].values()), 1.0)
            for level, value in targets[factor].items():
                expected = self.raw.loc[self.raw[source].eq(int(level)), "demo_alt_weight"].sum()
                self.assertAlmostEqual(value, expected / self.raw.demo_alt_weight.sum())

    def test_demo_does_not_overwrite_or_write_into_source(self):
        with self.assertRaises(FileExistsError):
            make_demo(self.paths["data_file"].parent)
        with self.assertRaisesRegex(ValueError, "outside"):
            make_demo(survey_input.ROOT / "demo-inputs")

    def test_profile_recode_uses_values_not_display_labels(self):
        frame, profile = self.raw.copy(), self.copied_profile()
        frame.demo_age *= 10
        profile["value_maps"]["age_group"] = {str(code * 10): code for code in range(1, 7)}
        data, _ = self.load_variant(frame, profile,
                                   variable_value_labels={"demo_age": {10: "A label, not the numeric code"}})
        self.assertEqual(set(data.age_group), set(range(1, 7)))

    def test_unmapped_values_and_invalid_targets_are_rejected(self):
        frame = self.raw.copy()
        frame.loc[0, "demo_contacts"] = 42
        with self.assertRaisesRegex(ValueError, "Unmapped responses for sharing_with_contacts"):
            self.load_variant(frame)
        profile = self.copied_profile()
        profile["value_maps"]["age_group"]["1"] = True
        with self.assertRaisesRegex(ValueError, "Invalid target categories"):
            self.load_variant(profile=profile)

    def test_sav_and_profile_missing_values_are_respected(self):
        frame = self.raw.copy()
        frame.loc[0, "demo_contacts"] = 99
        data, _ = self.load_variant(frame, missing_ranges={"demo_contacts": [99]})
        self.assertTrue(np.isnan(data.loc[0, "sharing_with_contacts"]))
        profile = self.copied_profile()
        profile["missing_values"]["sharing_with_contacts"] = [99]
        data, _ = self.load_variant(frame, profile)
        self.assertTrue(np.isnan(data.loc[0, "sharing_with_contacts"]))

    def test_invalid_weights_and_missing_background_stop_before_analysis(self):
        for bad in [0.0, -1.0, np.nan, np.inf]:
            with self.subTest(weight=bad):
                frame = self.raw.copy()
                frame.loc[0, "demo_weight"] = bad
                with self.assertRaisesRegex(ValueError, "primary_weight"):
                    self.load_variant(frame)
        frame = self.raw.copy()
        frame.loc[0, "demo_age"] = np.nan
        with self.assertRaisesRegex(ValueError, "Missing age_group"):
            self.load_variant(frame)

    def test_phone_contradictions_and_unclassified_responses_are_rejected(self):
        frame = self.raw.copy()
        frame.loc[0, ["demo_photo", "demo_video"]] = [8, 1]
        with self.assertRaisesRegex(ValueError, "Phone ownership"):
            self.load_variant(frame)
        frame.loc[0, ["demo_photo", "demo_video"]] = np.nan
        with self.assertRaisesRegex(ValueError, "Phone ownership"):
            self.load_variant(frame)

    def test_first_stage_definition_can_select_second_stage_units(self):
        frame, profile = self.raw.copy(), self.copied_profile()
        profile["columns"].pop("cluster")
        profile["columns"]["first_stage_unit"] = "demo_first"
        profile["columns"]["second_stage_unit"] = "demo_second"
        profile["design"]["second_stage_strata"] = [1]
        frame["demo_first"] = frame.demo_cluster
        frame["demo_second"] = frame.demo_cluster + "-V"
        frame.loc[frame.demo_stratum.eq(1), "demo_first"] = "one-town"
        data, receipt = self.load_variant(frame, profile)
        self.assertEqual(receipt["variance_clusters"], 36)
        self.assertTrue(data.loc[data.stratum.eq("1"), "cluster"].str.startswith("1:village:").all())
        self.assertTrue(data.loc[data.stratum.eq("2"), "cluster"].str.startswith("2:psu:").all())
        profile["columns"].pop("second_stage_unit")
        with self.assertRaisesRegex(ValueError, "second_stage_unit"):
            self.load_variant(frame, profile)

    def test_single_cluster_strata_and_missing_source_columns_are_rejected(self):
        frame = self.raw.copy()
        frame.loc[frame.demo_stratum.eq(1), "demo_cluster"] = "single"
        with self.assertRaisesRegex(ValueError, "at least two"):
            self.load_variant(frame)
        profile = self.copied_profile()
        profile["columns"]["primary_weight"] = "missing_column"
        with self.assertRaisesRegex(ValueError, "absent"):
            self.load_variant(profile=profile)

    def test_location_value_labels_are_normalized_before_classification(self):
        frame, profile = self.raw.copy(), self.copied_profile()
        profile["columns"].pop("area")
        profile["columns"]["location"] = "demo_location"
        profile["geography"]["use_value_labels"] = True
        frame["demo_location"] = frame.demo_area * 10
        reference = self.root / "reference_data"
        reference.mkdir()
        (reference / "area_classification.csv").write_text(
            "place,cluster\n臺示範市甲區,1\n臺示範市乙區,4\n", encoding="utf-8")
        with patch.object(survey_input, "ROOT", self.root):
            data, _ = self.load_variant(frame, profile, variable_value_labels={
                "demo_location": {10: "台示範市 甲區", 20: "台示範市乙區"}})
        np.testing.assert_array_equal(data.area, self.raw.demo_area)

    def test_inspection_writes_only_local_metadata_and_an_unconfigured_profile(self):
        output = self.root / "configure.json"
        result = survey_input.inspect_survey(self.paths["data_file"], output)
        self.assertEqual(result["status"], "needs_configuration")
        draft = json.loads(output.read_text())
        self.assertTrue(all(value == "" for value in draft["columns"].values()))
        catalogue = json.loads(Path(result["metadata"]).read_text())
        self.assertEqual(set(catalogue), {"variables", "purpose"})
        self.assertEqual(len(catalogue["variables"]), len(self.raw.columns))
        with self.assertRaises(FileExistsError):
            survey_input.inspect_survey(self.paths["data_file"], output)


if __name__ == "__main__":
    unittest.main()
