#!/usr/bin/env python3
"""Validate published aggregates without reestimating respondent-level statistics.

BY adjustments and sensitivity flags are independently reconstructed. The frozen
141- and 266-test families, including unestimable tests, remain unchanged.
"""
from __future__ import annotations

import argparse
import ast
from collections import Counter, defaultdict
import csv
import hashlib
import json
import math
from pathlib import Path

Row = dict[str, str]
OMNIBUS_FAMILY = 141
CONTRAST_FAMILY = 266
PROFILE_COUNT = 1683
DELETION_SCENARIOS = {f"delete_{index:02d}" for index in range(1, 71)}
ESTIMABLE_DELETIONS = 64
PROFILE_GROUP_FIELDS = ("outcome", "area", "factor", "level")
SUMMARY_FIELDS = (
    "estimate", "std_error", "conf_low", "conf_high", "statistic", "df",
    "p_value", "q_by_266",
)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def read_csv(path: Path) -> list[Row]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def number(value: str | None) -> float:
    return float(value) if value not in ("", "nan", "NaN", None) else math.nan


def near(actual: float, expected: float, label: str) -> None:
    if math.isnan(actual) or math.isnan(expected):
        require(math.isnan(actual) and math.isnan(expected), "Missing-value mismatch: " + label)
        return
    require(math.isfinite(actual) and math.isfinite(expected), "Nonfinite value: " + label)
    require(math.isclose(actual, expected, abs_tol=1e-11, rel_tol=1e-8), "Numeric mismatch: " + label)


def by_adjust(p_values: list[float]) -> list[float]:
    require(bool(p_values), "Empty BY family")
    require(all(math.isfinite(p) and 0 <= p <= 1 for p in p_values), "p outside [0,1]")
    family_size = len(p_values)
    order = sorted(range(family_size), key=p_values.__getitem__)
    harmonic = math.fsum(1.0 / rank for rank in range(1, family_size + 1))
    result, running = [math.nan] * family_size, 1.0
    for rank in range(family_size, 0, -1):
        index = order[rank - 1]
        running = min(running, p_values[index] * family_size * harmonic / rank)
        result[index] = running
    return result


def check_family(rows: list[Row], family: int, id_column: str, q_column: str) -> float:
    require(len(rows) == family, "Unexpected family size")
    require(len({row[id_column] for row in rows}) == family, "Duplicate test IDs")
    p_values = []
    for row in rows:
        p_value, q_value = number(row["p_value"]), number(row[q_column])
        if row["status"] == "estimated":
            require(math.isfinite(p_value) and 0 <= p_value <= 1, "Estimated test needs finite p in [0,1]")
            require(math.isfinite(q_value) and 0 <= q_value <= 1, "Estimated test needs finite q in [0,1]")
            p_values.append(p_value)
        else:
            require(math.isnan(p_value) and math.isnan(q_value), "Unestimable p and q should be missing")
            # Preserve the fixed family, but never report this placeholder as an estimate.
            p_values.append(1.0)
    adjusted = by_adjust(p_values)
    errors = []
    for row, expected in zip(rows, adjusted, strict=True):
        if row["status"] == "estimated":
            actual = number(row[q_column])
            near(actual, expected, row[id_column])
            errors.append(abs(actual - expected))
    return max(errors, default=0.0)


def group_by(rows: list[Row], key: str) -> dict[str, list[Row]]:
    groups = defaultdict(list)
    for row in rows:
        groups[row[key]].append(row)
    return dict(groups)


def check_bundle(root: Path) -> tuple[int, int]:
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    require(manifest["data_included"] is False, "Public bundle must exclude individual data")
    for relative, item in manifest["files"].items():
        path = root / relative
        require(not Path(relative).is_absolute() and ".." not in Path(relative).parts,
                "Invalid manifest path: " + relative)
        require(path.resolve().is_relative_to(root.resolve()) and not path.is_symlink(),
                "Manifest path leaves bundle: " + relative)
        require(path.is_file(), "Missing manifest file: " + relative)
        require(hashlib.sha256(path.read_bytes()).hexdigest() == item["sha256"],
                "Changed manifest file: " + relative)
    sources = [root / "run.py"] + sorted((root / "helpers").glob("*.py")) + sorted((root / "ci").glob("*.py"))
    for path in sources:
        ast.parse(path.read_text(encoding="utf-8"), filename=str(path.relative_to(root)))
    return len(manifest["files"]), len(sources)


def check_profiles(rows: list[Row], expected_count: int = PROFILE_COUNT) -> None:
    require(len(rows) == len({row["estimate_id"] for row in rows}) == expected_count,
            "Profile count changed")
    groups = defaultdict(list)
    for row in rows:
        require(0 <= number(row["estimate"]) <= 1, "Proportion outside [0,1]")
        require(0 <= int(row["event_n"]) <= int(row["n"]), "Invalid event count / denominator")
        groups[tuple(row[key] for key in PROFILE_GROUP_FIELDS)].append(row)
    for key, categories in groups.items():
        require(len({row["category"] for row in categories}) == len(categories), "Repeated profile category")
        require(len({row["n"] for row in categories}) == 1, "Category denominators differ")
        require(sum(int(row["event_n"]) for row in categories) == int(categories[0]["n"]),
                "Category event counts do not sum to denominator")
        near(math.fsum(number(row["estimate"]) for row in categories), 1.0, str(key))


def check_omnibus(base: Path) -> list[float]:
    scenarios = group_by(read_csv(base / "primary/scenario_tests.csv"), "scenario")
    require(set(scenarios) == {"primary", "alternative"} | DELETION_SCENARIOS,
            "Wrong BY141 scenario set")
    errors = [check_family(rows, OMNIBUS_FAMILY, "test_id", "q_by_141") for rows in scenarios.values()]
    for weight in ("primary", "alternative"):
        tests = read_csv(base / weight / "formal_tests.csv")
        errors.append(check_family(tests, OMNIBUS_FAMILY, "test_id", "q_by_141"))
        require(Counter(row["layer"] for row in tests) ==
                {"eda": 91, "probability_omnibus": 10, "probability_contrast": 40},
                "BY141 component counts changed")
        check_profiles(read_csv(base / weight / "descriptive_profiles.csv"))
    return errors


def check_contrast_scenarios(rows: list[Row]) -> list[float]:
    scenarios = group_by(rows, "scenario")
    require(set(scenarios) == {"primary", "alternative"} | DELETION_SCENARIOS,
            "Wrong BY266 scenario set")
    errors = []
    for family in scenarios.values():
        require(Counter(row["area"] for row in family) == {"0": 98, "1": 84, "2": 84},
                "Domain comparison counts changed")
        errors.append(check_family(family, CONTRAST_FAMILY, "contrast_id", "q_by_266"))
        for row in family:
            if row["status"] == "estimated":
                estimate, error = number(row["estimate"]), number(row["std_error"])
                require(math.isfinite(estimate) and math.isfinite(error) and error > 0,
                        "Estimated contrast needs finite estimate and positive standard error")
                near(estimate / error, number(row["statistic"]), row["contrast_id"])
    return errors


def check_sensitivity(rows: list[Row], summary: list[Row]) -> None:
    per_contrast = group_by(rows, "contrast_id")
    summary_ids = [row["contrast_id"] for row in summary]
    require(len(summary_ids) == len(set(summary_ids)) == len(per_contrast) == CONTRAST_FAMILY,
            "Contrast summary count changed")
    require(set(summary_ids) == set(per_contrast), "Contrast summary IDs differ")
    for row in summary:
        scenarios = per_contrast[row["contrast_id"]]
        values = {result["scenario"]: result for result in scenarios}
        require(len(scenarios) == len(values) and
                set(values) == {"primary", "alternative"} | DELETION_SCENARIOS,
                "Contrast scenario IDs differ")
        main, alternative = values["primary"], values["alternative"]
        deleted = [values[name] for name in DELETION_SCENARIOS]
        valid = [result for result in deleted if result["status"] == "estimated"]
        for prefix, result in (("primary", main), ("alternative", alternative)):
            for field in SUMMARY_FIELDS:
                near(number(row[prefix + "_" + field]), number(result[field]), row["contrast_id"] + field)
        significant = sum(number(result["q_by_266"]) < .05 for result in valid)
        reversals = sum(number(result["estimate"]) * number(main["estimate"]) < 0 for result in deleted)
        require(int(row["deletion_estimable"]) == len(valid), "Deletion estimability mismatch")
        require(int(row["deletion_significant"]) == significant, "Deletion significance mismatch")
        require(int(row["deletion_direction_reversals"]) == reversals, "Direction mismatch")
        supported = (number(main["q_by_266"]) < .05 and number(alternative["q_by_266"]) < .05
                     and number(alternative["estimate"]) * number(main["estimate"]) > 0
                     and len(valid) == significant == ESTIMABLE_DELETIONS and reversals == 0)
        require(row["supported_all_checks"] in {"True", "False"}, "Invalid sensitivity support flag")
        require((row["supported_all_checks"] == "True") == supported, "Sensitivity support flag mismatch")


def validate(root: Path) -> dict:
    manifest_files, parsed_sources = check_bundle(root)
    errors = check_omnibus(root / "aggregates")
    directory = root / "aggregates/contrasts"
    scenarios = read_csv(directory / "all_scenarios.csv")
    summary = read_csv(directory / "contrast_summary.csv")
    errors.extend(check_contrast_scenarios(scenarios))
    check_sensitivity(scenarios, summary)
    return {
        "status": "pass", "individual_data_read": False, "statistical_reestimation": False,
        "manifest_files_verified": manifest_files, "python_sources_parsed": parsed_sources,
        "by141_scenarios": 72, "by141_alternative_weight_family": OMNIBUS_FAMILY,
        "by266_scenarios": 72, "by266_rows": len(scenarios), "contrast_summaries": len(summary),
        "max_by_absolute_error": max(errors),
        "scope": "Integrity, syntax, aggregate internal consistency, independent BY recalculation and sensitivity-flag reconstruction. Survey estimates and variances are not reestimated.",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = validate(args.root.resolve())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
