# Generational Differences in Sharing Visuals by Phone and Preserving Digital Files

[![Software and public aggregate checks](https://github.com/ThreeMonth03/tscs2024-visuals-reproduction/actions/workflows/public-reproducibility.yml/badge.svg)](https://github.com/ThreeMonth03/tscs2024-visuals-reproduction/actions/workflows/public-reproducibility.yml)

**Original Chinese title:** 使用手機分享影像以及數位保存方式的世代差異分析

This package analyses phone photography and video recording, sharing photos and videos, and personal digital file practices across age, education and area groups. It calculates results from a user-supplied SPSS file for the 2024 Taiwan Social Change Survey (TSCS), Digital Society module. The study's aggregate results are also included for comparison and figure regeneration.

## Choose your starting point

| What you want to do | Start here |
|---|---|
| Recalculate from an official SAV you obtained | Upload one SAV to `data/official/`, then run all Notebook cells |
| See the existing results without a survey file | Set `MODE = "aggregate"`, then run all cells |
| Practise without survey records | Use the generated artificial SAV described in the [Notebook guide](docs/NOTEBOOK.md) |

[Open the Binder Notebook](https://binder.depositar.io/v2/gh/ThreeMonth03/tscs2024-visuals-reproduction/main?urlpath=lab%2Ftree%2Fnotebooks%2Freproduce.ipynb). In JupyterLab's left file browser, click the **home icon**, open **data → official**, and upload your SAV. Return to the Notebook tab and choose **Run → Run All Cells**. The default `survey` mode finds the file and checks its metadata. At the bottom, view nine figures or download the results ZIP. Download before the temporary Binder session ends.

## Your survey file

Obtain the official SAV and its documentation from [TSCS or SRDA](docs/DATA_ACCESS.md). Keep the original filename: no rename is required when `data/official/` contains exactly one SAV. With the default settings, the Notebook identifies the required variables and response categories from the file's metadata. Incomplete or ambiguous labels require a first-time confirmation; setup names what needs attention and stops before analysis. Once a release's mapping is confirmed, it can be reused with that release. The [Notebook guide](docs/NOTEBOOK.md) explains how.

The software follows the documented structure of historical public releases. Compatibility with a particular release is verified from that release's file and codebook; no unreleased variable mapping is bundled. Calculations retain the fixed 141-test and 266-contrast correction families. An optional population-target file enables an additional calibration check. The main analysis, supplied alternative-weight comparison and sampling-unit deletion checks run without that target file.

To run the same Notebook on your computer, install **Python 3.14.4**, then:

```bash
git clone https://github.com/ThreeMonth03/tscs2024-visuals-reproduction.git
cd tscs2024-visuals-reproduction
python3.14 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-notebook.txt
mkdir -p data/official
jupyter lab notebooks/reproduce.ipynb
```

Upload to `data/official/` in your local JupyterLab, or set `DATA_FILE` to a file already on your computer. See [local execution](docs/REPLICATION.md) for command-line runs and [input profiles](docs/INPUT_PROFILE.md) for advanced configuration.

## Outputs and data boundaries

Survey mode renders figures from the **current run's newly estimated tables**. Aggregate mode renders the bundled estimates. Both modes provide nine figures and a ZIP of figures and aggregate tables through the Notebook. Inputs, respondent rows, local profiles, metadata catalogues and execution logs are excluded from the ZIP.

No respondent data are distributed or automatically downloaded. Follow the official provider's terms; use cloud processing only when those terms permit it. CI checks software and existing aggregate results in public repositories only. Basic checks run on each push to `main`, pull request and manual run. The full Notebook test uses artificial data and runs for program, Notebook, environment or analysis-reference changes, or when manually requested. See [CI scope and triggers](docs/CI.md); CI does not establish agreement with an untested official SAV.

## Documentation

- [Notebook upload, settings, previews and downloads](docs/NOTEBOOK.md)
- [Resolve input mapping and advanced configuration](docs/INPUT_PROFILE.md)
- [Local execution](docs/REPLICATION.md)
- [Official sources and historical format evidence](docs/DATA_ACCESS.md)
- [Automated checks](docs/CI.md)
- [Research terms and denominators](docs/TERMINOLOGY.md)
- [Aggregate provenance](docs/PROVENANCE.md)
- [Official township classification](reference_data/README.md)
- [References and licensed PDFs](references/README.md)

Original code and documentation are licensed under [MIT](LICENSE). Survey materials, aggregate results and references retain their own terms; see [RIGHTS.md](RIGHTS.md). Cite the package using [CITATION.cff](CITATION.cff) and record the commit used.
