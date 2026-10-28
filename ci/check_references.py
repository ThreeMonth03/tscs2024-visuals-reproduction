#!/usr/bin/env python3
"""Check published reference inventory and attribution without network access."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
from urllib.parse import urlparse

EXPECTED_REFERENCE_COUNT = 23


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def local_path(root: Path, relative: str) -> Path:
    path = root / relative
    require(not Path(relative).is_absolute() and ".." not in Path(relative).parts,
            "Invalid reference path")
    require(path.resolve().is_relative_to(root.resolve()) and not path.is_symlink(),
            "Invalid reference path")
    require(path.is_file(), "Missing reference file: " + relative)
    return path


def public_url(value: str | None) -> bool:
    parsed = urlparse(value or "")
    return bool(parsed.scheme == "https" and parsed.hostname and not parsed.username and not parsed.password)


def validate(root: Path) -> dict:
    manifest = json.loads((root / "publication_manifest.json").read_text(encoding="utf-8"))
    catalog = json.loads((root / "references.json").read_text(encoding="utf-8"))["references"]
    entries = manifest["files"]
    paths = {entry["path"] for entry in entries}
    require(len(paths) == len(entries), "Duplicate publication manifest path")
    actual = {str(path.relative_to(root)) for path in root.rglob("*") if path.is_file() or path.is_symlink()}
    require(actual == paths | {"publication_manifest.json"}, "Reference files differ from the publication allowlist")
    contents = {}
    for entry in entries:
        data = local_path(root, entry["path"]).read_bytes()
        require(hashlib.sha256(data).hexdigest() == entry["sha256"] and len(data) == entry["bytes"],
                "Reference hash or size changed: " + entry["path"])
        contents[entry["path"]] = data
    keys = [entry["key"] for entry in catalog]
    require(len(keys) == len(set(keys)) == EXPECTED_REFERENCE_COUNT,
            "Expected 23 distinct manuscript citations")
    bibliography_keys = re.findall(r"(?m)^@\w+\{([^,]+),", contents["cited_references.bib"].decode("utf-8"))
    require(len(bibliography_keys) == len(set(bibliography_keys)) and set(bibliography_keys) == set(keys),
            "Bibliography and reference catalog keys differ")
    mirrored = set()
    for entry in catalog:
        require(public_url(entry.get("official_url")), "Missing official reference entry")
        if not entry.get("local_pdf"):
            continue
        relative = entry["local_pdf"]
        require(relative in paths and relative.endswith(".pdf") and entry.get("redistribution_license")
                and public_url(entry.get("license_evidence_url")),
                "Mirrored PDF requires provenance and redistribution evidence")
        data = contents[relative]
        require(data.startswith(b"%PDF-") and hashlib.sha256(data).hexdigest() == entry["sha256"],
                "PDF signature or catalog hash mismatch")
        mirrored.add(relative)
    require(mirrored == {path for path in paths if path.endswith(".pdf")}, "Uncatalogued reference PDF")
    return {"status": "pass", "references": len(catalog), "redistributable_pdfs": len(mirrored),
            "links_only": len(catalog) - len(mirrored)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1] / "references")
    args = parser.parse_args()
    print(json.dumps(validate(args.root.resolve())))


if __name__ == "__main__":
    main()
