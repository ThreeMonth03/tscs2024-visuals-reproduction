"""Export only reviewed figures and aggregate tables from a completed notebook run."""
from __future__ import annotations

import csv
import hashlib
from html import escape
import io
import json
from pathlib import Path
import shutil
import tempfile
import zipfile

FIGURES = {
    "age_frequency": "Frequency of taking photos, recording videos and sharing by age group",
    "education_frequency": "Frequency of taking photos, recording videos and sharing by education group",
    "sharing_experience": "Combinations of sharing audiences",
    "region_frequency": "Taking photos and sharing with family and friends within areas",
    "region_other_frequency": "Recording videos and sharing with an unspecified audience within areas",
    "file_answers": "Responses about personal digital files",
    "nonproduction": "Proportion reporting no production of digital files",
    "nonproduction_regions": "Proportion reporting no production of digital files within areas",
    "file_locations": "Primary storage locations for personal digital files",
}
TABLES = (
    "primary/descriptive_profiles.csv",
    "primary/adjusted_profiles.csv",
    "primary/formal_tests.csv",
    "primary/scenario_tests.csv",
    "alternative/descriptive_profiles.csv",
    "alternative/adjusted_profiles.csv",
    "alternative/formal_tests.csv",
    "contrasts/location_profiles.csv",
    "contrasts/all_scenarios.csv",
    "contrasts/contrast_summary.csv",
)
SCENARIO_DEFINITIONS = {
    "tables/primary/scenario_tests.csv": (
        "scenario=alternative means additional calibration of the main weights to population margins."
    ),
    "tables/alternative/*.csv": (
        "These three tables use the official alternative survey weights."
    ),
    "tables/contrasts/all_scenarios.csv": (
        "scenario=alternative means the official alternative survey weights."
    ),
    "tables/contrasts/location_profiles.csv": (
        "scenario=alternative means the official alternative survey weights."
    ),
    "tables/contrasts/contrast_summary.csv": (
        "alternative_* columns describe results using the official alternative survey weights."
    ),
}
PRIVATE_COLUMNS = {
    "respondent_id", "respondent", "case_id", "idno", "telephone",
    "phone_number", "email", "address",
}


def _plain_path(path: Path) -> Path:
    """Reject path traversal and symlink components, including the supplied root."""
    path = Path(path).expanduser()
    if ".." in path.parts:
        raise ValueError("Export paths must not contain '..'")
    path = path.absolute()
    if any(part.is_symlink() for part in (path, *path.parents)):
        raise ValueError("Export paths must not contain symlinks")
    return path


def _read(root: Path, relative: str) -> bytes:
    path = _plain_path(root / relative)
    if not path.is_relative_to(root) or not path.is_file():
        raise FileNotFoundError("Missing export input: " + relative)
    return path.read_bytes()


def _csv_shape(content: bytes) -> tuple[list[str], int]:
    reader = csv.reader(io.StringIO(content.decode("utf-8-sig")))
    header = next(reader, [])
    if not header or len(set(header)) != len(header):
        raise ValueError("Aggregate CSV requires a unique, nonempty header")
    if PRIVATE_COLUMNS.intersection(column.strip().casefold() for column in header):
        raise ValueError("Individual-data columns cannot be exported")
    count = 0
    for row in reader:
        if len(row) != len(header):
            raise ValueError("Malformed aggregate CSV row")
        count += 1
    return header, count


def _preview(reestimated: bool = False, calibration_available: bool | None = None,
             artificial_data: bool = False) -> str:
    origin = ("Results recalculated from the user-selected survey file."
              if reestimated else
              "Published aggregate results; survey statistics were not reestimated.")
    if artificial_data:
        origin = "Artificial demonstration data; these are not empirical study results. " + origin
    if reestimated and calibration_available is False:
        origin += " The additional population recalibration check was not run because targets were not supplied."
    figures = "\n".join(
        f'<section><h2>{escape(title)}</h2><a href="figures/{name}.pdf">Download PDF</a>'
        f'<img src="figures/{name}.png" alt="{escape(title)}" loading="lazy"></section>'
        for name, title in FIGURES.items()
    )
    return ("<!doctype html><html lang=\"en\"><meta charset=\"utf-8\">"
            "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
            "<title>Research figures and aggregate results</title><style>body{font-family:system-ui,sans-serif;"
            "max-width:1100px;margin:32px auto;padding:0 20px;color:#203438}"
            "h1{font-size:1.7rem}h2{font-size:1.25rem}section{margin:40px 0}"
            "img{display:block;width:100%;height:auto;margin-top:12px}a{color:#087d88}"
            "</style><h1>Research figures and aggregate results</h1><p>" + origin + "</p>"
            "<p>Nine figures and ten aggregate result tables. See summary.json for the complete file list.</p>" + figures + "</html>")


def export_results(root: Path, output_dir: Path, destination_root: Path) -> dict:
    """Create a new downloadable preview and ZIP, without logs or individual data.

    Files are selected explicitly rather than by walking a run directory. All
    inputs are validated before creating an export folder. Repeated calls produce
    separate export folders and preserve earlier results.
    """
    root, output, destination = (_plain_path(p) for p in (root, output_dir, destination_root))
    if output == root or output.is_relative_to(root):
        raise ValueError("Analysis output must remain outside the repository")
    if destination == output or destination.is_relative_to(output):
        raise ValueError("Download copies must be separate from analysis output")
    report = json.loads(_read(output, "notebook_report.json"))
    expected_pngs = [f"figures/{name}.png" for name in FIGURES]
    mode = report.get("mode")
    reestimated = mode == "survey"
    expected_source = "uploaded_survey" if reestimated else "published_aggregates"
    if (mode not in {"aggregate", "survey"} or report.get("status") != "pass"
            or report.get("statistical_reestimation") is not reestimated
            or report.get("input_estimates") != expected_source
            or report.get("figure_count") != len(FIGURES)
            or report.get("figure_files") != expected_pngs):
        raise ValueError("Only a completed, consistent aggregate or survey run can be exported")
    figures = json.loads(_read(output, "figures/figures_manifest.json"))
    if (figures.get("status") != "pass" or figures.get("figure_count") != len(FIGURES)
            or tuple(figures.get("figures", {})) != tuple(FIGURES)
            or figures.get("selected_rows") != 258):
        raise ValueError("Unexpected figure inventory")

    contents = {}
    for name in FIGURES:
        for suffix, signature in (("png", b"\x89PNG\r\n\x1a\n"), ("pdf", b"%PDF-")):
            relative = f"figures/{name}.{suffix}"
            data = _read(output, relative)
            sha = figures["figures"][name]["files"].get(f"{name}.{suffix}")
            if not data.startswith(signature) or hashlib.sha256(data).hexdigest() != sha:
                raise ValueError("Invalid or changed figure: " + relative)
            contents[relative] = data

    aggregate_root = output / "analysis/aggregates" if reestimated else root / "aggregates"
    bundle = json.loads(_read(root, "manifest.json"))
    fresh_inventory = json.loads(_read(output, "aggregate_manifest.json")) if reestimated else None
    if fresh_inventory is not None and (fresh_inventory.get("status") != "pass"
                                       or set(fresh_inventory.get("tables", {})) != set(TABLES)):
        raise ValueError("Reestimated aggregate inventory is incomplete")
    for relative in TABLES:
        data = _read(aggregate_root, relative)
        header, count = _csv_shape(data)
        if reestimated:
            expected_header, _ = _csv_shape(_read(root / "aggregates", relative))
            if set(header) != set(expected_header):
                raise ValueError("Reestimated aggregate table has an unexpected schema: " + relative)
            declared = fresh_inventory["tables"][relative]
            if count != declared.get("rows"):
                raise ValueError("Reestimated aggregate row count changed: " + relative)
        else:
            declared = bundle["files"].get("aggregates/" + relative, {})
        if hashlib.sha256(data).hexdigest() != declared.get("sha256"):
            origin = "this run's aggregate inventory" if reestimated else "the published inventory"
            raise ValueError("Aggregate differs from " + origin + ": " + relative)
        contents["tables/" + relative] = data

    selected = _read(output, "figures/selected_profiles.csv")
    if (_csv_shape(selected) != (_csv_shape(_read(aggregate_root, TABLES[0]))[0], 258)
            or hashlib.sha256(selected).hexdigest() != figures.get("selected_profiles_sha256")):
        raise ValueError("Invalid selected aggregate profiles")
    contents["figures/selected_profiles.csv"] = selected
    contents["index.html"] = _preview(reestimated, report.get("calibration_available"), report.get("artificial_data", False)).encode("utf-8")
    origin = ("Source: results recalculated from the user-selected survey file.\n"
              if reestimated else
              "Source: published aggregate results; survey statistics were not reestimated.\n")
    if report.get("artificial_data") is True:
        origin = "ARTIFICIAL DEMONSTRATION DATA: not empirical study results.\n" + origin
    if reestimated and report.get("calibration_available") is False:
        origin += "Additional population recalibration: not run; targets were not supplied.\n"
    contents["README.txt"] = (
        "Generational Differences in Sharing Visuals by Phone and Preserving Digital Files\n\n"
        "The term \"visuals\" refers to photos and videos.\n\n"
        + origin +
        "Open index.html to view the nine research figures. The figures/ folder contains PNGs, PDFs, and the plotting aggregates.\n"
        "tables/ contains ten aggregate result tables, grouped as primary, alternative and contrasts.\n"
        "This package excludes respondent records and execution logs.\n"
        "\nReading the alternative labels:\n"
        + "\n".join(f"- {path}: {meaning}" for path, meaning in SCENARIO_DEFINITIONS.items())
        + "\n"
    ).encode("utf-8")
    summary = {"mode": mode, "input_estimates": expected_source,
               "statistical_reestimation": reestimated, "figure_count": len(FIGURES),
               "aggregate_table_count": len(TABLES), "selected_profile_rows": 258,
               "scenario_definitions": SCENARIO_DEFINITIONS,
               "files": {name: {"sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)}
                         for name, data in contents.items()}}
    if reestimated:
        summary["calibration_available"] = report.get("calibration_available")
        summary["artificial_data"] = report.get("artificial_data", False)
    contents["summary.json"] = (json.dumps(summary, ensure_ascii=False, indent=2) + "\n").encode("utf-8")

    destination.mkdir(parents=True, exist_ok=True)
    directory = Path(tempfile.mkdtemp(prefix="tscs-results-", dir=destination))
    try:
        for relative, data in contents.items():
            target = directory / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        archive = directory / "tscs-results.zip"
        with zipfile.ZipFile(archive, "x", compression=zipfile.ZIP_DEFLATED) as zipped:
            for relative, data in contents.items():
                zipped.writestr(relative, data)
    except Exception:
        shutil.rmtree(directory)
        raise
    return {"directory": directory, "zip_path": archive, "index_path": directory / "index.html",
            "files": list(contents), "mode": mode, "artificial_data": report.get("artificial_data", False)}
