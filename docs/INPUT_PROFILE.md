# Configure your official survey file

The software reads an SPSS `.sav` file and a local JSON profile that connects its variables and value codes to the analysis. The distributed code does not contain a mapping for an unreleased survey file. Use the questionnaire, coding instructions and sampling documentation supplied with your official release.

## Create the profile

After uploading your official file into Binder's `data/official/` folder, open a terminal and run:

```bash
python run.py inspect \
  --data-file /home/jovyan/data/official/survey.sav \
  --output-profile /home/jovyan/data/official/profile.json
```

The command creates `profile.json` and `profile-metadata.json` in that folder. The metadata catalogue lists the names, labels, response codes and missing-value ranges from **your uploaded file**, with no respondent rows. Open these JSON files in JupyterLab, fill the empty entries in `profile.json`, and save it. They are local configuration files, not result downloads.

For local use, replace the paths with e.g. `~/Documents/TSCS/data/official/survey.sav` and `~/Documents/TSCS/data/official/profile.json`. Filenames are examples: use the actual name of your downloaded file.

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

This is an illustrative fragment; the generated profile contains all required roles. `value_maps` converts source response codes into the analysis categories below. Its initial identity maps are **templates to review**, not an assertion about your release. For example, if the source encodes a category as `10`, change its entry to `"10": 1`. An unlisted nonmissing response stops analysis.

| Role | Analysis categories |
|---|---|
| `photography`, `video_recording`, `sharing_with_contacts`, `sharing_with_unspecified_audiences` | 1 several times/day; 2 daily; 3 several times/week; 4 several times/month; 5 less often; 6 never |
| Additional equipment responses | Photography: 7 phone cannot take photos, 8 no phone; video: 7 phone cannot record videos |
| `personal_files` | 1 original device; 2 personal computer or hard disk; 3 other storage media or print; 4 cloud; 5 other; 6 does not produce files; 7 has not considered storage |
| `age_group` | 1 age18–29; 2 age30–39; 3 age40–49; 4 age50–59; 5 age60–69; 6 age70+ |
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

This creates a synthetic `survey.sav`, its complete `profile.json`, and synthetic `calibration.json`. Use these three files to practise upload and execution; they do not contain real respondents or reproduce the study's empirical findings. See [the Notebook guide](NOTEBOOK.md) for running and downloading results.
