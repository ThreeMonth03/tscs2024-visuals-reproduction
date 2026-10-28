# Public CI and release checks

The [workflow](../.github/workflows/public-reproducibility.yml) checks `github.event.repository.private == false` before allocating a runner to each job. Both jobs are skipped in private repositories.

| Job | Checks |
|---|---|
| `aggregate-checks` | Reviewed file inventory, input/statistical unit tests, preserved aggregate values, BY corrections, sensitivity summaries, reference rights and nine figures |
| `binder-notebook` | Builds the Binder image; executes aggregate mode and survey mode with generated artificial inputs, including automatic SAV setup |

CI never downloads or accepts actual respondent records. Its artificial input is generated during the run and is not uploaded as an artifact. Artifacts are selected by explicit paths: aggregate figures, aggregate check reports and Notebook run receipts. Input profiles, SAV files, metadata catalogues and execution logs are excluded.

The Docker test uses the Binder environment, including Python 3.14.4. Live browser verification additionally checks upload, editable settings, the rendered figure gallery and ZIP download. These are distinct checks: an HTTP success response alone does not establish that gallery images render. Artificial-data success validates the workflow, not agreement with empirical study results; numerical comparison with authorized study data is performed locally.

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

Use unused directories and supply `--font` if necessary. This example can use the generated profile beside the SAV. To specifically test metadata-only setup, copy only the artificial SAV into an otherwise empty `data/official/` directory, leave the Notebook's input settings blank, and run all cells. Validate any new official input against its codebook, sampling design and existing results. The fixed correction families remain 141 and 266, including 98/84/84 proportion contrasts across all adults and the two area groups.

## Release maintenance

Review new files and update the explicit inventory before publishing. Keep real input files, local profiles and metadata out of Git and Docker's build context. Clear Notebook outputs and personal settings. Preserve the recorded aggregate tables unless a separately validated numerical update is adopted. After publishing, check both public jobs, preview the figures and download the result ZIP.

The workflow has read-only repository permissions and does not persist checkout credentials. Its public-only job condition is described in [GitHub's documentation](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/control-jobs-with-conditions).
