#!/usr/bin/env python3
"""Inspect manual survey inputs, reestimate results, or check existing aggregates."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from ci.check_aggregates import validate as check_aggregates
from ci.check_references import validate as check_references

ROOT = Path(__file__).resolve().parent


def verify(root: Path = ROOT) -> dict:
    return {"status": "pass", "statistical_reestimation": False,
            "aggregates": check_aggregates(root),
            "references": check_references(root / "references")}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("verify-only", help="Check tables, BY adjustments, sensitivity summaries and references")
    figures = commands.add_parser("figures", help="Verify the aggregates and redraw nine figures")
    figures.add_argument("--output-dir", type=Path, required=True)
    figures.add_argument("--font", default="/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc")
    inspect = commands.add_parser("inspect", help="Create a local input profile and metadata catalogue")
    inspect.add_argument("--data-file", type=Path, required=True)
    inspect.add_argument("--output-profile", type=Path, required=True)
    demo = commands.add_parser("demo", help="Generate artificial data for testing the upload workflow")
    demo.add_argument("--output-dir", type=Path, required=True)
    survey = commands.add_parser("reestimate", help="Reestimate statistics and figures from a user-supplied SAV")
    survey.add_argument("--data-file", type=Path, required=True)
    survey.add_argument("--profile-file", type=Path, required=True)
    survey.add_argument("--calibration-file", type=Path)
    survey.add_argument("--output-dir", type=Path, required=True)
    survey.add_argument("--font", default="/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc")
    args = parser.parse_args()
    if args.command == "inspect":
        from helpers.survey_input import inspect_survey
        report = inspect_survey(args.data_file, args.output_profile)
    elif args.command == "demo":
        from helpers.survey_demo import make_demo
        report = make_demo(args.output_dir)
    elif args.command == "reestimate":
        from helpers.notebook_workflow import Configuration, run_workflow
        config = Configuration(output_dir=args.output_dir.expanduser().resolve(), font=args.font,
                               mode="survey", data_file=args.data_file, profile_file=args.profile_file,
                               calibration_file=args.calibration_file)
        report = run_workflow(ROOT, config)
    else:
        report = verify()
    if args.command == "figures":
        from helpers.build_figures import build

        output = args.output_dir.expanduser().resolve()
        if output == ROOT or output.is_relative_to(ROOT):
            parser.error("Choose an output directory outside the repository")
        if output.exists():
            parser.error("Output already exists; choose a new directory to preserve earlier results")
        report["figures"] = build(ROOT / "aggregates", output, args.font)
    print(json.dumps(report, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
