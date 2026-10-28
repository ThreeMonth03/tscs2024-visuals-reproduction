#!/usr/bin/env python3
"""Execute the thin notebook with this Python and keep all outputs outside Git."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import sys
from urllib.parse import unquote, urlsplit


def check_notebook_links(root: Path, notebook: dict) -> None:
    """Check local Markdown targets in the installed image, before execution."""
    root = root.resolve()
    for cell in notebook["cells"]:
        if cell["cell_type"] != "markdown":
            continue
        source = cell["source"]
        text = source if isinstance(source, str) else "".join(source)
        for link in re.findall(r"\[[^\]]*\]\(([^\s)]+)\)", text):
            url = urlsplit(link)
            if url.scheme or url.netloc or not url.path:
                continue
            target = (root / "notebooks" / unquote(url.path)).resolve()
            if not target.is_relative_to(root) or not target.is_file():
                raise FileNotFoundError("Notebook documentation link is unavailable: " + link)


def execution_environment(
    args: argparse.Namespace, output: Path, inherited: dict[str, str]
) -> dict[str, str]:
    """Use this run's output path while retaining the installed font."""
    env = inherited.copy()
    env.pop("PYTHONOPTIMIZE", None)
    env.update(
        REPRO_OUTPUT_DIR=str(output / "run"),
        PYTHONDONTWRITEBYTECODE="1",
        OPENBLAS_NUM_THREADS="1",
        OMP_NUM_THREADS="1",
    )
    env.update(REPRO_MODE=getattr(args, "mode", "aggregate"),
               REPRO_DATA_FILE=str(getattr(args, "data_file", None) or ""),
               REPRO_PROFILE_FILE=str(getattr(args, "profile_file", None) or ""),
               REPRO_CALIBRATION_FILE=str(getattr(args, "calibration_file", None) or ""))
    if args.font is not None:
        env["REPRO_FONT"] = args.font
    return env


def apply_cli_settings(notebook: dict, env: dict[str, str]) -> None:
    """Replace settings in memory; the source notebook remains unchanged."""
    cells = [cell for cell in notebook["cells"]
             if "parameters" in cell.get("metadata", {}).get("tags", [])]
    if len(cells) != 1 or cells[0]["cell_type"] != "code":
        raise ValueError("Notebook must contain exactly one parameters code cell")
    cells[0]["source"] = (
        "# Settings from this CLI invocation; the source notebook remains unchanged.\n"
        f"MODE = {env.get('REPRO_MODE', 'aggregate')!r}\n"
        f"DATA_FILE = {env.get('REPRO_DATA_FILE', '')!r}\n"
        f"PROFILE_FILE = {env.get('REPRO_PROFILE_FILE', '')!r}\n"
        f"CALIBRATION_FILE = {env.get('REPRO_CALIBRATION_FILE', '')!r}\n"
        f"OUTPUT_DIR = {env['REPRO_OUTPUT_DIR']!r}\n"
        f"FONT = {env.get('REPRO_FONT', '')!r}\n"
        "INPUT_OVERRIDES = {}\n"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--font")
    parser.add_argument("--mode", choices=["aggregate", "survey"], default="aggregate")
    parser.add_argument("--data-file", type=Path)
    parser.add_argument("--profile-file", type=Path)
    parser.add_argument("--calibration-file", type=Path)
    parser.add_argument("--timeout", type=int, default=600,
                        help="Maximum seconds per notebook cell")
    args = parser.parse_args()
    root, output = args.root.resolve(), args.output_dir.resolve()
    if output == root or output.is_relative_to(root):
        parser.error("--output-dir must be a new directory outside the repository")
    if output.exists():
        parser.error("--output-dir already exists; previous results are preserved")
    if args.timeout < 1:
        parser.error("--timeout must be positive")

    import nbformat
    from nbclient import NotebookClient
    from jupyter_client import KernelManager
    from jupyter_client.kernelspec import KernelSpecManager

    notebook = nbformat.read(root / "notebooks/reproduce.ipynb", as_version=4)
    nbformat.validate(notebook)
    check_notebook_links(root, notebook)
    if any(cell.get("outputs") or cell.get("execution_count") is not None
           for cell in notebook.cells if cell.cell_type == "code"):
        raise ValueError("The committed notebook must have empty outputs and execution counts")
    env = execution_environment(args, output, dict(os.environ))
    apply_cli_settings(notebook, env)
    output.mkdir(parents=True)
    kernels = output / "kernels"
    kernel_dir = kernels / "tscs-reproduction"
    kernel_dir.mkdir(parents=True)
    (kernel_dir / "kernel.json").write_text(json.dumps({
        "argv": [sys.executable, "-m", "ipykernel_launcher", "-f", "{connection_file}"],
        "display_name": "TSCS reproduction", "language": "python"}), encoding="utf-8")
    manager = KernelManager(kernel_name="tscs-reproduction",
                            kernel_spec_manager=KernelSpecManager(kernel_dirs=[str(kernels)]))
    client = NotebookClient(notebook, km=manager, timeout=args.timeout, allow_errors=False,
                            resources={"metadata": {"path": str(root)}})
    try:
        client.execute(cwd=str(root), env=env, cleanup_kc=True)
    finally:
        # Local diagnostic artifact only; the source notebook is never modified.
        nbformat.write(notebook, output / "executed.ipynb")
    report = json.loads((output / "run/notebook_report.json").read_text(encoding="utf-8"))
    download_report = output / "run/download_report.json"
    if download_report.is_file():
        report["downloads"] = json.loads(download_report.read_text(encoding="utf-8"))
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
