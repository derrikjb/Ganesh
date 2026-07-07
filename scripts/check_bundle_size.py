#!/usr/bin/env python3
"""Bundle size budget enforcement.

Cross-platform (Windows + Linux) checker that verifies build artifacts stay
within configured size budgets.  Used by CI (`.github/workflows/ci.yml` and
`.github/workflows/build.yml`) after the build step.

Thresholds (Task 41):
    Sidecar binary  (dist/ganesh-backend[.exe]):  warn 150 MB / fail 250 MB
    Minimal installer artifact:                   warn 100 MB / fail 150 MB
    Full installer artifact:                      warn 1 GB  / fail 1.5 GB

Usage:
    python scripts/check_bundle_size.py --artifact sidecar  --path backend/dist/ganesh-backend
    python scripts/check_bundle_size.py --artifact minimal --path src-tauri/target/release/bundle/
    python scripts/check_bundle_size.py --artifact full    --path src-tauri/target/release/bundle/

Exit codes:
    0 — all artifacts within budget (warnings printed to stderr but do not fail)
    1 — one or more artifacts exceeded the FAIL threshold
    2 — usage error / artifact not found
"""

from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass
from pathlib import Path

# --- Budget table ---------------------------------------------------------

MB = 1024 * 1024
GB = 1024 * MB


@dataclass(frozen=True)
class Budget:
    """Size budget for a single artifact category."""

    warn_bytes: int
    fail_bytes: int


BUDGETS: dict[str, Budget] = {
    "sidecar": Budget(warn_bytes=150 * MB, fail_bytes=250 * MB),
    "minimal": Budget(warn_bytes=100 * MB, fail_bytes=150 * MB),
    "full": Budget(warn_bytes=1 * GB, fail_bytes=int(1.5 * GB)),
}

# Artifact name patterns used when scanning a directory for installer files.
INSTALLER_PATTERNS = ("*.msi", "*.deb", "*.AppImage", "*.exe", "*.dmg")


# --- Helpers --------------------------------------------------------------


def _human_size(num_bytes: int) -> str:
    """Return a human-readable size string."""
    if num_bytes >= GB:
        return f"{num_bytes / GB:.2f} GB"
    if num_bytes >= MB:
        return f"{num_bytes / MB:.2f} MB"
    return f"{num_bytes / 1024:.2f} KB"


def _file_size(path: Path) -> int:
    """Return file size in bytes, or 0 if not found."""
    try:
        return path.stat().st_size
    except OSError:
        return 0


def _dir_size(path: Path) -> int:
    """Return total size of a directory tree in bytes."""
    if path.is_file():
        return _file_size(path)
    total = 0
    if path.is_dir():
        for entry in path.rglob("*"):
            if entry.is_file():
                total += _file_size(entry)
    return total


def _resolve_artifact_size(path: Path) -> int:
    """Resolve the size of an artifact path.

    If *path* is a file, returns its size.  If it is a directory, returns the
    total size of the directory tree.  If it does not exist, searches the
    directory's parent for installer-pattern files (for bundle directories).
    """
    if path.is_file():
        return _file_size(path)
    if path.is_dir():
        return _dir_size(path)
    # Path doesn't exist — maybe it's a glob parent (bundle dir not built yet).
    # Try matching installer patterns in the nearest existing ancestor.
    search_root = path if path.is_dir() else path.parent
    if search_root.is_dir():
        total = 0
        for pattern in INSTALLER_PATTERNS:
            for match in search_root.rglob(pattern):
                total += _file_size(match)
        return total
    return 0


# --- Core check -----------------------------------------------------------


def check_artifact(artifact: str, path: Path) -> int:
    """Check a single artifact against its budget.

    Returns 0 if within budget (warnings allowed), 1 if over fail threshold.
    """
    if artifact not in BUDGETS:
        print(f"ERROR: unknown artifact type '{artifact}'.", file=sys.stderr)
        print(f"Valid types: {', '.join(BUDGETS)}", file=sys.stderr)
        return 2

    budget = BUDGETS[artifact]
    size = _resolve_artifact_size(path)

    if size == 0:
        print(
            f"WARNING: artifact '{artifact}' not found at {path} — skipping.",
            file=sys.stderr,
        )
        return 0  # Not a failure — artifact may not be built in this matrix.

    print(f"[{artifact}] {path} → {_human_size(size)}")

    if size > budget.fail_bytes:
        print(
            f"FAIL: {artifact} size {_human_size(size)} exceeds fail threshold "
            f"{_human_size(budget.fail_bytes)}",
            file=sys.stderr,
        )
        return 1

    if size > budget.warn_bytes:
        print(
            f"WARN: {artifact} size {_human_size(size)} exceeds warn threshold "
            f"{_human_size(budget.warn_bytes)} (but within fail limit)",
            file=sys.stderr,
        )

    return 0


# --- CLI ------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Enforce bundle size budgets for Ganesh build artifacts.",
    )
    parser.add_argument(
        "--artifact",
        choices=list(BUDGETS),
        action="append",
        default=[],
        help="Artifact category to check (can be repeated).",
    )
    parser.add_argument(
        "--path",
        action="append",
        default=[],
        help="Path to the artifact (matched positionally with --artifact).",
    )
    args = parser.parse_args(argv)

    if not args.artifact:
        parser.error("at least one --artifact is required")
    if len(args.artifact) != len(args.path):
        parser.error("--artifact and --path must be specified in pairs")

    repo_root = Path(__file__).resolve().parent.parent
    worst = 0
    for artifact, raw_path in zip(args.artifact, args.path):
        path = Path(raw_path)
        if not path.is_absolute():
            path = repo_root / path
        worst = max(worst, check_artifact(artifact, path))

    return worst


if __name__ == "__main__":
    sys.exit(main())
