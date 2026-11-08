#!/usr/bin/env python3
"""Prepare a Binder-only figure preview from the reviewed public aggregates."""
from __future__ import annotations

import argparse
import base64
import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile


GALLERY_TAG = "aggregate-preview"


def preview_cell(notebook: dict) -> dict:
    cells = [cell for cell in notebook["cells"]
             if GALLERY_TAG in cell.get("metadata", {}).get("tags", [])]
    if len(cells) != 1 or cells[0]["cell_type"] != "code":
        raise ValueError("Demo must contain exactly one aggregate-preview code cell")
    return cells[0]


def preview_metadata(root: Path) -> dict:
    return {"source": "published_aggregates", "statistical_reestimation": False,
            "figure_count": 9,
            "manifest_sha256": hashlib.sha256((root / "manifest.json").read_bytes()).hexdigest()}


def validate_preview(notebook: dict, root: Path) -> None:
    """Only the build-generated PNG gallery may be retained in the demo image."""
    from PIL import Image

    if notebook.get("metadata", {}).get("aggregate_preview") != preview_metadata(root):
        raise ValueError("Demo preview does not identify the current public aggregates")
    if notebook.get("metadata", {}).get("widgets"):
        raise ValueError("Demo must not retain widget state")
    gallery = preview_cell(notebook)
    for cell in notebook["cells"]:
        if cell.get("execution_count") is not None or cell.get("attachments"):
            raise ValueError("Demo must not retain execution counts or attachments")
        if cell is not gallery and cell.get("outputs"):
            raise ValueError("Only the aggregate figure gallery may retain outputs")
    outputs = gallery.get("outputs", [])
    if len(outputs) != 9:
        raise ValueError("Demo must contain all nine aggregate figures")
    for index, output in enumerate(outputs, 1):
        if (set(output) != {"output_type", "data", "metadata"}
                or output["output_type"] != "display_data"
                or set(output["data"]) != {"image/png", "text/plain"}
                or output["data"]["text/plain"] != f"Published aggregate figure {index}"
                or output["metadata"] != {"image/png": {"width": 1000}}):
            raise ValueError("Unexpected demo output; only public PNG figures are allowed")
        try:
            payload = base64.b64decode(output["data"]["image/png"], validate=True)
            with Image.open(io.BytesIO(payload)) as image:
                if image.format != "PNG":
                    raise ValueError("Demo figure is not PNG")
                image.verify()
        except (ValueError, TypeError, OSError) as exc:
            raise ValueError("Invalid demo PNG figure") from exc


def prepare(root: Path, output: Path) -> dict:
    """Render fresh public figures; never read an uploaded SAV or save run logs."""
    import nbformat

    root = root.resolve()
    sys.path.insert(0, str(root))
    from helpers.notebook_workflow import Configuration, default_font, run_workflow

    notebook = nbformat.read(root / "notebooks/demo.ipynb", as_version=4)
    nbformat.validate(notebook)
    if any(cell.get("outputs") or cell.get("execution_count") is not None
           or cell.get("attachments") for cell in notebook.cells):
        raise ValueError("Prepare the demo from a clean source Notebook")
    gallery = preview_cell(notebook)
    with tempfile.TemporaryDirectory(prefix="tscs-demo-preview-") as temporary:
        directory = Path(temporary) / "run"
        report = run_workflow(root, Configuration(directory, default_font(), mode="aggregate"))
        if report["statistical_reestimation"] or report["figure_count"] != 9:
            raise ValueError("Demo requires nine public aggregate figures")
        gallery.outputs = [nbformat.v4.new_output(
            "display_data",
            data={"image/png": base64.b64encode((directory / name).read_bytes()).decode("ascii"),
                  "text/plain": f"Published aggregate figure {index}"},
            metadata={"image/png": {"width": 1000}},
        ) for index, name in enumerate(report["figure_files"], 1)]
    notebook.metadata["aggregate_preview"] = preview_metadata(root)
    validate_preview(notebook, root)
    nbformat.validate(notebook)
    output.parent.mkdir(parents=True, exist_ok=True)
    nbformat.write(notebook, output)
    return {"figure_count": 9, "source": "published_aggregates", "statistical_reestimation": False}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output", type=Path, required=True,
                        help="In Binder's image use notebooks/demo.ipynb; locally use a temporary path")
    args = parser.parse_args()
    print(json.dumps(prepare(args.root, args.output), indent=2))


if __name__ == "__main__":
    main()
