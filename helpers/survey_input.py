"""Read a user-owned SPSS file through an explicit, local semantic profile.

No survey-specific source column names or unpublished questionnaire text are
distributed. Profiles and metadata stay with the user's input files.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import unicodedata

import numpy as np
import pandas as pd
import pyreadstat


ACTIVITIES = ("photography", "video_recording", "sharing_with_contacts",
              "sharing_with_unspecified_audiences")
CATEGORIES = {**{name: list(range(1, 7)) for name in ACTIVITIES},
              "photography": list(range(1, 9)), "video_recording": list(range(1, 8)),
              "personal_files": list(range(1, 8)), "age_group": list(range(1, 7)),
              "education_group": list(range(1, 5)), "sex_group": [1, 2], "area": [1, 2]}
REQUIRED = (*ACTIVITIES, "personal_files", "age_group", "education_group", "sex_group",
            "stratum", "primary_weight", "alternative_weight")
ROOT = Path(__file__).resolve().parents[1]


def key(value: object) -> str:
    if isinstance(value, (int, float, np.number)) and np.isfinite(value):
        return str(int(value)) if float(value).is_integer() else str(value)
    return str(value)


def dump(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")


def profile_template() -> dict:
    return {
        "schema_version": 1,
        "columns": {name: "" for name in (*REQUIRED, "first_stage_unit", "second_stage_unit", "location")},
        "value_maps": {name: {str(code): code for code in codes}
                       for name, codes in CATEGORIES.items() if name != "area"},
        "missing_values": {},
        "design": {"second_stage_strata": []},
        "geography": {"use_value_labels": True},
        "notes": "Fill source columns and check all value maps against your official release. See docs/INPUT_PROFILE.md.",
    }


def inspect_survey(data_file: Path, output_profile: Path) -> dict:
    """Write a draft profile and local metadata catalogue, never case rows."""
    data_file, output_profile = Path(data_file).expanduser().resolve(), Path(output_profile).expanduser().resolve()
    metadata_file = output_profile.with_name(output_profile.stem + "-metadata.json")
    if output_profile.exists() or metadata_file.exists():
        raise FileExistsError("Choose unused profile and metadata paths")
    if output_profile.is_relative_to(ROOT) or metadata_file.is_relative_to(ROOT):
        # Binder's upload area is inside its checkout, and is explicitly ignored.
        allowed = ROOT / "data" / "official"
        if not output_profile.is_relative_to(allowed):
            raise ValueError("Save profiles beside your private input, outside tracked source folders")
    _, metadata = pyreadstat.read_sav(data_file, metadataonly=True, user_missing=True)
    catalogue = {"variables": [{"column": name,
                 "label": metadata.column_names_to_labels.get(name),
                 "values": {key(k): v for k, v in metadata.variable_value_labels.get(name, {}).items()},
                 "missing_ranges": metadata.missing_ranges.get(name, [])}
                for name in metadata.column_names],
                "purpose": "Local input configuration only; excluded from result downloads."}
    output_profile.parent.mkdir(parents=True, exist_ok=True)
    dump(output_profile, profile_template())
    dump(metadata_file, catalogue)
    return {"profile": str(output_profile), "metadata": str(metadata_file), "status": "needs_configuration"}


def _missing(series: pd.Series, source: str, role: str, profile: dict, metadata) -> pd.Series:
    mask = series.isna()
    custom = {key(v) for v in profile.get("missing_values", {}).get(role, [])}
    mask |= series.map(key).isin(custom)
    for span in metadata.missing_ranges.get(source, []):
        low, high = span["lo"], span["hi"]
        if low == high:
            mask |= series.eq(low)
        elif pd.api.types.is_numeric_dtype(series):
            mask |= series.between(low, high)
    return mask


def _recode(series: pd.Series, source: str, role: str, profile: dict, metadata) -> pd.Series:
    mapping = profile.get("value_maps", {}).get(role)
    if not isinstance(mapping, dict) or not mapping:
        raise ValueError(f"Configure value_maps for {role}")
    allowed = CATEGORIES[role]
    if any(isinstance(v, bool) or v not in allowed for v in mapping.values()):
        raise ValueError(f"Invalid target categories for {role}; see INPUT_PROFILE.md")
    missing = _missing(series, source, role, profile, metadata)
    mapped = series.map(key).map(mapping)
    if (mapped.isna() & ~missing).any():
        raise ValueError(f"Unmapped responses for {role}; check the local metadata and profile")
    return mapped.where(~missing, np.nan).astype(float)


def _place(value: object) -> str:
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", str(value))).replace("台", "臺")


def load_survey(data_file: Path, profile_file: Path) -> tuple[pd.DataFrame, dict]:
    """Return semantic analysis fields in memory; do not write cleaned records."""
    data_file, profile_file = Path(data_file).expanduser().resolve(), Path(profile_file).expanduser().resolve()
    profile = json.loads(profile_file.read_text(encoding="utf-8"))
    if profile.get("schema_version") != 1:
        raise ValueError("Unsupported input profile schema")
    columns = profile.get("columns", {})
    if not isinstance(columns, dict) or any(not isinstance(v, str) for v in columns.values()):
        raise ValueError("Profile columns must map semantic roles to source column names")
    for role in REQUIRED:
        if not columns.get(role):
            raise ValueError(f"Configure the input column for {role}")
    if not columns.get("cluster") and not columns.get("first_stage_unit"):
        raise ValueError("Configure cluster or first_stage_unit")
    if not columns.get("area") and not columns.get("location"):
        raise ValueError("Configure area or location")
    _, metadata = pyreadstat.read_sav(data_file, metadataonly=True, user_missing=True)
    requested = sorted({value for value in columns.values() if value})
    if set(requested) - set(metadata.column_names):
        raise ValueError("Some configured input columns are absent; inspect this file and update the profile")
    raw, metadata = pyreadstat.read_sav(data_file, usecols=requested, user_missing=True,
                                      apply_value_formats=False, disable_datetime_conversion=True)
    if raw.empty:
        raise ValueError("The input contains no observations")
    data = pd.DataFrame(index=raw.index)
    for role in (*ACTIVITIES, "personal_files", "age_group", "education_group", "sex_group"):
        source = columns[role]
        data[role] = _recode(raw[source], source, role, profile, metadata)
    for role in ("primary_weight", "alternative_weight"):
        source = columns[role]
        values = pd.to_numeric(raw[source], errors="coerce")
        if _missing(raw[source], source, role, profile, metadata).any() or not np.isfinite(values).all() or (values <= 0).any():
            raise ValueError(f"{role} must be observed, finite and positive for every observation")
        data[role] = values.astype(float)
    for role in ("age_group", "education_group", "sex_group"):
        if data[role].isna().any():
            raise ValueError(f"Missing {role}; define the intended population before analysis")
        data[role] = data[role].astype(int)
    source = columns["stratum"]
    if _missing(raw[source], source, "stratum", profile, metadata).any():
        raise ValueError("Sampling strata must be observed")
    data["stratum"] = raw[source].map(key)
    if columns.get("cluster"):
        source = columns["cluster"]
        if _missing(raw[source], source, "cluster", profile, metadata).any():
            raise ValueError("Variance clusters must be observed")
        data["cluster"] = raw[source].map(key)
    else:
        source = columns["first_stage_unit"]
        second = {key(v) for v in profile.get("design", {}).get("second_stage_strata", [])}
        use_second = data.stratum.isin(second)
        if second - set(data.stratum):
            raise ValueError("Configured second-stage strata are absent from this input")
        if use_second.any() and not columns.get("second_stage_unit"):
            raise ValueError("Configure second_stage_unit for the specified sampling strata")
        codes = raw[source].copy()
        missing = _missing(raw[source], source, "first_stage_unit", profile, metadata)
        if use_second.any():
            ss = columns["second_stage_unit"]
            codes.loc[use_second] = raw.loc[use_second, ss]
            missing.loc[use_second] = _missing(raw[ss], ss, "second_stage_unit", profile, metadata).loc[use_second]
        if missing.any():
            raise ValueError("The configured first-stage variance clusters contain missing values")
        marker = pd.Series(np.where(use_second, ":village:", ":psu:"), index=raw.index)
        data["cluster"] = data.stratum + marker + codes.map(key)
    if columns.get("area"):
        source = columns["area"]
        data["area"] = _recode(raw[source], source, "area", profile, metadata)
    else:
        source = columns["location"]
        labels = metadata.variable_value_labels.get(source, {})
        if profile.get("geography", {}).get("use_value_labels", True):
            places = raw[source].map(labels)
        else:
            places = raw[source]
        if places.isna().any():
            raise ValueError("Location labels are incomplete; configure a compatible official geography source")
        crosswalk = pd.read_csv(ROOT / "reference_data" / "area_classification.csv", encoding="utf-8-sig")
        if crosswalk.place.map(_place).duplicated().any():
            raise ValueError("Duplicate locations in the official area classification")
        lookup = dict(zip(crosswalk.place.map(_place), np.where(crosswalk.cluster.eq(1), 1, 2)))
        data["area"] = places.map(_place).map(lookup)
    if data.area.isna().any():
        raise ValueError("Some locations cannot be classified; inspect the official location labels")
    data["area"] = data.area.astype(int)
    photo, video = data.photography, data.video_recording
    no_phone = photo.eq(8)
    holder = photo.between(1, 7) | video.between(1, 7)
    if (no_phone & holder).any() or (~no_phone & ~holder).any():
        raise ValueError("Phone ownership is inconsistent or unclassified from the two device questions")
    data["phone_holder"] = holder.astype(float)
    design = data[["stratum", "cluster"]].drop_duplicates()
    if design.groupby("stratum").size().lt(2).any():
        raise ValueError("Each stratum requires at least two variance clusters for the specified JKn design")
    receipt = {"observations": len(data), "strata": int(design.stratum.nunique()),
               "variance_clusters": len(design), "profile_schema": 1,
               "artificial_data": profile.get("artificial_data") is True,
               "input_sha256": hashlib.sha256(data_file.read_bytes()).hexdigest(),
               "profile_sha256": hashlib.sha256(profile_file.read_bytes()).hexdigest()}
    return data, receipt


def run_survey(data_file: Path, profile_file: Path, output_dir: Path, *, calibration_file: Path | None = None) -> dict:
    from helpers.survey_analysis import run_analysis

    output_dir = Path(output_dir).expanduser().resolve()
    if output_dir.exists():
        raise FileExistsError("Choose a new analysis directory")
    if output_dir == ROOT or output_dir.is_relative_to(ROOT):
        raise ValueError("Keep analysis outputs outside the source repository")
    data, receipt = load_survey(data_file, profile_file)
    targets = None
    if calibration_file:
        targets = json.loads(Path(calibration_file).expanduser().read_text(encoding="utf-8"))
    result = run_analysis(data, output_dir, calibration_targets=targets, sensitivity=True)
    result["artificial_data"] = receipt["artificial_data"]
    dump(output_dir / "analysis_report.json", result)
    # Input hashes are local provenance, not part of downloadable public results.
    dump(output_dir / "input_receipt.json", receipt)
    return result
