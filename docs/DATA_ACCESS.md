# Data sources and access

## Official source

This study uses the 2024 Taiwan Social Change Survey (TSCS), Cycle 8, Year 5, Digital Society module. Obtain survey data directly through the provider's publication or access process:

- [TSCS questionnaires and reports](https://www2.ios.sinica.edu.tw/sc/cht/scDownload2.php#eighth)
- [TSCS series at SRDA](https://srda.sinica.edu.tw/plan/?idx=SRDA.AS002)
- [SRDA data-access portal](https://srda.sinica.edu.tw/)
- [TSCS data-use and acknowledgement requirements](https://www2.ios.sinica.edu.tw/sc/cht/scDownload3.php)

Use the provider's citation and acknowledgement instructions. The code's MIT license does not license the survey data or questionnaire. This repository does not redistribute either and does not provide an automatic data downloader.

## Analyze your own copy

The SAV input workflow is built on the working assumption that the new official release follows the documented format of previous public TSCS releases: an SPSS data file with accompanying variable and response-code documentation. The mapping profile makes the release-specific connection explicit; no unpublished schema is bundled with the code.

Historical evidence: the [2023 public release guide](https://srda.sinica.edu.tw/file/5f372e16-2f84-46ad-8728-5569c6ca8c0f) and [public variable catalogue](https://srda.sinica.edu.tw/search/survey/detail/C00401_2/0) document labelled survey responses, demographic groups, sampling design, geography and alternative final weights. The [2022 guide](https://srda.sinica.edu.tw/file/919768fb-aca7-446b-bd14-8140500b0965) documents the same core release structure with grouping syntax. These earlier surveys establish the input-format assumption; their observations are not substituted for the 2024 Digital Society data.

Create a profile from your own file:

```bash
python run.py inspect \
  --data-file "$HOME/Documents/TSCS/data/official/survey.sav" \
  --output-profile "$HOME/Documents/TSCS/data/official/profile.json"
```

Complete the profile using the downloaded release's documentation and the [input-profile guide](INPUT_PROFILE.md). The inspection output and profile remain local. They are not included in the results ZIP. The [Notebook guide](NOTEBOOK.md) gives exact local paths, Binder upload steps and settings.

A survey run estimates the Question E outcomes using the mapped inputs. Required variables, response coding, grouping, weights and survey design are checked. Additional population calibration uses an optional target file; when targets are not supplied, that sensitivity check is marked unavailable. The complete statistical comparison families remain defined, including records of unavailable or failed comparisons.

The working assumption enables implementation and testing before a new release arrives. Compatibility with a particular official release is established by running that release, checking the mapping, and comparing the results. Tests with artificial data validate the software workflow; they do not establish agreement with an as-yet untested official dataset.

## Local and cloud execution

Run the Notebook locally when the data must remain on your computer. Binder supports manual file upload, but use it only when your data-use conditions permit processing on that cloud service. Files uploaded into a session are not automatically published as GitHub files or depositar dataset resources by this workflow. Input files are excluded from Git, CI and the downloadable results ZIP.

Automated cloud tests use generated artificial data. Respondent files are not included in those tests.

## Bundled aggregate results

The repository also includes ten study-produced aggregate tables from 1,338 respondents: group proportions, sample sizes, tests and sensitivity results. Their catalogue and checksums are in `manifest.json`.

`aggregate` mode checks these fixed tables and redraws nine figures. `survey` mode calculates new tables from the supplied SAV and uses those new tables for the figures and ZIP. The Notebook and download summary state which mode produced the results. See [RIGHTS.md](../RIGHTS.md) for code, aggregate-result and third-party licensing.
