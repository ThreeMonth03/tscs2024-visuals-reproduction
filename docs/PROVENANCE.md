# Aggregate provenance and verification scope

The published results come from the study of phone photography, video recording, sharing audiences, and personal digital file practices using the 2024 Taiwan Social Change Survey, Digital Society module. Cite the study using [CITATION.cff](../CITATION.cff) and follow the survey provider's acknowledgement requirements in [DATA_ACCESS.md](DATA_ACCESS.md).

## Fixed numerical inputs

`aggregates/` contains ten aggregate result tables with the study's estimates, sample sizes, test results, and sensitivity comparisons. `manifest.json` identifies these aggregate files and their checksums. These tables supply the numerical inputs to aggregate mode and serve as preserved comparison evidence for survey mode.

| Directory | Contents | Tables |
|---|---|---|
| `aggregates/primary/` | Main descriptive estimates, adjusted estimates, formal tests, and diagnostic scenarios | 4 |
| `aggregates/alternative/` | Descriptive estimates, adjusted estimates, and formal tests using alternative weights | 3 |
| `aggregates/contrasts/` | Storage profiles, proportion contrasts across scenarios, and contrast summaries | 3 |

The package preserves two multiple-testing families: 141 tests and 266 proportion contrasts. Each proportion-contrast scenario includes 98 comparisons for all adults and 84 within each of the two area groups. Changing the set of comparisons would change the adjustment being checked.

The label `alternative` has a table-specific meaning:

| Table or columns | Meaning |
|---|---|
| `primary/scenario_tests.csv`, `scenario=alternative` | Additional calibration of the main weights to population margins |
| The three tables in `alternative/` | Official alternative survey weights |
| `contrasts/all_scenarios.csv` and `contrasts/location_profiles.csv`, `scenario=alternative` | Official alternative survey weights |
| `contrasts/contrast_summary.csv`, `alternative_*` columns | Results using official alternative survey weights |

The additional calibration check requires population targets. In survey mode, leaving `CALIBRATION_FILE` blank marks that check unavailable; it does not skip the official alternative-weight analysis. The ZIP includes this table-specific guide in `README.txt` and `summary.json`.

## What each mode establishes

- File checks identify whether the supplied package matches its recorded contents.
- Numerical checks recalculate multiple-testing adjustments and sensitivity summaries from the aggregate results.
- Plotting regenerates nine figures from the supplied estimates and uncertainty measures.
- Notebook checks exercise settings, previews, and aggregate downloads.

The operations above describe aggregate mode. Survey mode reads a user-supplied SAV through a local profile and recalculates estimates, uncertainty, tests and sensitivity tables before rendering figures. Its statistical functions have been checked against the adopted results using authorized local data. The manual-input workflow uses historical public-release structure as its contract; the target official release itself has not yet been verified. Artificial data exercise CI and the cloud upload workflow. These checks have distinct purposes and are reported separately.

## Figure labels and citation

The interface and figure labels use English. The original Chinese study title and official reference titles remain as bibliographic information. The [terminology guide](TERMINOLOGY.md) explains the outcome definitions, comparison groups, and denominators used by the figures.

Record the package commit or release when citing a result or sharing a Binder link. Generated files identify their aggregate source; software and font differences can affect rendering without changing the plotted values.

## Fixed research archive

[depositar, ark:37281/k5j350466](https://pid.depositar.io/ark:37281/k5j350466), preserves a recorded code snapshot, the ten aggregate tables, nine figures and supplementary appendices, with an index and file checksums. The archive's metadata and included manifest identify its version. GitHub may contain later software or documentation changes, so cite the commit used for a new run and the archive identifier for the preserved materials.

The archive can check the stored summaries and regenerate figures without respondent records. Reestimating from individual observations requires an official SAV obtained by the user, with its mapping and available inputs checked against that release's documentation. Neither the archive nor successful artificial-data tests establish agreement with an official release that has not yet been tested. Rights remain separated by component as described in [RIGHTS.md](../RIGHTS.md) and the archive's rights statement.
