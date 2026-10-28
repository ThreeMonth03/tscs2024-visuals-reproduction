#!/usr/bin/env python3
"""Reject unreviewed files and common private-data formats in the public tree.

The Git index is checked so that ignored local runs are never read or uploaded.
New published files require an explicit update of a reviewed inventory.
"""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path, PurePosixPath
import subprocess

POLICY_PATH = "ci/release_files.json"
FORBIDDEN_SUFFIXES = {
    ".sav", ".xlsx", ".xls", ".dta", ".parquet", ".rds", ".rdata", ".docx", ".pptx", ".zip",
}
FORBIDDEN_DIRECTORIES = {
    "raw", "processed", "private-data", ".codex-build", "document_sync", "node_modules",
}
INDIVIDUAL_COLUMNS = {
    "respondent_id", "respondent", "case_id", "idno", "telephone", "phone_number", "email", "address",
}


def safe_file(root: Path, relative: str) -> Path:
    """Accept only canonical, regular, in-tree paths without symlink parents."""
    parsed = PurePosixPath(relative)
    if (not relative or "\\" in relative or parsed.is_absolute()
            or ".." in parsed.parts or str(parsed) != relative):
        raise ValueError(f"Invalid release path: {relative}")
    path = root / relative
    if not path.resolve().is_relative_to(root.resolve()):
        raise ValueError(f"Release path escapes repository: {relative}")
    if any((root / Path(*parsed.parts[:i])).is_symlink() for i in range(1, len(parsed.parts) + 1)):
        raise ValueError(f"Release path contains a symlink: {relative}")
    if not path.is_file():
        raise ValueError(f"Missing release file: {relative}")
    return path


def read_json(root: Path, relative: str) -> dict:
    return json.loads(safe_file(root, relative).read_text(encoding="utf-8"))


def declared_files(root: Path) -> set[str]:
    bundle = read_json(root, "manifest.json")
    if bundle.get("data_included") is not False:
        raise ValueError("Public bundle must exclude individual data")
    references = read_json(root, "references/publication_manifest.json")
    policy = read_json(root, POLICY_PATH)
    if policy.get("schema_version") != 1:
        raise ValueError("Unknown release inventory schema")
    support = policy["support_files"]
    if len(support) != len(set(support)):
        raise ValueError("Duplicate support-file entry")
    return (set(bundle["files"]) | {"manifest.json", "references/publication_manifest.json"}
            | {"references/" + item["path"] for item in references["files"]} | set(support))


def tracked_files(root: Path) -> set[str]:
    top = subprocess.check_output(["git", "rev-parse", "--show-toplevel"], cwd=root, text=True).strip()
    if Path(top).resolve() != root.resolve():
        raise ValueError("Run the release check at the public repository root")
    output = subprocess.check_output(["git", "ls-files", "-z"], cwd=root)
    return {path.decode("utf-8") for path in output.split(b"\0") if path}


def validate(root: Path) -> dict:
    root = root.resolve()
    allowed, tracked = declared_files(root), tracked_files(root)
    if tracked != allowed:
        raise ValueError(
            f"Release inventory mismatch: unreviewed={sorted(tracked - allowed)}, "
            f"missing={sorted(allowed - tracked)}"
        )
    csv_count = 0
    for relative in sorted(tracked):
        path = safe_file(root, relative)
        directories = set(PurePosixPath(relative).parts[:-1])
        if path.suffix.lower() in FORBIDDEN_SUFFIXES or FORBIDDEN_DIRECTORIES.intersection(directories):
            raise ValueError(f"Private data or document format is not permitted: {relative}")
        if path.suffix.lower() == ".pdf" and not relative.startswith("references/pdfs/"):
            raise ValueError(f"Only catalogued reference PDFs are published: {relative}")
        if path.suffix.lower() == ".ipynb":
            notebook = json.loads(path.read_text(encoding="utf-8"))
            if notebook.get("metadata", {}).get("widgets"):
                raise ValueError(f"Notebook widget state must be cleared: {relative}")
            for cell in notebook.get("cells", []):
                if cell.get("outputs") or cell.get("execution_count") is not None or cell.get("attachments"):
                    raise ValueError(f"Notebook execution output must be cleared: {relative}")
        with path.open("rb") as stream:
            if stream.read(4) in {b"$FL2", b"$FL3"}:
                raise ValueError(f"Individual survey data signature: {relative}")
        if path.suffix.lower() == ".csv":
            with path.open(encoding="utf-8-sig", newline="") as stream:
                header = next(csv.reader(stream), [])
            if INDIVIDUAL_COLUMNS.intersection(column.strip().casefold() for column in header):
                raise ValueError(f"Individual-data columns are not permitted: {relative}")
            csv_count += 1
    return {"status": "pass", "tracked_files": len(tracked), "aggregate_or_reference_csvs": csv_count,
            "scope": "Reviewed Git index inventory, path safety and common private-data formats; numerical and reference checks run separately."}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    print(json.dumps(validate(args.root), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
