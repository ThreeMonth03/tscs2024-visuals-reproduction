# Local reproduction

The package supports two operations: reestimate from a user-supplied official SAV, or inspect existing aggregate results. The historical public-release format is the working input contract. The target release's exact estimates can be checked when its official file is obtained.

## Set up

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-notebook.txt
```

Obtain your data through [the official provider](DATA_ACCESS.md), and configure a local [input profile](INPUT_PROFILE.md). Keep data and output outside the repository.

## Reestimate from your file

```bash
python run.py reestimate \
  --data-file "$HOME/Documents/TSCS/data/official/survey.sav" \
  --profile-file "$HOME/Documents/TSCS/data/official/profile.json" \
  --output-dir "$HOME/Documents/TSCS/results/run-01"
```

Optionally add `--calibration-file` for the additional population-margin check, and `--font` for an installed font. Use a new output directory each time. Calculations preserve the defined outcomes, denominators, design-based variance, 141-test family and 266-contrast family; there is no automatic reduction of comparison scope when inputs are missing.

The output contains newly estimated aggregate tables under `analysis/aggregates/`, nine figures under `figures/`, and local run receipts. The receipt records whether the additional calibration check was available. No cleaned respondent table is written. For the browser gallery and results ZIP, run the [Notebook](NOTEBOOK.md); its ZIP excludes inputs, profiles, metadata catalogues and logs.

## Test the workflow with artificial data

```bash
python run.py demo --output-dir "$HOME/Documents/TSCS/demo-input"
python run.py reestimate \
  --data-file "$HOME/Documents/TSCS/demo-input/survey.sav" \
  --profile-file "$HOME/Documents/TSCS/demo-input/profile.json" \
  --calibration-file "$HOME/Documents/TSCS/demo-input/calibration.json" \
  --output-dir "$HOME/Documents/TSCS/results/demo-run-01"
```

This validates the input and analysis workflow with artificial observations. Its results are demonstrations, not study findings.

## Verify existing aggregates or redraw them

```bash
python run.py verify-only
python run.py figures --output-dir "$HOME/Documents/TSCS/results/aggregate-figures-01"
```

These commands check the supplied aggregate hashes, BY adjustments, sensitivity summaries and references, and regenerate figures from the stored estimates. They do not read a SAV. See [terminology](TERMINOLOGY.md) and [provenance](PROVENANCE.md) for interpretation and verification scope.
