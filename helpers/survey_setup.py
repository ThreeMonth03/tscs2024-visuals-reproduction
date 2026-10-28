"""Configure a user-owned SAV from its metadata, without source-name guesses.

Generated profiles and metadata catalogues stay beside the private input. Only
complete, unambiguous mappings pass to the existing survey-input validator.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import json
from pathlib import Path
import re
import tempfile
import unicodedata

import pyreadstat

from helpers import survey_input


@dataclass(frozen=True)
class SetupResult:
    data_file: Path
    profile_file: Path
    summary: str


class InputSetupError(ValueError):
    """An input requires clarification before any analysis can run."""

    def __init__(self, message: str, *, unresolved=(), draft_path=None, metadata_path=None):
        self.unresolved = tuple(unresolved)
        self.draft_path = draft_path
        self.metadata_path = metadata_path
        if draft_path:
            message += f"\nPrivate draft profile: {draft_path}"
        if metadata_path:
            message += f"\nPrivate metadata catalogue: {metadata_path}"
        super().__init__(message)


def _text(value: object) -> str:
    return unicodedata.normalize("NFKC", str(value or "")).strip().lower()


def _has(text: str, pattern: str) -> bool:
    return re.search(pattern, text) is not None


def _role_matches(label: str, role: str) -> bool:
    """Match meanings in labels, never the source column identifier."""
    label = _text(label)
    # Explicit semantic labels also support renamed-column demonstration files.
    if label == role or label == role.replace("_", " "):
        return True
    if label == f"artificial demonstration: {role}":
        return True
    if role in ("age_group", "education_group", "sex_group") and _has(label, r"spouse|partner|father|mother|配偶|父親|母親|訪員"):
        return False
    share = _has(label, r"shar|傳送|分享|傳給")
    photo = _has(label, r"photo|拍照|照片")
    video = _has(label, r"video|錄影|影片|錄像")
    patterns = {
        "personal_files": r"personal.*(?:file|storage)|個人.*(?:檔案|儲存|存放)",
        "age_group": r"age.*(?:group|band)|年齡.*(?:組|分組|區間)",
        "education_group": r"education|教育|學歷",
        "sex_group": r"\bsex\b|\bgender\b|性別",
        "stratum": r"sampling strat|sample strat|抽樣.*(?:分層|層別|階層)|抽樣層",
        # A generic township/PSU label does not establish a variance cluster.
        "cluster": r"variance cluster|variance.*sampling unit|變異數.*(?:群集|抽樣單位)",
        "first_stage_unit": r"first.stage.*(?:unit|cluster)|第一階段.*(?:單位|鄉鎮)",
        "second_stage_unit": r"second.stage.*(?:unit|cluster)|第二階段.*(?:單位|村里)",
        "location": r"township|municipality|鄉鎮|居住地區|居住地點",
        "area": r"digital.*(?:maturity|development).*group|數位.*(?:成熟|發展).*分組",
        "primary_weight": r"(?:final|calibrat).*weight.*(?:inverse|selection.probability)|(?:inverse|selection.probability).*final.*weight|最終.*權[數重].*抽選機率|抽選機率.*最終.*權[數重]",
        "alternative_weight": r"(?:final|calibrat).*weight.*(?:unit.start|equal.start)|(?:unit.start|equal.start).*final.*weight|最終.*權[數重].*起始.*1|起始.*1.*最終.*權[數重]",
    }
    if role == "photography":
        return photo and not share and not _has(label, r"edit|編輯|修圖")
    if role == "video_recording":
        return video and not share and not photo and not _has(label, r"edit|編輯|觀看")
    if role == "sharing_with_contacts":
        return share and _has(label, r"friend|famil|contact|親友|親人|朋友|家人") and not _has(label, r"不特定|unspecified")
    if role == "sharing_with_unspecified_audiences":
        return share and _has(label, r"unspecified|public audience|不特定")
    return _has(label, patterns.get(role, r"(?!)"))


def _category(label: str, role: str, artificial: bool) -> int | None:
    text = _text(label)
    if artificial:
        match = re.fullmatch(rf"artificial {re.escape(role)} category (\d+)", text)
        if match:
            code = int(match.group(1))
            return code if code in survey_input.CATEGORIES[role] else None
    if role in survey_input.ACTIVITIES:
        if role == "photography" and _has(text, r"no (?:mobile |cell )?phone|沒有手機|無手機"):
            return 8
        if _has(text, r"cannot|unable|不能|無法|沒有.*功能"):
            if role == "photography" and _has(text, r"photo|拍照|照相"):
                return 7
            if role == "video_recording" and _has(text, r"video|錄影|影片"):
                return 7
            return None
        if _has(text, r"never|從未|不曾"):
            return 6
        if _has(text, r"several|multiple|數次|多次|幾次"):
            if _has(text, r"day|daily|天|日"):
                return 1
            if _has(text, r"week|週|周|星期"):
                return 3
            if _has(text, r"month|月"):
                return 4
        if _has(text, r"less often|less than.*month|少於.*月|很少|偶爾|更少|數月一次|不常"):
            return 5
        if _has(text, r"daily|every day|once a day|每天|每日|一天一次|一日一次"):
            return 2
    elif role == "personal_files":
        if _has(text, r"not.*(?:produc|creat)|不產製|不製作|不產生"):
            return 6
        if _has(text, r"not.*consider|未考慮|不考慮|沒有考慮|沒想過"):
            return 7
        if _has(text, r"original device|原.*(?:設備|裝置)"):
            return 1
        if _has(text, r"cloud|雲端"):
            return 4
        if _has(text, r"other.*(?:media|storage)|print|其他.*媒體|光碟|隨身碟|列印|沖印"):
            return 3
        if _has(text, r"personal computer|hard dis[kc]|電腦|硬碟"):
            return 2
        if re.fullmatch(r"(?:other|others|其他)[.。]?", text):
            return 5
    elif role == "age_group":
        bounds = [(18, 29), (30, 39), (40, 49), (50, 59), (60, 69)]
        numbers = re.findall(r"\d+", text)
        for code, (low, high) in enumerate(bounds, 1):
            if numbers == [str(low), str(high)] and _has(text, r"[-–—~～至到]|\bto\b"):
                return code
        if numbers == ["70"] and _has(text, r"\+|以上|older|over|above"):
            return 6
    elif role == "education_group":
        # Ranges spanning analysis groups require an explicit user mapping.
        below = _has(text, r"以下|below|lower|less")
        above = _has(text, r"以上|above|higher|more")
        elementary = _has(text, r"elementary|primary school|小學|國小")
        college = _has(text, r"college|university|專科|大學")
        if (below and not elementary) or (above and not college):
            return None
        if _has(text, r"junior high|middle school|國中|初中|初職"):
            return 2
        if _has(text, r"senior high|high school|vocational|高中|高職"):
            return 3
        if _has(text, r"college|university|graduate|doctoral|專科|大學|碩士|博士"):
            return 4
        if _has(text, r"elementary|primary school|no formal|illiterate|小學|國小|不識字|未受.*教育|自修"):
            return 1
    elif role == "sex_group":
        if re.fullmatch(r"male|man|男|男性", text):
            return 1
        if re.fullmatch(r"female|woman|女|女性", text):
            return 2
    elif role == "area":
        if _has(text, r"non.?mature|非.*成熟"):
            return 2
        if _has(text, r"mature|成熟"):
            return 1
    return None


def _declared_missing(value: object, source: str, metadata) -> bool:
    for span in metadata.missing_ranges.get(source, []):
        try:
            if span["lo"] <= value <= span["hi"]:
                return True
        except TypeError:
            continue
    return False


def _value_map(source: str, role: str, metadata, artificial: bool) -> dict | None:
    values = metadata.variable_value_labels.get(source, {})
    mapping = {}
    for value, label in values.items():
        if _declared_missing(value, source, metadata) or _missing_label(label):
            continue
        code = _category(label, role, artificial)
        if code is None:
            return None
        mapping[survey_input.key(value)] = code
    required = set(range(1, 7)) if role in survey_input.ACTIVITIES else set(survey_input.CATEGORIES[role])
    return mapping if required.issubset(set(mapping.values())) else None


def _missing_label(label: str) -> bool:
    return re.fullmatch(r"refus(?:ed|al)|don['’]?t know|unknown|not asked|skipped|拒答|不知道|跳答|未訪問", _text(label)) is not None


def _set_category_mapping(profile: dict, source: str, role: str, metadata, artificial: bool) -> None:
    profile.setdefault("value_maps", {})
    profile.setdefault("missing_values", {}).pop(role, None)
    mapping = _value_map(source, role, metadata, artificial)
    if mapping is None:
        profile["value_maps"].pop(role, None)
    else:
        profile["value_maps"][role] = mapping
    missing = [value for value, label in metadata.variable_value_labels.get(source, {}).items()
               if _missing_label(label)]
    if missing:
        profile["missing_values"][role] = missing


def _merge(base: dict, updates: dict) -> dict:
    result = deepcopy(base)
    for name, value in updates.items():
        if isinstance(value, dict) and isinstance(result.get(name), dict):
            result[name] = _merge(result[name], value)
        else:
            result[name] = deepcopy(value)
    return result


def _resolve_path(root: Path, value: str | Path) -> Path:
    path = Path(value).expanduser()
    return (root / path).resolve() if not path.is_absolute() else path.resolve()


def _choose_data(root: Path, data_file: str | Path | None) -> Path:
    if data_file:
        path = _resolve_path(root, data_file)
        if not path.is_file():
            raise FileNotFoundError("DATA_FILE must point to an existing .sav file.")
        if path.suffix.lower() != ".sav":
            raise InputSetupError("DATA_FILE must point to an existing .sav file.")
        return path
    folder = root / "data" / "official"
    paths = sorted(path for path in folder.glob("*") if path.is_file() and path.suffix.lower() == ".sav")
    if len(paths) != 1:
        message = ("Upload one .sav file into data/official, then rerun this cell." if not paths else
                   "More than one SAV is in data/official. Set DATA_FILE to the file you want to analyse.")
        raise InputSetupError(message, unresolved=("data_file",))
    return paths[0].resolve()


def _write_local(data_file: Path, profile: dict, metadata, root: Path) -> tuple[Path, Path]:
    folder = data_file.parent
    if folder.is_relative_to(root) and not folder.is_relative_to(root / "data" / "official"):
        raise InputSetupError("Put the SAV in data/official or outside the repository before generating a local profile.")
    with tempfile.NamedTemporaryFile(prefix="input-profile-", suffix=".json", dir=folder, delete=False) as file:
        profile_path = Path(file.name)
    metadata_path = profile_path.with_name(profile_path.stem + "-metadata.json")
    catalogue = {"purpose": "Private configuration only; do not publish or include in result downloads.",
                 "variables": [{"column": name, "label": metadata.column_names_to_labels.get(name),
                                "values": {survey_input.key(k): v for k, v in metadata.variable_value_labels.get(name, {}).items()},
                                "missing_ranges": metadata.missing_ranges.get(name, [])}
                               for name in metadata.column_names]}
    survey_input.dump(profile_path, profile)
    survey_input.dump(metadata_path, catalogue)
    return profile_path, metadata_path


def _infer(metadata) -> tuple[dict, list[str]]:
    artificial = "artificial workflow demonstration" in _text(metadata.file_label)
    profile = {"schema_version": 1, "columns": {}, "value_maps": {}, "missing_values": {},
               "design": {}, "geography": {"use_value_labels": True}, "artificial_data": artificial}
    issues = []
    roles = (*survey_input.REQUIRED, "cluster", "first_stage_unit", "second_stage_unit", "area", "location")
    for role in roles:
        matches = [name for name in metadata.column_names
                   if _role_matches(metadata.column_names_to_labels.get(name), role)]
        if len(matches) > 1 and role in survey_input.CATEGORIES:
            complete = [name for name in matches if _value_map(name, role, metadata, artificial) is not None]
            if complete:
                matches = complete
        if len(matches) != 1:
            if len(matches) > 1:
                issues.append(f"{role}: multiple metadata labels match")
            continue
        source = matches[0]
        profile["columns"][role] = source
        if role in survey_input.CATEGORIES:
            _set_category_mapping(profile, source, role, metadata, artificial)
    return profile, issues


def _check_profile(profile: dict, inferred_issues: list[str]) -> list[str]:
    columns = profile.get("columns", {})
    if not isinstance(columns, dict):
        return ["columns: expected a semantic mapping"]
    issues = [issue for issue in inferred_issues if not columns.get(issue.split(":")[0])]
    for role in survey_input.REQUIRED:
        if not columns.get(role) and not any(issue.startswith(role + ":") for issue in issues):
            issues.append(f"{role}: identify the input column")
    if not columns.get("cluster"):
        if not columns.get("first_stage_unit"):
            issues.append("cluster: identify the documented variance clusters or first-stage units")
        elif "second_stage_strata" not in profile.get("design", {}):
            issues.append("design.second_stage_strata: confirm the design, including an explicit empty list if no strata use second-stage units")
    if not columns.get("area") and not columns.get("location"):
        issues.append("area/location: identify the documented area group or full township labels")
    for role in survey_input.CATEGORIES:
        if columns.get(role) and not profile.get("value_maps", {}).get(role):
            issues.append(f"{role}: provide a complete value map; the response labels could not be mapped safely")
    return issues


def prepare_upload(root: Path, data_file: str | Path | None = None,
                   profile_file: str | Path | None = None, overrides: dict | None = None) -> SetupResult:
    """Return validated paths, or stop with a private draft explaining what is missing.

    Explicit profiles take precedence. Without one, a neighbouring profile.json
    or <SAV stem>.profile.json is used; otherwise metadata labels are inspected.
    ``overrides`` uses the same columns/value_maps/design structure as a profile.
    No case records are written or displayed by this function.
    """
    root = Path(root).expanduser().resolve()
    data = _choose_data(root, data_file)
    _, metadata = pyreadstat.read_sav(data, metadataonly=True, user_missing=True)
    if overrides is not None and not isinstance(overrides, dict):
        raise InputSetupError("INPUT_OVERRIDES must be a profile-style dictionary.")
    chosen = _resolve_path(root, profile_file) if profile_file else None
    if chosen is None:
        neighbours = list(dict.fromkeys(path for path in (
            data.with_name("profile.json"), data.with_suffix(".profile.json")) if path.is_file()))
        if len(neighbours) > 1:
            raise InputSetupError("Two neighbouring profiles exist. Set PROFILE_FILE to the one you intend to use.", unresolved=("profile_file",))
        chosen = neighbours[0] if neighbours else None
    if chosen:
        if not chosen.is_file():
            raise InputSetupError("PROFILE_FILE does not exist.", unresolved=("profile_file",))
        try:
            profile = json.loads(chosen.read_text(encoding="utf-8"))
        except (ValueError, OSError) as error:
            raise InputSetupError("PROFILE_FILE must contain readable JSON.", unresolved=("profile_file",)) from error
        if not isinstance(profile, dict):
            raise InputSetupError("PROFILE_FILE must contain a JSON object.", unresolved=("profile_file",))
        inferred_issues = []
    else:
        profile, inferred_issues = _infer(metadata)
    old_columns = profile.get("columns", {}).copy()
    profile = _merge(profile, overrides or {})
    # A changed source column must not inherit another column's recoding.
    for role, source in profile.get("columns", {}).items():
        if (role in survey_input.CATEGORIES and source != old_columns.get(role)
                and role not in (overrides or {}).get("value_maps", {})):
            _set_category_mapping(profile, source, role, metadata, profile.get("artificial_data", False))
            if role in (overrides or {}).get("missing_values", {}):
                profile["missing_values"][role] = deepcopy(overrides["missing_values"][role])
    # The artificial marker cannot be lost through profile overrides.
    if "artificial workflow demonstration" in _text(metadata.file_label):
        profile["artificial_data"] = True
    issues = _check_profile(profile, inferred_issues)
    need_new = chosen is None or bool(overrides) or profile.get("artificial_data") is True
    draft, catalogue = _write_local(data, profile, metadata, root) if need_new or issues else (chosen, None)
    if not issues:
        try:
            _, receipt = survey_input.load_survey(data, draft)
        except (ValueError, TypeError, KeyError) as error:
            issues.append(str(error))
    if issues:
        if catalogue is None:
            draft, catalogue = _write_local(data, profile, metadata, root)
        raise InputSetupError(
            "Input setup needs confirmation before analysis:\n- " + "\n- ".join(issues) +
            "\nReview the private metadata and draft profile beside the SAV; set PROFILE_FILE or INPUT_OVERRIDES, then rerun.",
            unresolved=issues, draft_path=draft, metadata_path=catalogue)
    kind = "Artificial demonstration" if receipt["artificial_data"] else "User-supplied survey"
    summary = (f"{kind} input validated: {receipt['observations']:,} observations, "
               f"{receipt['strata']} sampling strata, {receipt['variance_clusters']} variance clusters. "
               "The local profile is ready; no input records were exported.")
    return SetupResult(data, draft, summary)
