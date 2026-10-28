"""Keep cloud tests free of real respondent inputs and disabled on private repositories."""
from pathlib import Path
import re
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]


class PublicPackagingTests(unittest.TestCase):
    def test_every_cloud_job_is_public_only_before_runner_allocation(self):
        workflow = (ROOT / '.github/workflows/public-reproducibility.yml').read_text()
        jobs = re.split(r'^  ([a-z][a-z-]+):\s*$', workflow.split('jobs:\n', 1)[1], flags=re.M)
        self.assertEqual(jobs[1::2], ['aggregate-checks', 'binder-notebook'])
        for name, block in zip(jobs[1::2], jobs[2::2], strict=True):
            with self.subTest(job=name):
                condition = re.search(r'^    if: (.*)$', block, re.M).group(1)
                self.assertTrue(condition.startswith('${{ github.event.repository.private == false'))
                self.assertNotIn('||', condition)
                self.assertLess(block.index('if:'), block.index('runs-on:'))

    def test_basic_checks_always_run_and_notebook_uses_change_decision(self):
        workflow = (ROOT / '.github/workflows/public-reproducibility.yml').read_text()
        events, jobs = workflow.split('jobs:\n', 1)
        self.assertIn('workflow_dispatch:', events)
        self.assertNotIn('paths:', events)
        self.assertNotIn('paths-ignore:', events)
        basic, notebook = jobs.split('  binder-notebook:', 1)
        self.assertIn('if: ${{ github.event.repository.private == false }}', basic)
        self.assertIn('fetch-depth: 0', basic)
        self.assertIn('id: notebook-changes', basic)
        self.assertIn('run: python ci/notebook_changes.py', basic)
        self.assertIn('run_notebook: ${{ steps.notebook-changes.outputs.run_notebook }}', basic)
        self.assertIn('needs: aggregate-checks', notebook)
        self.assertIn("needs.aggregate-checks.outputs.run_notebook == 'true'", notebook)
        # The cloud pipeline accepts no respondent-data input or download URL.
        self.assertIn('python run.py demo --output-dir /tmp/demo-input', notebook)
        self.assertIn('cp /tmp/demo-input/survey.sav data/official/uploaded.sav', notebook)

    def test_cli_exposes_explicit_manual_input_operations(self):
        result = subprocess.run([sys.executable, ROOT / 'run.py', '--help'],
                                capture_output=True, text=True, check=True)
        self.assertIn('{verify-only,figures,inspect,demo,reestimate}', result.stdout)
        rejected = subprocess.run([sys.executable, ROOT / 'run.py', 'reestimate'],
                                  capture_output=True, text=True, check=False)
        self.assertNotEqual(rejected.returncode, 0)

    def test_binder_copies_only_public_directories(self):
        dockerfile = (ROOT / '.binder/Dockerfile').read_text()
        directories = re.findall(r'^COPY --chown=1000:1000 (\S+/) ', dockerfile, re.M)
        self.assertEqual(set(directories), {
            'docs/', '.github/workflows/', 'helpers/', 'aggregates/',
            'ci/', 'references/', 'reference_data/', 'notebooks/',
        })
        for directory in directories:
            self.assertTrue((ROOT / directory).is_dir())


if __name__ == '__main__':
    unittest.main()
