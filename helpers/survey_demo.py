"""Create an artificial SPSS input for exercising the manual-upload workflow.

The fixed seed makes the generated observations reproducible. No observations,
population margins, or statistics are copied from the study's survey data.
"""
from __future__ import annotations

from itertools import product
from pathlib import Path

import numpy as np
import pandas as pd
import pyreadstat

from helpers.survey_input import ACTIVITIES, CATEGORIES, ROOT, dump


SEED = 20261029
SOURCE_COLUMNS = {
    "photography": "demo_photo",
    "video_recording": "demo_video",
    "sharing_with_contacts": "demo_contacts",
    "sharing_with_unspecified_audiences": "demo_audiences",
    "personal_files": "demo_files",
    "age_group": "demo_age",
    "education_group": "demo_education",
    "sex_group": "demo_sex",
    "stratum": "demo_stratum",
    "cluster": "demo_cluster",
    "area": "demo_area",
    "primary_weight": "demo_weight",
    "alternative_weight": "demo_alt_weight",
}


def _observations() -> pd.DataFrame:
    rng = np.random.default_rng(SEED)
    combinations = list(product(range(1, 5), range(1, 10), range(1, 7),
                                range(1, 5), [1, 2]))
    data = pd.DataFrame(combinations, columns=["stratum", "unit", "age", "education", "sex"])
    count = len(data)
    raw = pd.DataFrame({
        "demo_age": data.age,
        "demo_education": data.education,
        "demo_sex": data.sex,
        "demo_stratum": data.stratum,
        "demo_cluster": [f"S{s}-C{c}" for s, c in zip(data.stratum, data.unit)],
        "demo_area": 1 + (data.stratum + data.unit) % 2,
    })
    age_effect = (data.age.to_numpy() - 3.5) * 0.035
    education_effect = (data.education.to_numpy() - 2.5) * 0.025
    for number, activity in enumerate(ACTIVITIES):
        weekly = np.clip(0.52 - number * 0.055 - age_effect + education_effect, 0.2, 0.8)
        frequent = rng.random(count) < weekly
        raw[SOURCE_COLUMNS[activity]] = np.where(frequent, rng.integers(1, 4, count),
                                                rng.integers(4, 7, count)).astype(float)
    # Every response category remains possible throughout the artificial sample.
    raw["demo_files"] = rng.integers(1, 8, count).astype(float)
    no_phone = rng.random(count) < 0.065
    raw.loc[no_phone, "demo_photo"] = 8
    raw.loc[no_phone, ["demo_video", "demo_contacts", "demo_audiences"]] = np.nan
    cannot_photo = (rng.random(count) < 0.025) & ~no_phone
    cannot_video = (rng.random(count) < 0.035) & ~no_phone
    raw.loc[cannot_photo, "demo_photo"] = 7
    raw.loc[cannot_video, "demo_video"] = 7
    primary = rng.uniform(0.7, 1.3, count) * (1 + 0.035 * data.age.to_numpy())
    alternative = primary * np.exp(0.015 * (data.sex.to_numpy() - 1.5)
                                  - 0.01 * (data.age.to_numpy() - 3.5))
    raw["demo_weight"] = primary / primary.mean()
    raw["demo_alt_weight"] = alternative / alternative.mean()
    return raw


def make_demo(output_dir: Path | str) -> dict[str, Path]:
    """Write a new artificial SAV, semantic profile, and demonstration margins."""
    output_dir = Path(output_dir).expanduser().resolve()
    if output_dir == ROOT or output_dir.is_relative_to(ROOT):
        raise ValueError("Create demonstration inputs outside the source repository")
    if output_dir.exists():
        raise FileExistsError("Choose a new directory for the demonstration inputs")
    raw = _observations()
    profile = {
        "schema_version": 1,
        "artificial_data": True,
        "columns": SOURCE_COLUMNS.copy(),
        "value_maps": {role: {str(code): code for code in codes}
                       for role, codes in CATEGORIES.items()},
        "missing_values": {},
        "design": {"second_stage_strata": []},
        "geography": {"use_value_labels": False},
        "notes": "Artificial demonstration only. These are not TSCS observations or study results.",
    }
    value_labels = {
        SOURCE_COLUMNS[role]: {code: f"Artificial {role} category {code}" for code in codes}
        for role, codes in CATEGORIES.items()
    }
    targets = {}
    weights = raw.demo_alt_weight
    for factor, source in [("sex", "demo_sex"), ("age", "demo_age"),
                           ("education", "demo_education"), ("stratum", "demo_stratum")]:
        targets[factor] = {str(int(level)): float(weights[raw[source].eq(level)].sum() / weights.sum())
                           for level in sorted(raw[source].unique())}
    output_dir.mkdir(parents=True)
    paths = {"data_file": output_dir / "survey.sav", "profile_file": output_dir / "profile.json",
             "calibration_file": output_dir / "calibration.json"}
    pyreadstat.write_sav(raw, paths["data_file"],
                        file_label="Artificial workflow demonstration; not survey observations",
                        column_labels={column: f"Artificial demonstration: {role}"
                                       for role, column in SOURCE_COLUMNS.items()},
                        variable_value_labels=value_labels)
    dump(paths["profile_file"], profile)
    dump(paths["calibration_file"], targets)
    return paths
