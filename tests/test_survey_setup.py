"""Metadata setup uses meanings, never private source identifiers or guessed codes."""
from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

import pyreadstat

from helpers.survey_demo import make_demo
from helpers import survey_input, survey_setup


class SurveySetupTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = tempfile.TemporaryDirectory()
        paths = make_demo(Path(cls.fixture.name) / "demo")
        cls.raw, cls.metadata = pyreadstat.read_sav(paths["data_file"])
        cls.profile = json.loads(paths["profile_file"].read_text())

    @classmethod
    def tearDownClass(cls):
        cls.fixture.cleanup()

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name).resolve()
        self.inputs = self.root / "data" / "official"
        self.inputs.mkdir(parents=True)

    def write_input(self, *, frame=None, labels=None, values=None, filename="download.SAV", artificial=True):
        data = self.inputs / filename
        pyreadstat.write_sav(
            self.raw if frame is None else frame, data,
            column_labels=self.metadata.column_names_to_labels if labels is None else labels,
            variable_value_labels=self.metadata.variable_value_labels if values is None else values,
            file_label="Artificial workflow demonstration; not survey observations" if artificial else "Public-format test",
        )
        return data

    def test_single_uploaded_sav_is_discovered_and_validated(self):
        original = self.write_input().read_bytes()
        result = survey_setup.prepare_upload(self.root)
        self.assertEqual(result.data_file.name, "download.SAV")
        self.assertIn("1,728 observations", result.summary)
        self.assertIn("Artificial demonstration", result.summary)
        self.assertEqual(result.data_file.read_bytes(), original)
        profile = json.loads(result.profile_file.read_text())
        self.assertTrue(profile["artificial_data"])
        self.assertTrue(result.profile_file.is_relative_to(self.inputs))
        self.assertNotIn("demo_", result.summary)

    def test_renamed_columns_and_recoded_values_need_no_name_convention(self):
        renamed = {name: f"arbitrary_{index}" for index, name in enumerate(self.raw.columns)}
        frame = self.raw.rename(columns=renamed).copy()
        values = {}
        for old, labels in self.metadata.variable_value_labels.items():
            frame[renamed[old]] *= 10
            values[renamed[old]] = {code * 10: label for code, label in labels.items()}
        self.write_input(frame=frame, labels={renamed[k]: v for k, v in self.metadata.column_names_to_labels.items()}, values=values)
        result = survey_setup.prepare_upload(self.root)
        data, receipt = survey_input.load_survey(result.data_file, result.profile_file)
        self.assertEqual(receipt["observations"], 1728)
        self.assertEqual(set(data.age_group), set(range(1, 7)))
        mapping = json.loads(result.profile_file.read_text())["value_maps"]["photography"]
        self.assertEqual(mapping["10"], 1)
        self.assertNotIn("1", mapping)

    def test_no_file_and_multiple_files_require_selection(self):
        with self.assertRaisesRegex(survey_setup.InputSetupError, "Upload one"):
            survey_setup.prepare_upload(self.root)
        self.write_input(filename="first.sav")
        self.write_input(filename="second.sav")
        with self.assertRaisesRegex(survey_setup.InputSetupError, "More than one"):
            survey_setup.prepare_upload(self.root)
        result = survey_setup.prepare_upload(self.root, data_file="data/official/second.sav")
        self.assertEqual(result.data_file.name, "second.sav")

    def test_missing_value_labels_never_assume_identity_codes(self):
        values = dict(self.metadata.variable_value_labels)
        values.pop("demo_photo")
        self.write_input(values=values)
        with self.assertRaises(survey_setup.InputSetupError) as caught:
            survey_setup.prepare_upload(self.root)
        self.assertIn("photography: provide a complete value map", str(caught.exception))
        self.assertTrue(caught.exception.draft_path.is_file())
        self.assertTrue(caught.exception.metadata_path.is_file())
        profile = json.loads(caught.exception.draft_path.read_text())
        self.assertNotIn("photography", profile["value_maps"])

    def test_unmapped_label_and_unlabelled_observed_code_both_stop(self):
        values = json.loads(json.dumps(self.metadata.variable_value_labels))
        values = {name: {int(float(k)): v for k, v in labels.items()} for name, labels in values.items()}
        values["demo_photo"][1] = "Unexplained response"
        self.write_input(values=values)
        with self.assertRaisesRegex(survey_setup.InputSetupError, "complete value map"):
            survey_setup.prepare_upload(self.root)
        frame = self.raw.copy()
        frame.loc[0, "demo_contacts"] = 42
        self.write_input(frame=frame)
        with self.assertRaisesRegex(survey_setup.InputSetupError, "Unmapped responses for sharing_with_contacts"):
            survey_setup.prepare_upload(self.root)

    def test_ambiguous_role_stops_and_override_resolves_it(self):
        frame = self.raw.copy()
        frame["second_photo"] = frame.demo_photo
        labels = {**self.metadata.column_names_to_labels, "second_photo": "Artificial demonstration: photography"}
        values = {**self.metadata.variable_value_labels, "second_photo": self.metadata.variable_value_labels["demo_photo"]}
        self.write_input(frame=frame, labels=labels, values=values)
        with self.assertRaisesRegex(survey_setup.InputSetupError, "photography: multiple"):
            survey_setup.prepare_upload(self.root)
        override = {"columns": {"photography": "second_photo"},
                    "value_maps": {"photography": self.profile["value_maps"]["photography"]}}
        result = survey_setup.prepare_upload(self.root, overrides=override)
        self.assertEqual(json.loads(result.profile_file.read_text())["columns"]["photography"], "second_photo")

    def test_incomplete_binary_candidate_cannot_replace_frequency_item(self):
        frame = self.raw.copy()
        frame["binary_candidate"] = 6
        labels = {**self.metadata.column_names_to_labels, "binary_candidate": "Artificial demonstration: photography"}
        values = {**self.metadata.variable_value_labels, "binary_candidate": {2: "Daily", 6: "Never"}}
        self.write_input(frame=frame, labels=labels, values=values)
        result = survey_setup.prepare_upload(self.root)
        profile = json.loads(result.profile_file.read_text())
        self.assertEqual(profile["columns"]["photography"], "demo_photo")
        # Without a complete item, the partial response set must stop setup.
        labels["demo_photo"] = "Other variable"
        self.write_input(frame=frame, labels=labels, values=values)
        with self.assertRaisesRegex(survey_setup.InputSetupError, "complete value map"):
            survey_setup.prepare_upload(self.root)

    def test_changed_source_discards_stale_missing_codes_and_honours_override(self):
        frame = self.raw.copy()
        frame["new_contacts"] = frame.demo_contacts * 10
        labels = {**self.metadata.column_names_to_labels, "new_contacts": "Artificial demonstration: sharing_with_contacts"}
        values = {**self.metadata.variable_value_labels, "new_contacts": {
            code * 10: label for code, label in self.metadata.variable_value_labels["demo_contacts"].items()}}
        self.write_input(frame=frame, labels=labels, values=values)
        profile = json.loads(json.dumps(self.profile))
        profile["missing_values"]["sharing_with_contacts"] = [10]
        path = self.inputs / "profile.json"
        path.write_text(json.dumps(profile))
        override = {"columns": {"sharing_with_contacts": "new_contacts"}}
        result = survey_setup.prepare_upload(self.root, overrides=override)
        rebuilt = json.loads(result.profile_file.read_text())
        self.assertNotIn("sharing_with_contacts", rebuilt["missing_values"])
        mapped, _ = survey_input.load_survey(result.data_file, result.profile_file)
        self.assertEqual(mapped.sharing_with_contacts.isna().sum(), frame.new_contacts.isna().sum())
        override["missing_values"] = {"sharing_with_contacts": [60]}
        result = survey_setup.prepare_upload(self.root, overrides=override)
        rebuilt = json.loads(result.profile_file.read_text())
        self.assertEqual(rebuilt["missing_values"]["sharing_with_contacts"], [60])

    def test_explicit_and_neighbouring_profiles_take_precedence_without_overwrite(self):
        data = self.write_input(labels={name: "Uninformative label" for name in self.raw.columns})
        profile_file = self.inputs / "profile.json"
        profile_file.write_text(json.dumps(self.profile))
        original = profile_file.read_bytes()
        result = survey_setup.prepare_upload(self.root)
        self.assertEqual(result.data_file, data)
        self.assertEqual(profile_file.read_bytes(), original)
        alternate = self.inputs / "custom.json"
        alternate.write_bytes(original)
        result = survey_setup.prepare_upload(self.root, profile_file=alternate)
        self.assertIn("validated", result.summary)
        self.assertEqual(alternate.read_bytes(), original)

    def test_invalid_explicit_profile_is_not_silently_replaced(self):
        self.write_input()
        profile = json.loads(json.dumps(self.profile))
        profile["columns"]["primary_weight"] = "does_not_exist"
        path = self.inputs / "profile.json"
        path.write_text(json.dumps(profile))
        with self.assertRaisesRegex(survey_setup.InputSetupError, "absent"):
            survey_setup.prepare_upload(self.root)

    def test_two_neighbouring_profiles_require_choice(self):
        self.write_input()
        for name in ("profile.json", "download.profile.json"):
            (self.inputs / name).write_text(json.dumps(self.profile))
        with self.assertRaisesRegex(survey_setup.InputSetupError, "Two neighbouring"):
            survey_setup.prepare_upload(self.root)

    def test_design_is_not_guessed_from_first_stage_identifier(self):
        labels = dict(self.metadata.column_names_to_labels)
        labels["demo_cluster"] = "First-stage sampling unit"
        self.write_input(labels=labels)
        with self.assertRaisesRegex(survey_setup.InputSetupError, "design.second_stage_strata"):
            survey_setup.prepare_upload(self.root)
        result = survey_setup.prepare_upload(self.root, overrides={"design": {"second_stage_strata": []}})
        self.assertIn("36 variance clusters", result.summary)

    def test_generic_weight_labels_are_not_assigned_by_order(self):
        labels = dict(self.metadata.column_names_to_labels)
        labels["demo_weight"] = "Survey weight"
        labels["demo_alt_weight"] = "Other survey weight"
        self.write_input(labels=labels)
        with self.assertRaises(survey_setup.InputSetupError) as caught:
            survey_setup.prepare_upload(self.root)
        self.assertIn("primary_weight: identify", str(caught.exception))
        self.assertIn("alternative_weight: identify", str(caught.exception))
        self.assertNotIn("demo_weight", str(caught.exception))

    def test_private_generated_profiles_do_not_overwrite_each_other(self):
        self.write_input()
        first = survey_setup.prepare_upload(self.root)
        second = survey_setup.prepare_upload(self.root)
        self.assertNotEqual(first.profile_file, second.profile_file)
        self.assertTrue(first.profile_file.is_file())

    def test_generic_english_and_chinese_category_labels(self):
        cases = [
            ("Several times a day", "photography", 1), ("每天", "photography", 2),
            ("一週數次", "photography", 3), ("每月數次", "photography", 4),
            ("Less often", "photography", 5), ("從未使用", "photography", 6),
            ("手機無法拍照", "photography", 7), ("沒有手機", "photography", 8),
            ("30 至 39 歲", "age_group", 2), ("70 歲以上", "age_group", 6),
            ("Junior high school", "education_group", 2),
            ("Female", "sex_group", 2), ("Original device", "personal_files", 1),
            ("Non-mature", "area", 2),
        ]
        for label, role, expected in cases:
            with self.subTest(label=label):
                self.assertEqual(survey_setup._category(label, role, False), expected)

    def test_education_ranges_spanning_groups_need_explicit_mapping(self):
        for label in ("高中以下", "小學以上", "High school or below", "Junior high or above", "Below college"):
            with self.subTest(label=label):
                self.assertIsNone(survey_setup._category(label, "education_group", False))
        self.assertEqual(survey_setup._category("Elementary or below", "education_group", False), 1)
        self.assertEqual(survey_setup._category("College or above", "education_group", False), 4)


if __name__ == "__main__":
    unittest.main()
