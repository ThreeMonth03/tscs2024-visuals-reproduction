# Software and public aggregate checks

CI checks the published software and aggregate results. It uses the bundled statistical tables and generated artificial observations; it does not obtain or reanalyze actual respondent data. Each job checks `github.event.repository.private == false` before allocating a runner, so private repositories skip both jobs.

## What runs, and when

The [workflow](../.github/workflows/public-reproducibility.yml) starts on pushes to `main`, pull requests and manual runs.

| Job | When it runs | What it checks |
|---|---|---|
| `aggregate-checks` | Every workflow run | Reviewed public file inventory, unit tests, ten aggregate tables, BY corrections, sensitivity summaries, reference rights and regeneration of nine selected figures |
| `binder-notebook` | Relevant runtime changes or a manual run | Builds the Binder image and executes the Notebook in aggregate mode and with an artificial SAV, including automatic input setup, fresh statistical estimates, nine figures and the results ZIP |

The full Notebook test runs when changes affect:

- Program, test or CI code: `run.py`, `helpers/`, `ci/`, `tests/`, `.github/workflows/`.
- Notebooks: `notebooks/`.
- The execution environment: `.binder/`, `.dockerignore`, `requirements*.txt`, `environment.json`.
- Analysis reference inputs: `reference_data/`, including the geographic classification used by the calculations.

Changes only to prose documentation, reference PDFs or aggregate tables still receive the basic checks and figure regeneration, but skip the full Notebook test. Markdown and reStructuredText files remain documentation-only changes even inside the folders above. If the workflow cannot reliably determine the changed files, it runs the full test. The workflow summary records the decision and reason.

To request a full check yourself, open the repository's **Actions** tab, select **Software and public aggregate checks**, click **Run workflow**, select `main` and run it. A manual run always requests both jobs, even when the latest change only edits documentation.

## What a successful run establishes

The aggregate checks verify the existing tables and redraw figures from stored estimates. They do not recalculate empirical proportions, standard errors or hypothesis tests from a SAV. The nine figures show the selected study results; additional comparisons and sensitivity results remain in the CSV tables.

The full Notebook test calculates new results from artificial observations. It checks that input setup, analysis, plotting and export work together in the Binder environment. Agreement with a particular official survey release must be checked separately after obtaining that release and confirming its input mapping.

The Docker test uses Python 3.14.4. Live browser verification separately checks the upload interface, rendered gallery and ZIP download; the CI Docker test does not operate a browser.

## Data and artifacts

CI does not download or accept actual respondent files, and it requires no data-access credentials. The artificial SAV is generated during the run and is not uploaded as an artifact. Artifact paths explicitly select aggregate figures, check reports, the executed aggregate Notebook and run receipts. SAV files, input profiles, metadata catalogues and execution logs are excluded.

## Local checks

Install the [Notebook environment](NOTEBOOK.md), then run:

```bash
python run.py verify-only
python ci/check_release.py
python -m unittest discover -s tests -v
python ci/check_references.py
python ci/execute_notebook.py --mode aggregate --output-dir /tmp/tscs-aggregate-check
python run.py demo --output-dir /tmp/tscs-demo-check
python ci/execute_notebook.py \
  --mode survey \
  --data-file /tmp/tscs-demo-check/survey.sav \
  --calibration-file /tmp/tscs-demo-check/calibration.json \
  --output-dir /tmp/tscs-survey-check
```

Use unused directories and supply `--font` if necessary. This example can use the generated profile beside the SAV. To test metadata-only setup, copy only the artificial SAV into an otherwise empty `data/official/` directory, leave the Notebook's input settings blank, and run all cells. The fixed correction families remain 141 and 266, including 98/84/84 proportion contrasts across all adults and the two area groups.

## Release maintenance

Review new files and update the explicit inventory before publishing. Keep real input files, local profiles and metadata out of Git and Docker's build context. Clear Notebook outputs and personal settings. Preserve the recorded aggregate tables unless a separately validated numerical update is adopted. After publishing, check the workflow summary and the jobs selected for that change. For a Notebook release, also preview the figures and download the result ZIP in a live Binder session.

The workflow has read-only repository permissions and does not persist checkout credentials. Its public-only job condition is described in [GitHub's documentation](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/control-jobs-with-conditions).
