"""Check editable settings and the two explicit input paths."""
import argparse
from dataclasses import replace
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from ci.execute_notebook import apply_cli_settings, check_notebook_links, execution_environment
from helpers import notebook_workflow as workflow


ROOT = Path(__file__).resolve().parents[1]


class NotebookTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.output = Path(self.temporary.name).resolve() / "run"
        self.config = workflow.Configuration(self.output, "test-font")
        self.commands = []

    def fake_command(self, root, output, name, arguments):
        self.commands.append((name, [str(item) for item in arguments]))
        if name == "figures":
            directory = output / "figures"
            directory.mkdir()
            (directory / "figures_manifest.json").write_text(json.dumps({
                "status": "pass", "figure_count": 9,
                "figures": {f"figure_{i}": {} for i in range(9)}}))

    def test_workflow_uses_only_published_aggregates(self):
        with patch.object(workflow, "_run", side_effect=self.fake_command):
            report = workflow.run_workflow(ROOT, self.config)
        self.assertEqual([name for name, _ in self.commands],
                         ["bundle", "references", "aggregates", "figures"])
        self.assertEqual(report["mode"], "aggregate")
        self.assertFalse(report["statistical_reestimation"])
        self.assertEqual(report["input_estimates"], "published_aggregates")
        self.assertEqual(dict(self.commands)["figures"][-1], "test-font")

    def test_failed_check_does_not_render_or_report_success(self):
        def fail(root, output, name, arguments):
            if name == "aggregates":
                raise RuntimeError("Aggregate check failed")
            self.fake_command(root, output, name, arguments)
        with patch.object(workflow, "_run", side_effect=fail):
            with self.assertRaisesRegex(RuntimeError, "Aggregate check failed"):
                workflow.run_workflow(ROOT, self.config)
        self.assertFalse((self.output / "figures").exists())
        self.assertFalse((self.output / "notebook_report.json").exists())

    def test_outputs_cannot_change_repository_or_previous_run(self):
        with self.assertRaisesRegex(ValueError, "outside"):
            workflow.run_workflow(ROOT, replace(self.config, output_dir=ROOT / "generated"))
        self.output.mkdir()
        (self.output / "important.txt").write_text("keep")
        with self.assertRaises(FileExistsError):
            workflow.run_workflow(ROOT, self.config)
        self.assertEqual((self.output / "important.txt").read_text(), "keep")

    def test_editable_cell_settings_take_effect(self):
        notebook = json.loads((ROOT / "notebooks/reproduce.ipynb").read_text())
        cell = next(cell for cell in notebook["cells"]
                    if "parameters" in cell.get("metadata", {}).get("tags", []))
        source = (cell["source"].replace('OUTPUT_DIR = ""', f'OUTPUT_DIR = {str(self.output)!r}')
                  .replace('FONT = ""', 'FONT = "selected-font"'))
        namespace = {}
        exec(source, namespace)
        config = workflow.configuration({"REPRO_OUTPUT_DIR": namespace["OUTPUT_DIR"],
                                         "REPRO_FONT": namespace["FONT"]})
        self.assertEqual(config.output_dir, self.output)
        self.assertEqual(config.font, "selected-font")

    def test_blank_output_creates_new_temporary_location(self):
        with patch.object(workflow.tempfile, "mkdtemp", return_value=str(self.output.parent)):
            config = workflow.configuration({"REPRO_OUTPUT_DIR": "", "REPRO_FONT": ""})
        self.assertEqual(config.output_dir, self.output)
        self.assertEqual(config.font, workflow.default_font())

    def test_local_default_does_not_require_binders_linux_font(self):
        with patch.object(workflow.Path, "is_file", return_value=False):
            config = workflow.configuration({"REPRO_OUTPUT_DIR": str(self.output)})
        self.assertEqual(config.font, "DejaVu Sans")

    def test_binder_font_and_explicit_selection_are_preserved(self):
        with patch.object(workflow.Path, "is_file", return_value=True):
            config = workflow.configuration({"REPRO_OUTPUT_DIR": str(self.output)})
            explicit = workflow.configuration({"REPRO_OUTPUT_DIR": str(self.output),
                                               "REPRO_FONT": "chosen-font"})
        self.assertEqual(config.font, workflow.DEFAULT_FONT)
        self.assertEqual(explicit.font, "chosen-font")

    def test_cli_settings_override_only_executed_copy(self):
        notebook = json.loads((ROOT / "notebooks/reproduce.ipynb").read_text())
        before = (ROOT / "notebooks/reproduce.ipynb").read_bytes()
        args = argparse.Namespace(font="selected-font")
        env = execution_environment(args, self.output, {
            "REPRO_OUTPUT_DIR": "/old-run", "REPRO_FONT": "old-font", "PYTHONOPTIMIZE": "1"})
        self.assertNotIn("PYTHONOPTIMIZE", env)
        apply_cli_settings(notebook, env)
        cell = next(cell for cell in notebook["cells"]
                    if "parameters" in cell.get("metadata", {}).get("tags", []))
        namespace = {}
        exec(cell["source"], namespace)
        self.assertEqual(namespace["OUTPUT_DIR"], str(self.output / "run"))
        self.assertEqual(namespace["FONT"], "selected-font")
        self.assertEqual((ROOT / "notebooks/reproduce.ipynb").read_bytes(), before)

    def test_cli_uses_installed_font_when_not_overridden(self):
        env = execution_environment(argparse.Namespace(font=None), self.output,
                                    {"REPRO_FONT": "installed-font"})
        self.assertEqual(env["REPRO_FONT"], "installed-font")
        self.assertEqual(env["OPENBLAS_NUM_THREADS"], "1")

    def test_survey_paths_are_explicit_and_missing_inputs_stop_early(self):
        config = workflow.configuration({"REPRO_MODE": "survey", "REPRO_OUTPUT_DIR": str(self.output),
                                         "REPRO_DATA_FILE": str(self.output.parent / "survey.sav"),
                                         "REPRO_PROFILE_FILE": str(self.output.parent / "profile.json")})
        self.assertEqual(config.mode, "survey")
        self.assertEqual(config.data_file, self.output.parent / "survey.sav")
        with self.assertRaisesRegex(FileNotFoundError, "DATA_FILE"):
            workflow.run_workflow(ROOT, config)
        self.assertFalse(self.output.exists())

    def test_unknown_mode_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "MODE"):
            workflow.configuration({"REPRO_MODE": "full"})

    def test_cli_survey_settings_override_inherited_paths(self):
        args = argparse.Namespace(font=None, mode="survey", data_file=Path("/input/new.sav"),
                                  profile_file=Path("/input/new.json"), calibration_file=None)
        env = execution_environment(args, self.output, {"REPRO_DATA_FILE": "/old.sav"})
        self.assertEqual(env["REPRO_DATA_FILE"], "/input/new.sav")
        self.assertEqual(env["REPRO_PROFILE_FILE"], "/input/new.json")
        self.assertEqual(env["REPRO_CALIBRATION_FILE"], "")
        notebook = json.loads((ROOT / "notebooks/reproduce.ipynb").read_text())
        apply_cli_settings(notebook, env)
        cell = next(c for c in notebook["cells"] if "parameters" in c["metadata"].get("tags", []))
        namespace = {}
        exec(cell["source"], namespace)
        self.assertEqual(namespace["MODE"], "survey")
        self.assertEqual(namespace["DATA_FILE"], "/input/new.sav")

    def test_cli_rejects_missing_duplicate_or_noncode_settings_cell(self):
        parameter = {"cell_type": "code", "metadata": {"tags": ["parameters"]}, "source": ""}
        for cells in ([], [parameter, parameter], [{**parameter, "cell_type": "markdown"}]):
            with self.subTest(cells=cells):
                with self.assertRaisesRegex(ValueError, "exactly one parameters code cell"):
                    apply_cli_settings({"cells": cells}, {})

    def test_missing_documentation_fails_before_execution(self):
        notebook = {"cells": [{"cell_type": "markdown", "source":
                    "[Guide](../docs/NOTEBOOK.md)"}]}
        with self.assertRaisesRegex(FileNotFoundError, "NOTEBOOK.md"):
            check_notebook_links(Path(self.temporary.name), notebook)

    def test_notebook_links_and_empty_outputs(self):
        notebook = json.loads((ROOT / "notebooks/reproduce.ipynb").read_text())
        check_notebook_links(ROOT, notebook)
        for cell in notebook["cells"]:
            if cell["cell_type"] == "code":
                self.assertEqual(cell["outputs"], [])
                self.assertIsNone(cell["execution_count"])
        self.assertNotIn("/Users/", json.dumps(notebook))


if __name__ == "__main__":
    unittest.main()
