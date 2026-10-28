# Input setup and advanced configuration

Start with [the Notebook's upload-and-run workflow](NOTEBOOK.md). With a single SAV in `data/official/`, leave `DATA_FILE` and `PROFILE_FILE` blank. The program first looks for a completed `profile.json` or a profile named after the SAV, such as `survey.profile.json`, beside the input. Otherwise it uses the file's labels and metadata to identify the analysis inputs. It checks the resulting mapping before analysis. If both profile names are present, select one explicitly with `PROFILE_FILE`.

Use this guide when setup asks for confirmation or you want to supply a mapping explicitly. A profile connects your release's variables and value codes to the analysis. No mapping for an unreleased file is distributed. Confirm any unresolved inputs from the codebook and sampling documentation supplied with your official release.

## If automatic setup needs confirmation

The error names the unresolved inputs and gives paths to a profile draft and metadata catalogue beside your SAV. Existing files are preserved. The catalogue lists column labels, response codes and missing-value definitions from **your file**, without respondent rows.

For a small correction, update `INPUT_OVERRIDES` in the Notebook's settings cell. This artificial example chooses the photography column:

```python
INPUT_OVERRIDES = {
    "columns": {"photography": "demo_photo"}
}
```

Replace the example with a column from your file. Overrides use the profile's structure: `columns`, `value_maps`, `missing_values` and `design`. They are local settings; do not commit personal mappings or outputs. Rerun the settings cell and all following cells after making a correction.

For several changes, open the generated profile draft from JupyterLab's file browser: **right-click → Open With → Editor**. Double-clicking a JSON file may open the read-only tree viewer instead. Complete the unresolved entries, save the file, and set `PROFILE_FILE` to the draft's full path shown by setup. Use the metadata catalogue and official documentation together; the remaining sections explain the profile's fields.

After validation, keep that profile with your local copy of the release. Select it explicitly on later runs, or save a copy as `profile.json` beside the SAV for automatic selection. Download the profile separately from JupyterLab before a Binder session ends; it is intentionally excluded from the results ZIP. Recheck the mapping when switching releases.

## Create a profile manually

This is an alternative to automatic setup. In Binder, open **File → New → Terminal** and run the commands below. The first command matters: a Terminal may open inside the folder selected in the file browser.

```bash
cd /home/jovyan
python run.py inspect \
  --data-file /home/jovyan/data/official/survey.sav \
  --output-profile /home/jovyan/data/official/profile.json
```

Use your uploaded SAV's actual filename. The command creates `profile.json` and `profile-metadata.json` in that folder. If those files already exist, choose new output names. Open the profile using **Open With → Editor**, fill its empty entries, review the response maps, and save it. Set `PROFILE_FILE` in the Notebook to the completed profile's path. These local configuration files are excluded from result downloads.

For local use, run from the repository root and replace the paths with, for example, `"$HOME/Documents/TSCS/data/official/survey.sav"` and `"$HOME/Documents/TSCS/data/official/profile.json"`.

## Connect columns and responses

`columns` maps each semantic role to a variable name in your file. For example, an artificial file could use:

```json
{
  "columns": {
    "photography": "demo_photo",
    "age_group": "demo_age",
    "primary_weight": "demo_weight"
  }
}
```

This is an illustrative fragment; the generated profile contains all required roles. `value_maps` converts source response codes into the analysis categories below. The manual `inspect` command starts with identity maps: these are **templates to review**, not an assertion about your release. For example, if the source encodes a category as `10`, change its entry to `"10": 1`. An unlisted nonmissing response stops analysis.

| Role | Analysis categories |
|---|---|
| `photography`, `video_recording`, `sharing_with_contacts`, `sharing_with_unspecified_audiences` | 1 several times/day; 2 daily; 3 several times/week; 4 several times/month; 5 less often; 6 never |
| Additional equipment responses | Photography: 7 phone cannot take photos, 8 no phone; video: 7 phone cannot record videos |
| `personal_files` | 1 original device; 2 personal computer or hard disk; 3 other storage media or print; 4 cloud; 5 other; 6 does not produce files; 7 has not considered storage |
| `age_group` | 1 age 18–29; 2 age 30–39; 3 age 40–49; 4 age 50–59; 5 age 60–69; 6 age 70+ |
| `education_group` | 1 elementary or below; 2 junior high; 3 senior high/vocational; 4 college or above |
| `sex_group` | 1 male; 2 female |
| `primary_weight`, `alternative_weight` | Positive numeric official final weights; main unequal-probability start and alternative unit start, respectively |

These are analysis encodings, not a reproduction of a questionnaire or a list of provider variable names. Prefer the release's documented age and education groups. If these are absent, construct them using the official grouping syntax and fixed survey reference year before running this pipeline; do not substitute age at the current date. SPSS user-missing ranges are read automatically. Additional missing codes can be specified per semantic role in `missing_values`.

## Sampling units and geography

Specify `stratum` plus either an already constructed `cluster`, or `first_stage_unit` and `second_stage_unit`. In the latter case, `design.second_stage_strata` lists the source stratum codes whose first variance unit is the second-stage unit in the file. Set this from the official sampling documentation. Each analysis stratum must contain at least two variance clusters. The software does not replace a missing complex design with a simple random sample.

For geography, `location` normally points to a variable whose value labels are complete county-and-township names. The loader matches these labels to the [official 368-township classification](../reference_data/README.md). Alternatively, map an already validated area variable to `area` and supply its `value_maps`: 1 digitally mature, 2 non-mature. Do not replace this classification with an urban/rural variable.

The analysis always compares age and education groups within the whole sample and within both area groups. Frequency denominators include substantive frequency responses; the storage-location denominator includes the four specified locations. Missing design, grouping or weight information stops the full analysis with a message explaining what to configure.

## Optional additional calibration check

The official alternative-weight analysis uses `alternative_weight` from the SAV. A separate archived supplemental check recalibrates the main weights to population margins. To reproduce that extra check, supply `calibration.json` containing four objects named `sex`, `age`, `education` and `stratum`; each maps the analysis category or source stratum code to its population proportion. Each object's values must be finite and positive; the program normalizes them to proportions summing to 1. Use the population margins from the official report, not proportions guessed from this sample.

Set `CALIBRATION_FILE` to this file. If it is empty, the extra recalibration scenario is marked unavailable; the main analysis, supplied alternative weights and sampling-unit deletion checks remain separate. No stored estimate is substituted for a missing scenario. The fixed 141-test and 266-contrast families are retained.

## Try the complete configuration with artificial data

```bash
python run.py demo --output-dir /tmp/tscs-demo
```

This creates a synthetic `survey.sav`, its complete `profile.json`, and synthetic `calibration.json`. Uploading only the SAV tests automatic setup; supplying the two JSON files also exercises explicit profile selection and the extra calibration check. These files contain no real respondents. See [the Notebook guide](NOTEBOOK.md) for running and downloading results.
