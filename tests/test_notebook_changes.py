"""Exercise CI selection against real Git history and event payloads."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from ci.notebook_changes import determine, runtime_path


ROOT = Path(__file__).resolve().parents[1]


class NotebookChangesTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.environ = {key: value for key, value in os.environ.items()
                        if key not in {"GITHUB_OUTPUT", "GITHUB_STEP_SUMMARY"}}
        self.git("init", "-b", "main")
        self.git("config", "user.name", "Test")
        self.git("config", "user.email", "test@example.invalid")
        self.write("README.md", "Start\n")
        self.write("helpers/analysis.py", "VALUE = 1\n")
        self.base = self.commit("Initial fixture")

    def git(self, *args):
        return subprocess.check_output(["git", *args], cwd=self.root, stderr=subprocess.PIPE,
                                       text=True).strip()

    def write(self, name, text):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)

    def commit(self, message):
        self.git("add", "--all")
        self.git("commit", "-m", message)
        return self.git("rev-parse", "HEAD")

    def push(self, before, after):
        return determine("push", {"before": before, "after": after}, self.root)

    def test_documentation_and_aggregate_updates_keep_basic_checks_only(self):
        for path in ("README.md", "docs/NOTEBOOK.md", "references/catalog.json",
                     "aggregates/primary/result.csv", "LICENSE"):
            self.write(path, "Updated\n")
        result = self.push(self.base, self.commit("Documents and results"))
        self.assertFalse(result["run_notebook"])
        self.assertEqual(len(result["changed_paths"]), 5)
        self.assertIn("basic checks still run", result["reason"])

    def test_runtime_path_categories_and_prefix_boundaries(self):
        for path in ("run.py", "helpers/analysis.py", "ci/check.py", "tests/test_analysis.py",
                     "notebooks/reproduce.ipynb", ".binder/Dockerfile", ".github/workflows/ci.yml",
                     "requirements.txt", "requirements-notebook.txt", "environment.json",
                     ".dockerignore", "reference_data/area_classification.csv"):
            with self.subTest(path=path):
                self.assertTrue(runtime_path(path))
        for path in ("docs/requirements.txt", "helperish/test.py", "requirements.md",
                     "notebooks-guide.md", ".github/ISSUE_TEMPLATE.md",
                     "reference_data/README.md", ".binder/README.md", "ci/checks.rst"):
            with self.subTest(path=path):
                self.assertFalse(runtime_path(path))

    def test_code_update_selects_complete_check(self):
        self.write("helpers/analysis.py", "VALUE = 2\n")
        result = self.push(self.base, self.commit("Change analysis"))
        self.assertTrue(result["run_notebook"])
        self.assertEqual(result["changed_paths"], ["helpers/analysis.py"])

    def test_deletion_selects_complete_check(self):
        (self.root / "helpers/analysis.py").unlink()
        result = self.push(self.base, self.commit("Remove analysis"))
        self.assertTrue(result["run_notebook"])

    def test_rename_out_of_code_directory_checks_old_and_new_paths(self):
        self.git("mv", "helpers/analysis.py", "example.txt")
        result = self.push(self.base, self.commit("Move example"))
        self.assertTrue(result["run_notebook"])
        self.assertEqual(result["changed_paths"], ["example.txt", "helpers/analysis.py"])

    def test_push_compares_all_commits_not_only_last_commit(self):
        self.write("helpers/analysis.py", "VALUE = 3\n")
        self.commit("Code update")
        self.write("README.md", "New explanation\n")
        result = self.push(self.base, self.commit("Follow-up documentation"))
        self.assertTrue(result["run_notebook"])
        self.assertEqual(result["changed_paths"], ["README.md", "helpers/analysis.py"])

    def test_pull_request_uses_merge_base_and_ignores_target_only_code_changes(self):
        self.git("switch", "-c", "review")
        self.write("docs/NOTEBOOK.md", "New explanation\n")
        head = self.commit("PR documentation")
        self.git("switch", "main")
        self.write("helpers/analysis.py", "VALUE = 4\n")
        base = self.commit("Unrelated target branch code")
        event = {"pull_request": {"base": {"sha": base}, "head": {"sha": head}}}
        result = determine("pull_request", event, self.root)
        self.assertFalse(result["run_notebook"])
        self.assertEqual(result["changed_paths"], ["docs/NOTEBOOK.md"])

    def test_manual_dispatch_always_selects_complete_check(self):
        result = determine("workflow_dispatch", {}, self.root)
        self.assertTrue(result["run_notebook"])
        self.assertIn("Manual", result["reason"])

    def test_unavailable_or_invalid_comparison_runs_complete_check(self):
        cases = [("push", {}), ("push", {"before": "0" * 40, "after": self.base}),
                 ("push", {"before": "f" * 40, "after": self.base}),
                 ("push", {"before": "--output=unsafe", "after": self.base}),
                 ("pull_request", {}), ("pull_request", {"pull_request": {"base": None}}),
                 ("schedule", {}), ("push", None)]
        for event_name, payload in cases:
            with self.subTest(event_name=event_name, payload=payload):
                self.assertTrue(determine(event_name, payload, self.root)["run_notebook"])

    def test_shell_syntax_and_newlines_in_filenames_remain_literal(self):
        name = "docs/$(touch unexpected);\nrun_notebook=true.md"
        self.write(name, "Literal filename\n")
        result = self.push(self.base, self.commit("Odd but valid documentation name"))
        self.assertFalse(result["run_notebook"])
        self.assertEqual(result["changed_paths"], [name])
        self.assertFalse((self.root / "unexpected").exists())

    def test_cli_outputs_one_boolean_and_bounded_safe_diagnostics(self):
        self.write("README.md", "Documentation\n")
        after = self.commit("Docs")
        event_path, output, summary = (self.root / name for name in ("event.json", "output", "summary"))
        event_path.write_text(json.dumps({"before": self.base, "after": after}))
        env = {**self.environ, "GITHUB_OUTPUT": str(output), "GITHUB_STEP_SUMMARY": str(summary)}
        process = subprocess.run(
            [sys.executable, ROOT / "ci/notebook_changes.py", "--event-name", "push",
             "--event-path", event_path, "--root", self.root],
            capture_output=True, text=True, check=True, env=env,
        )
        self.assertEqual(output.read_text(), "run_notebook=false\n")
        self.assertIn("Basic checks run", summary.read_text())
        self.assertFalse(json.loads(process.stdout)["run_notebook"])

    def test_cli_unreadable_payload_still_selects_complete_check(self):
        output = self.root / "output"
        process = subprocess.run(
            [sys.executable, ROOT / "ci/notebook_changes.py", "--event-name", "push",
             "--event-path", self.root / "absent.json", "--root", self.root],
            capture_output=True, text=True, check=True,
            env={**self.environ, "GITHUB_OUTPUT": str(output)},
        )
        self.assertEqual(output.read_text(), "run_notebook=true\n")
        self.assertTrue(json.loads(process.stdout)["run_notebook"])

    def test_cli_uses_event_environment_and_bounds_changed_path_output(self):
        for index in range(55):
            self.write(f"docs/page-{index:02}.md", "Documentation\n")
        after = self.commit("Many documentation files")
        event_path = self.root / "event.json"
        event_path.write_text(json.dumps({"before": self.base, "after": after}))
        process = subprocess.run(
            [sys.executable, ROOT / "ci/notebook_changes.py"], cwd=self.root,
            capture_output=True, text=True, check=True,
            env={**self.environ, "GITHUB_EVENT_NAME": "push", "GITHUB_EVENT_PATH": str(event_path)},
        )
        result = json.loads(process.stdout)
        self.assertFalse(result["run_notebook"])
        self.assertEqual(result["changed_file_count"], 55)
        self.assertEqual(len(result["changed_paths"]), 50)
        self.assertTrue(result["paths_truncated"])


if __name__ == "__main__":
    unittest.main()
