# Binder and local Notebook guide

The Notebook has two input modes:

| Mode | Input | Result |
|---|---|---|
| `aggregate` | The ten tables included in the repository | Checked tables and nine redrawn figures |
| `survey` | Your SAV file and a release-specific mapping profile | Newly calculated statistics and nine figures drawn from them |

Both modes offer a figure gallery and a downloadable ZIP. The ZIP contains figures and aggregate results only.

## Open Binder

[Launch the Notebook](https://binder.depositar.io/v2/gh/ThreeMonth03/tscs2024-visuals-reproduction/main?urlpath=lab%2Ftree%2Fnotebooks%2Freproduce.ipynb). Wait for JupyterLab to open. A commit or release tag can replace `main` in the link to select a specific code version.

For a preview of the supplied results, leave `MODE = "aggregate"` and run the cells in order with **Shift + Enter**. No survey file is needed.

## Analyze a survey file

### 1. Obtain and prepare the input

Download the official release through the [provider's channels](DATA_ACCESS.md) and retain its codebook and citation information. A mapping profile connects that release's variables and response codes to the analysis. Create and complete it using the [input-profile guide](INPUT_PROFILE.md).

Keep the SAV and completed profile together. For example, on your computer:

```text
~/Documents/TSCS/data/official/survey.sav
~/Documents/TSCS/data/official/profile.json
```

The filenames are examples; use the names of your own files. If you also have population targets for the additional recalibration check, prepare the target JSON described in the input-profile guide.

### 2. Upload to Binder, or use local files

On Binder, open `data`, then `official`, in JupyterLab's left file browser. Click **Upload Files** and select the SAV and completed profile from your computer. If supplied, upload the calibration-target JSON to the same folder. Uploading to the selected folder gives these example absolute paths:

```python
DATA_FILE = "/home/jovyan/data/official/survey.sav"
PROFILE_FILE = "/home/jovyan/data/official/profile.json"
CALIBRATION_FILE = ""  # Or "/home/jovyan/data/official/calibration.json"
```

If the folder does not exist in an older image, use **New Folder** in the file browser to create `data/official` under `/home/jovyan` first. Check the current folder before uploading.

Use the cloud workflow only for data you are permitted to process there. The same Notebook runs locally without uploading any files. This workflow does not send survey files to GitHub, depositar datasets or CI. Binder stores session files temporarily; see its [service documentation](https://docs.depositar.io/en/stable/user-guide/binder.html).

### 3. Edit the settings cell

For Binder:

```python
MODE = "survey"
DATA_FILE = "/home/jovyan/data/official/survey.sav"
PROFILE_FILE = "/home/jovyan/data/official/profile.json"
CALIBRATION_FILE = ""
OUTPUT_DIR = "/tmp/tscs-results/run-01"
FONT = ""
```

For a local run:

```python
MODE = "survey"
DATA_FILE = "~/Documents/TSCS/data/official/survey.sav"
PROFILE_FILE = "~/Documents/TSCS/data/official/profile.json"
CALIBRATION_FILE = ""
OUTPUT_DIR = "~/Documents/TSCS/results/run-01"
FONT = ""
```

`~` means your home directory. `FONT` can remain blank on Binder. Locally, set it to an installed font if the default is unavailable. `CALIBRATION_FILE` supplies targets for the additional population recalibration check; leaving it blank marks that check unavailable, rather than substituting stored estimates.

The output directory must be new and outside the repository. Use `run-02` for another run, or leave `OUTPUT_DIR` blank to create a fresh temporary directory. Existing inputs and results are preserved.

### 4. Execute and check the results

Run the settings cell and all subsequent cells. The confirmation cell shows the mode, selected input paths and output directory. Verify the paths before starting analysis. After changing a setting, rerun from the settings cell onward.

Survey mode reads the selected file and computes the results; it does not copy the supplied statistical tables. Required inputs are checked before estimation. A failed calculation stops the workflow instead of producing a success download. Statistical failures and unavailable checks are recorded in the result tables.

When the run completes, the Notebook shows the source mode, nine figures, and two links:

- **View nine figures** opens the figure gallery.
- **Download figures and aggregates (ZIP)** downloads this run's results.

The main results are in the configured output directory. Survey-mode aggregate CSVs are under `analysis/aggregates/`; figures are under `figures/`. The download copies are in `notebooks/downloads/`, where Jupyter can serve them. Generated inputs and outputs are excluded from Git.

## Install and run locally

From the repository root:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-notebook.txt
jupyter lab notebooks/reproduce.ipynb
```

To execute the Notebook from the command line:

```bash
python ci/execute_notebook.py \
  --mode survey \
  --data-file "$HOME/Documents/TSCS/data/official/survey.sav" \
  --profile-file "$HOME/Documents/TSCS/data/official/profile.json" \
  --output-dir "$HOME/Documents/TSCS/results/notebook-01" \
  --timeout 3600
```

Add `--calibration-file` when supplying population targets, and `--font` if needed. Command-line options replace the settings only in the executed copy; the source Notebook stays unchanged. For the bundled aggregate preview, omit `--mode`, `--data-file` and `--profile-file`.

## Test the upload workflow without survey records

The demo generator creates artificial data and a matching profile. It is useful for learning the upload process and testing settings; its results are not study findings.

```bash
python run.py demo --output-dir "$HOME/Documents/TSCS/demo-input"
```

Upload the generated `survey.sav`, `profile.json` and `calibration.json` to Binder's `data/official` folder and use their paths in survey mode. The sample is generated by code and contains no real respondents.

## Download contents

The ZIP contains nine figures in PNG/PDF formats, plotting aggregates, ten statistical tables and reading information. Survey mode exports the newly calculated tables; aggregate mode exports the bundled tables. It excludes survey files, mapping profiles, respondent records, logs and input paths. After extraction, open `index.html` to browse the figures.

Download before leaving Binder because the service provides no persistent storage. Clear Notebook outputs and reset personal paths before contributing changes. CI uses artificial inputs and public aggregates, and runs only in public repositories; see [CI.md](CI.md).
