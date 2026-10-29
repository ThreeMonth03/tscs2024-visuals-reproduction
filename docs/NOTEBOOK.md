# Binder and local Notebook guide

The normal workflow is **upload one SAV → run all cells → view or download results**. The Notebook checks the uploaded file before calculating anything.

| Mode | Input | Result |
|---|---|---|
| `survey` (default) | Your official SAV | Newly calculated statistics and nine figures |
| `aggregate` | The ten tables included in the repository | Checked tables and nine redrawn figures |

Both modes provide a figure gallery and a ZIP containing figures and aggregate results only.

## Run on Binder

### 1. Obtain your file and open the Notebook

Download the official SAV through [TSCS or SRDA](DATA_ACCESS.md), and retain its codebook and citation information. Use Binder when the provider's terms permit cloud processing; otherwise use the same Notebook [locally](#run-on-your-computer).

[Launch the Binder Notebook](https://binder.depositar.io/v2/gh/ThreeMonth03/tscs2024-visuals-reproduction/main?urlpath=lab%2Ftree%2Fnotebooks%2Freproduce.ipynb) and wait for JupyterLab to open. A commit or release tag can replace `main` in this link when you need a specific code version.

### 2. Upload to `data/official/`

In the left file browser, click the **home icon** to return to the repository root. Open **data**, then **official**. Click **Upload Files** and select your SAV. Wait until the upload completes. Leave its original filename unchanged.

The absolute folder on Binder is `/home/jovyan/data/official/`. For example, a file named `survey.sav` will be at:

```text
/home/jovyan/data/official/survey.sav
```

Keep exactly one SAV in that folder for automatic selection. If there are several files, set `DATA_FILE` in the Notebook to the particular file you want to analyze.

### 3. Run all cells

Return to the `reproduce.ipynb` tab and choose **Run → Run All Cells**. The default settings find the SAV automatically:

```python
MODE = "survey"
DATA_FILE = ""          # Find the single SAV in data/official/.
PROFILE_FILE = ""       # Use profile.json beside it, or inspect its metadata.
INPUT_OVERRIDES = {}    # Only needed if setup requests confirmation.
CALIBRATION_FILE = ""   # Optional population targets for an extra check.
OUTPUT_DIR = ""         # Create a fresh temporary output directory.
FONT = ""              # Use the available default font.
```

No Terminal command is needed for the normal workflow. The setup output shows the selected file and how the analysis inputs were identified. Analysis starts only after required variables, response coding, grouping, weights and sampling design pass validation.

The metadata must identify each required input unambiguously. Incomplete or ambiguous labels require a first-time confirmation: the Notebook stops with unresolved inputs and paths to a local profile draft and metadata catalogue. Follow [the input-profile guide](INPUT_PROFILE.md), then rerun from the settings cell. Once confirmed, save the profile to reuse with the same release. A missing or ambiguous input never causes the Notebook to substitute the bundled results.

### 4. View and download your results

After calculation, the Notebook shows the source mode, nine figures and two links:

- **View nine figures** opens a gallery with embedded images.
- **Download figures and aggregates (ZIP)** downloads this run's figures and tables.

Survey mode draws the **newly calculated tables from your SAV**. Aggregate mode draws the bundled estimates. The gallery and ZIP identify the mode used. After extracting the ZIP, open `index.html` to browse its figures offline.

The setup output gives the full output-directory path. Survey CSVs are under `analysis/aggregates/`, and figures are under `figures/`. Browser download copies are placed in `notebooks/downloads/` so Jupyter can serve them. These generated files are excluded from Git.

Download the ZIP before leaving Binder: session storage is temporary. Uploading a file here does not publish it as a GitHub file or a depositar dataset through this workflow. See [Binder service documentation](https://docs.depositar.io/en/stable/user-guide/binder.html) for the hosting environment.

## Change settings when needed

With one SAV in `data/official/`, blank input settings are enough when its metadata resolves all required inputs. To select files explicitly, edit the settings cell. For example:

```python
MODE = "survey"
DATA_FILE = "/home/jovyan/data/official/survey.sav"
PROFILE_FILE = "/home/jovyan/data/official/profile.json"
INPUT_OVERRIDES = {}
CALIBRATION_FILE = ""
OUTPUT_DIR = "/tmp/tscs-results/run-01"
FONT = ""
```

Use the actual filenames you uploaded. `PROFILE_FILE` is only needed when selecting a completed profile explicitly; blank uses a `profile.json` beside the SAV or automatic metadata setup. A profile records the mapping from your release's columns and codes to the analysis. `INPUT_OVERRIDES` supplies individual corrections when setup requests them; see [input configuration](INPUT_PROFILE.md).

`CALIBRATION_FILE` supplies official population targets for an additional recalibration check. Blank marks that extra scenario unavailable. The main analysis, comparison using the supplied alternative weight, and sampling-unit deletion checks remain distinct calculations.

The output directory must be new and outside the repository. Choose `run-02` for another run, or leave `OUTPUT_DIR` blank to create a fresh directory automatically. After changing settings, rerun the settings cell and all following cells.

To preview results without a SAV, change only:

```python
MODE = "aggregate"
```

## Run on your computer

Install **Python 3.14.4**, matching the tested Binder environment. Use the [local setup guide](REPLICATION.md#set-up) to obtain the repository or follow the Windows commands. On macOS or Linux, run from the repository root:

```bash
python3.14 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-notebook.txt
mkdir -p data/official
jupyter lab notebooks/reproduce.ipynb
```

Upload the SAV to `data/official/` in your local JupyterLab and run all cells, just as on Binder. The file stays on your computer. Alternatively, use an existing local file:

```python
MODE = "survey"
DATA_FILE = "~/Documents/TSCS/data/official/survey.sav"
PROFILE_FILE = ""
INPUT_OVERRIDES = {}
CALIBRATION_FILE = ""
OUTPUT_DIR = "~/Documents/TSCS/results/run-01"
FONT = ""
```

`~` means your home directory. Leave `FONT` blank to use Binder's installed Noto font or Matplotlib's bundled DejaVu Sans on other systems. To choose a font yourself, supply an installed family name or font-file path. For command-line execution, see [local reproduction](REPLICATION.md).

## Practise without survey records

The demo generator creates an artificial SAV and matching configuration files:

```bash
python run.py demo --output-dir "$HOME/Documents/TSCS/demo-input"
```

Upload only the generated `survey.sav` to an otherwise empty Binder `data/official/` folder and run all cells to test automatic setup. Its metadata identifies it as artificial. To exercise the additional calibration check too, upload `calibration.json` and set `CALIBRATION_FILE` to its path. The generated `profile.json` is also available for practising explicit profile selection.

These observations are generated by code. Their results demonstrate the workflow and are not study findings.

## ZIP contents

The ZIP contains nine figures in PNG/PDF formats, plotting aggregates, ten statistical tables and reading information. It excludes SAV files, mapping profiles, metadata catalogues, respondent records, logs and input paths.

Statistical failures and unavailable checks appear in the result tables. A workflow error stops execution instead of offering a successful new download. Clear Notebook outputs and personal settings before contributing changes. [CI](CI.md) checks public aggregates and software behavior. Basic checks run on every update to `main` or a pull request; the full Notebook test runs for relevant runtime changes or a manual request. It uses artificial observations, runs only in public repositories, and does not validate agreement with an untested official SAV.
