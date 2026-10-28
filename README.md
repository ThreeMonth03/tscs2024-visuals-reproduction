# Generational Differences in Sharing Visuals by Phone and Preserving Digital Files

[![Public reproducibility checks](https://github.com/ThreeMonth03/tscs2024-visuals-reproduction/actions/workflows/public-reproducibility.yml/badge.svg)](https://github.com/ThreeMonth03/tscs2024-visuals-reproduction/actions/workflows/public-reproducibility.yml)

**Original Chinese title:** 使用手機分享影像以及數位保存方式的世代差異分析

This package analyses phone photography and video recording, sharing photos and videos, and personal digital file practices across age, education and area groups. It supports manual SPSS input for the 2024 Taiwan Social Change Survey (TSCS), Digital Society module, and includes the study's aggregate results for comparison and figure regeneration.

## Choose your starting point

| What you want to do | Start here |
|---|---|
| See the existing results without a survey file | Open the Notebook in `aggregate` mode; run all cells |
| Recalculate from an official SAV you obtained | Upload the file, configure its input profile, select `survey` mode |
| Practise the complete upload-to-results workflow | Generate the artificial demo files and run them in `survey` mode |

[Open the Binder Notebook](https://binder.depositar.io/v2/gh/ThreeMonth03/tscs2024-visuals-reproduction/main?urlpath=lab%2Ftree%2Fnotebooks%2Freproduce.ipynb). The [Notebook guide](docs/NOTEBOOK.md) gives the exact upload folder, settings, figure preview and ZIP download steps. Download results before the temporary Binder session ends.

## Manual data input

Obtain the official SAV and its coding/sampling documentation from [TSCS or SRDA](docs/DATA_ACCESS.md). The software uses the historical public-release format as its working contract: labelled SPSS responses, documented demographic groups, sampling design, geographic labels and two official weights. Compatibility with the target release is checked when the official file is supplied. An input profile connects that file to the semantic analysis roles; no unreleased variable mapping is bundled.

Locally:

```bash
git clone https://github.com/ThreeMonth03/tscs2024-visuals-reproduction.git
cd tscs2024-visuals-reproduction
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-notebook.txt
python run.py inspect \
  --data-file "$HOME/Documents/TSCS/data/official/survey.sav" \
  --output-profile "$HOME/Documents/TSCS/data/official/profile.json"
```

Complete the profile using the [input guide](docs/INPUT_PROFILE.md), then run:

```bash
python run.py reestimate \
  --data-file "$HOME/Documents/TSCS/data/official/survey.sav" \
  --profile-file "$HOME/Documents/TSCS/data/official/profile.json" \
  --output-dir "$HOME/Documents/TSCS/results/run-01"
```

The run estimates new proportions, design-based uncertainty, hypothesis tests and sensitivity results. It retains the fixed 141-test and 266-contrast correction families. An additional population-margin calibration check accepts an optional local configuration file; without it that supplemental scenario is marked unavailable. The supplied alternative-weight comparison remains a separate calculation.

To practise with artificial data, run `python run.py demo --output-dir /tmp/tscs-demo` and use the three generated files. To check existing aggregate results only, run `python run.py verify-only`; to redraw them, use `python run.py figures --output-dir /tmp/tscs-figures-01`.

## Outputs and data boundaries

Survey mode renders figures from the **current run's newly estimated tables**. Aggregate mode renders the bundled estimates. Both modes provide nine figures and a ZIP of figures and aggregate tables through the Notebook. Inputs, respondent rows, local profiles, metadata catalogues and execution logs are excluded from the ZIP.

No respondent data are distributed or automatically downloaded. Follow the official provider's terms; use cloud processing only when those terms permit it. Public CI runs only in public repositories and tests artificial inputs plus the existing aggregates. It never obtains actual survey records.

## Documentation

- [Notebook upload, settings, previews and downloads](docs/NOTEBOOK.md)
- [Configure a local input profile](docs/INPUT_PROFILE.md)
- [Local execution](docs/REPLICATION.md)
- [Official sources and historical format evidence](docs/DATA_ACCESS.md)
- [Automated checks](docs/CI.md)
- [Research terms and denominators](docs/TERMINOLOGY.md)
- [Aggregate provenance](docs/PROVENANCE.md)
- [Official township classification](reference_data/README.md)
- [References and licensed PDFs](references/README.md)

Original code and documentation are licensed under [MIT](LICENSE). Survey materials, aggregate results and references retain their own terms; see [RIGHTS.md](RIGHTS.md). Cite the package using [CITATION.cff](CITATION.cff) and record the commit used.
