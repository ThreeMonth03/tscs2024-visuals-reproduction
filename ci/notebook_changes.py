#!/usr/bin/env python3
"""Select the complete Notebook check without skipping the basic CI checks."""
from __future__ import annotations

import argparse
import fnmatch
import json
import os
from pathlib import Path
import re
import subprocess


RUNTIME_PREFIXES = (
    "helpers/", "ci/", "tests/", "notebooks/", ".binder/",
    ".github/workflows/", "reference_data/",
)
RUNTIME_FILES = {"run.py", "environment.json", ".dockerignore"}


def runtime_path(path: str) -> bool:
    """Include analysis configuration and all code exercised by the Notebook."""
    if path.lower().endswith((".md", ".rst")):
        return False
    return (path in RUNTIME_FILES or path.startswith(RUNTIME_PREFIXES)
            or ("/" not in path and fnmatch.fnmatchcase(path, "requirements*.txt")))


def _decision(run: bool, reason: str, paths: list[str] | None = None) -> dict:
    return {"run_notebook": run, "reason": reason, "changed_paths": paths or []}


def _commit(value: object) -> str | None:
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-fA-F]{40}", value):
        return None
    return value.lower() if value != "0" * 40 else None


def determine(event_name: str, event: dict, root: Path) -> dict:
    """Compare complete Git histories; uncertainty selects the full check.

    Pushes compare the before/after trees. Pull requests use their merge base,
    so unrelated changes on the target branch do not count as PR changes.
    Renames are treated as a deletion and an addition to check both paths.
    """
    if event_name == "workflow_dispatch":
        return _decision(True, "Manual dispatch requests the complete Notebook check.")
    if not isinstance(event, dict):
        return _decision(True, "Event metadata is unavailable; running the complete check.")
    if event_name == "push":
        before, after = _commit(event.get("before")), _commit(event.get("after"))
        revisions = [before, after]
    elif event_name == "pull_request":
        request = event.get("pull_request")
        if not isinstance(request, dict):
            request = {}
        base, head = request.get("base"), request.get("head")
        before = _commit(base.get("sha")) if isinstance(base, dict) else None
        after = _commit(head.get("sha")) if isinstance(head, dict) else None
        revisions = [f"{before}...{after}"]
    else:
        return _decision(True, "Unrecognized event type; running the complete check.")
    if before is None or after is None:
        return _decision(True, "Comparison commits are unavailable; running the complete check.")
    try:
        result = subprocess.run(
            ["git", "diff", "--no-ext-diff", "--name-only", "--no-renames", "-z", *revisions, "--"],
            cwd=Path(root), check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return _decision(True, "Git comparison is unavailable; running the complete check.")
    paths = sorted(set(path.decode("utf-8", errors="surrogateescape")
                       for path in result.stdout.split(b"\0") if path))
    if any(runtime_path(path) for path in paths):
        return _decision(True, "Code, Notebook, environment or analysis configuration changed.", paths)
    return _decision(False, "No Notebook runtime changes; basic checks still run.", paths)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--event-name", default=os.environ.get("GITHUB_EVENT_NAME", ""))
    parser.add_argument("--event-path", type=Path, default=os.environ.get("GITHUB_EVENT_PATH"))
    parser.add_argument("--root", type=Path, default=Path.cwd())
    args = parser.parse_args()
    try:
        event = json.loads(args.event_path.read_text(encoding="utf-8")) if args.event_path else {}
    except (OSError, ValueError):
        event = {}
    decision = determine(args.event_name, event, args.root)
    selected = str(decision["run_notebook"]).lower()
    if output := os.environ.get("GITHUB_OUTPUT"):
        with Path(output).open("a", encoding="utf-8") as stream:
            stream.write(f"run_notebook={selected}\n")
    if summary := os.environ.get("GITHUB_STEP_SUMMARY"):
        with Path(summary).open("a", encoding="utf-8") as stream:
            stream.write("## Notebook check selection\n\n")
            stream.write(f"Complete Notebook check: **{'run' if decision['run_notebook'] else 'skip'}**. ")
            stream.write(decision["reason"] + "\n\n")
            stream.write("Basic checks run on every supported event. Actual respondent data are not used.\n")
    # Paths are diagnostic only; never interpolate them into a shell or output key.
    paths = decision.pop("changed_paths")
    decision.update(changed_file_count=len(paths), changed_paths=[path[:240] for path in paths[:50]],
                    paths_truncated=len(paths) > 50 or any(len(path) > 240 for path in paths))
    print(json.dumps(decision, indent=2))


if __name__ == "__main__":
    main()
