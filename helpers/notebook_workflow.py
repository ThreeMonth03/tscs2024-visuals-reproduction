"""Run an aggregate preview or reestimate from a user-selected survey file."""
from __future__ import annotations

from dataclasses import dataclass, field, replace
import csv
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile


DEFAULT_FONT = "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"


@dataclass(frozen=True)
class Configuration:
    output_dir: Path
    font: str
    mode: str = "aggregate"
    data_file: Path | None = None
    profile_file: Path | None = None
    calibration_file: Path | None = None
    input_overrides: dict = field(default_factory=dict)


def find_root(start: Path | None = None) -> Path:
    current = (start or Path.cwd()).resolve()
    for candidate in (current, *current.parents):
        if (candidate / "run.py").is_file() and (candidate / "manifest.json").is_file():
            return candidate
    raise FileNotFoundError("Open this notebook from the reproduction repository")


def configuration(environ: dict[str, str] | None = None) -> Configuration:
    env = os.environ if environ is None else environ
    mode = env.get("REPRO_MODE") or "aggregate"
    if mode not in {"aggregate", "survey"}:
        raise ValueError("MODE must be 'aggregate' or 'survey'")
    output = env.get("REPRO_OUTPUT_DIR")
    output_dir = (Path(output).expanduser().resolve() if output else
                  Path(tempfile.mkdtemp(prefix="tscs-results-")) / "run")
    def input_path(name: str) -> Path | None:
        value = env.get(name)
        return Path(value).expanduser().resolve() if value else None
    return Configuration(output_dir=output_dir, font=env.get("REPRO_FONT") or DEFAULT_FONT,
                         mode=mode, data_file=input_path("REPRO_DATA_FILE"),
                         profile_file=input_path("REPRO_PROFILE_FILE"),
                         calibration_file=input_path("REPRO_CALIBRATION_FILE"))


def _run(root: Path, output: Path, name: str, arguments: list[str | Path]) -> None:
    """Keep diagnostic details in local logs, outside the downloadable results."""
    with (output / "logs" / (name + ".log")).open("w", encoding="utf-8") as log:
        result = subprocess.run([str(value) for value in arguments], cwd=root,
                                stdout=log, stderr=subprocess.STDOUT, check=False)
    if result.returncode:
        raise RuntimeError(f"{name} failed; inspect logs/{name}.log in the output directory")


def _survey_inventory(root: Path, aggregate_root: Path, output: Path) -> None:
    """Record only fixed-schema aggregate tables, with no input paths or mappings."""
    from helpers.notebook_exports import TABLES, _csv_shape, _read
    tables = {}
    for relative in TABLES:
        content = _read(aggregate_root, relative)
        header, rows = _csv_shape(content)
        with (root / "aggregates" / relative).open(encoding="utf-8-sig", newline="") as stream:
            expected_header = next(csv.reader(stream))
        if set(header) != set(expected_header):
            raise ValueError("Reestimated aggregate table has an unexpected schema: " + relative)
        tables[relative] = {"sha256": hashlib.sha256(content).hexdigest(), "rows": rows}
    (output / "aggregate_manifest.json").write_text(
        json.dumps({"status": "pass", "tables": tables}, indent=2) + "\n", encoding="utf-8")


def run_workflow(root: Path, config: Configuration) -> dict:
    """Run the selected input path and draw figures from that run's aggregates."""
    root, output = root.resolve(), config.output_dir.resolve()
    if config.mode not in {"aggregate", "survey"}:
        raise ValueError("MODE must be 'aggregate' or 'survey'")
    if config.mode == "survey":
        from helpers.survey_setup import prepare_upload
        prepared = prepare_upload(root, data_file=config.data_file,
                                  profile_file=config.profile_file,
                                  overrides=config.input_overrides)
        config = replace(config, data_file=prepared.data_file, profile_file=prepared.profile_file)
        if config.calibration_file is not None and not config.calibration_file.is_file():
            raise FileNotFoundError("Set CALIBRATION_FILE to an existing file, or leave it blank")
    if output == root or output.is_relative_to(root):
        raise ValueError("Notebook output must be outside the repository")
    if output.exists():
        raise FileExistsError("Choose a new output directory; existing output is preserved")
    output.mkdir(parents=True)
    (output / "logs").mkdir()
    py = sys.executable
    if config.mode == "aggregate":
        _run(root, output, "bundle", [py, root / "run.py", "verify-only"])
        _run(root, output, "references", [py, root / "ci/check_references.py",
                                          "--root", root / "references"])
        _run(root, output, "aggregates", [py, root / "ci/check_aggregates.py", "--root", root,
                                          "--output", output / "aggregate_check.json"])
        _run(root, output, "figures", [py, root / "ci/build_public_figures.py", "--root", root,
                                       "--output-dir", output / "figures", "--font", config.font])
    else:
        from helpers.survey_input import run_survey
        from helpers.build_figures import build
        print("Reading the selected survey file and reestimating statistics...")
        survey_report = run_survey(config.data_file, config.profile_file, output / "analysis",
                                   calibration_file=config.calibration_file)
        if survey_report.get("status") != "pass":
            raise RuntimeError("Survey reestimation did not complete; no download was created")
        aggregate_root = output / "analysis/aggregates"
        _survey_inventory(root, aggregate_root, output)
        build(aggregate_root, output / "figures", config.font)

    figures = json.loads((output / "figures/figures_manifest.json").read_text(encoding="utf-8"))
    if figures.get("status") != "pass" or figures.get("figure_count") != 9:
        raise RuntimeError("Expected all nine research figures")
    reestimated = config.mode == "survey"
    report = {"status": "pass", "mode": config.mode, "statistical_reestimation": reestimated,
              "input_estimates": "uploaded_survey" if reestimated else "published_aggregates",
              "figure_count": figures["figure_count"],
              "figure_files": ["figures/" + name + ".png" for name in figures["figures"]]}
    if reestimated:
        report["calibration_available"] = bool(survey_report.get("calibration_available", False))
        report["artificial_data"] = bool(survey_report.get("artificial_data", False))
    (output / "notebook_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report
