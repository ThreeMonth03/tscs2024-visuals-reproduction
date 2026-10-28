#!/usr/bin/env python3
"""Render the nine figures from released aggregate profiles, without reestimation."""
from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path


def build_public_figures(root: Path, output: Path, font: str) -> dict:
    """Use the selected package's standalone aggregate renderer."""
    # --root may select a bundle other than the one containing this CLI.
    helper_path = root / "helpers/build_figures.py"
    spec = importlib.util.spec_from_file_location("bundle_figure_helper", helper_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load figure helper: {helper_path}")
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    report = helper.build(root / "aggregates", output, font)
    report["input_estimates"] = "published_aggregates"
    report["scope"] = (
        "Nine original research figures regenerated from released aggregate profiles; "
        "no individual data, survey estimation or sensitivity reestimation is performed by this job."
    )
    (output / "figures_manifest.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--font", required=True)
    args = parser.parse_args()
    report = build_public_figures(args.root.resolve(), args.output_dir, args.font)
    print(json.dumps({
        "figure_count": report["figure_count"],
        "selected_rows": report["selected_rows"],
        "statistical_reestimation": False,
        "input_estimates": report["input_estimates"],
    }, indent=2))


if __name__ == "__main__":
    main()
