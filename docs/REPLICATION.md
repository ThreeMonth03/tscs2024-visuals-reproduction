# Local reproduction

The package supports two operations: reestimate from a user-supplied official SAV, or inspect existing aggregate results. The historical public-release format is the working input contract. The target release's exact estimates can be checked when its official file is obtained.

## Set up

Install **Python 3.14.4**, matching the tested Binder environment. Obtain the source with `git clone https://github.com/ThreeMonth03/tscs2024-visuals-reproduction.git`, then enter its folder with `cd tscs2024-visuals-reproduction`. On macOS or Linux:

```bash
python3.14 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-notebook.txt
mkdir -p data/official
```

On Windows, use PowerShell:

```powershell
py -3.14 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-notebook.txt
New-Item -ItemType Directory -Force data/official
.\.venv\Scripts\jupyter.exe lab notebooks/reproduce.ipynb
```

No PowerShell activation is required. For the commands below, replace `python` with `.\.venv\Scripts\python.exe` and use your own file paths; enter commands on one line instead of using the Bash `\` line continuations. Use `$env:USERPROFILE` in place of `$HOME` when constructing Windows paths.

Binder uses its installed Noto font. On other systems, the default falls back to Matplotlib's bundled DejaVu Sans, which covers the English figure labels. To choose another installed font, set `FONT` in the Notebook or pass `--font` as a family name or font-file path. A missing explicitly selected font stops plotting rather than silently changing the selection.

Obtain your data through [the official provider](DATA_ACCESS.md). For the simplest workflow, launch `jupyter lab notebooks/reproduce.ipynb`, upload one SAV to `data/official/`, and choose **Run → Run All Cells**. See [the Notebook guide](NOTEBOOK.md) for figure previews and ZIP downloads.

The ignored `data/official/` directory is for local inputs; outputs must be outside the repository. You can also keep inputs outside the repository and select them by absolute path.

## Reestimate from your file

```bash
python run.py reestimate \
  --data-file "$HOME/Documents/TSCS/data/official/survey.sav" \
  --output-dir "$HOME/Documents/TSCS/results/run-01"
```

The command uses `profile.json` beside the SAV when present; otherwise it attempts metadata-based setup. If the file is the only SAV in `data/official/`, you can also omit `--data-file`. Ambiguous inputs stop with a message explaining what needs confirmation. For an explicitly completed profile, add `--profile-file` with its path; see [input configuration](INPUT_PROFILE.md).

Optionally add `--calibration-file` for the additional population-margin check, and `--font` for an installed font. Use a new output directory each time. Calculations preserve the defined outcomes, denominators, design-based variance, 141-test family and 266-contrast family; missing inputs do not silently reduce the comparison scope.

The output contains newly estimated aggregate tables under `analysis/aggregates/`, nine figures under `figures/`, and local run receipts. The receipt records whether the additional calibration check was available. No cleaned respondent table is written. For the browser gallery and results ZIP, run the [Notebook](NOTEBOOK.md); its ZIP excludes inputs, profiles, metadata catalogues and logs.

To execute the Notebook from the command line:

```bash
python ci/execute_notebook.py \
  --mode survey \
  --data-file "$HOME/Documents/TSCS/data/official/survey.sav" \
  --output-dir "$HOME/Documents/TSCS/results/notebook-01" \
  --timeout 3600
```

Command-line settings apply only to the executed copy. The source Notebook stays unchanged. Use `--mode aggregate` to execute it with the bundled results instead.

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
