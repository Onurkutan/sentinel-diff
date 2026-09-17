#!/usr/bin/env python3
"""
Repository Hygiene & Publish-Safety Checker for sentinel-diff.
Ensures zero secret leaks, no raw satellite data in git, and no local path leaks.
"""

import os
import re
import subprocess
import sys
from pathlib import Path

# Patterns indicating credentials or secrets
SECRET_PATTERNS = [
    (re.compile(r"(?i)(api[_-]?key|secret[_-]?key|access[_-]?token)\s*[:=]\s*['\"][A-Za-z0-9_\-]{8,}['\"]"), "API Key/Token assignment"),
    (re.compile(r"gho_[A-Za-z0-9_]{20,}"), "GitHub Personal Access Token"),
    (re.compile(r"ghp_[A-Za-z0-9_]{20,}"), "GitHub Classic Token"),
    (re.compile(r"AKIA[0-9A-Z]{16}"), "AWS Access Key ID"),
    (re.compile(r"AIza[0-9A-Za-z\\-_]{35}"), "Google API Key"),
    (re.compile(r"-----BEGIN (RSA|EC|OPENSSH|DSA|PGP) PRIVATE KEY-----"), "Private Key block"),
]

# Sensitive or large file extensions that should NEVER be tracked in git
FORBIDDEN_EXTENSIONS = {
    ".tif", ".tiff", ".jp2", ".h5", ".hdf", ".nc", ".parquet",
    ".zip", ".tar", ".gz", ".7z",
    ".env", ".key", ".pem", ".secret", ".token"
}

# Patterns indicating hardcoded user paths
LOCAL_PATH_PATTERNS = [
    re.compile(r"[A-Za-z]:\\[Uu]sers\\[A-Za-z0-9_\\-]+"),
    re.compile(r"/home/[A-Za-z0-9_\\-]+"),
]

MAX_FILE_SIZE_BYTES = 2 * 1024 * 1024  # 2 MB


def get_tracked_files():
    """Get list of files tracked by git."""
    try:
        res = subprocess.run(
            ["git", "ls-files"],
            capture_output=True,
            text=True,
            check=True
        )
        return [f.strip() for f in res.stdout.splitlines() if f.strip()]
    except Exception as e:
        print(f"Warning: git ls-files failed ({e}). Scanning directory directly.")
        files = []
        for root, _, filenames in os.walk("."):
            if ".git" in root or ".venv" in root:
                continue
            for name in filenames:
                files.append(os.path.relpath(os.path.join(root, name), "."))
        return files


def check_hygiene():
    repo_root = Path(__file__).resolve().parent.parent
    os.chdir(repo_root)

    tracked_files = get_tracked_files()
    errors = []
    warnings = []

    for rel_path in tracked_files:
        p = Path(rel_path)
        if not p.is_file():
            continue

        # 1. Extension check
        if p.suffix.lower() in FORBIDDEN_EXTENSIONS:
            errors.append(f"Forbidden extension committed: {rel_path}")

        # 2. File size check
        size = p.stat().st_size
        if size > MAX_FILE_SIZE_BYTES:
            errors.append(f"File exceeds maximum allowed size ({size / 1024 / 1024:.2f} MB > 2 MB): {rel_path}")

        # 3. Content scanning (text files only)
        try:
            content = p.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue

        # Check for secrets
        for pattern, desc in SECRET_PATTERNS:
            if pattern.search(content):
                errors.append(f"Possible secret leak ({desc}) in: {rel_path}")

        # Check for hardcoded local user paths (skip this script itself)
        if rel_path != "scripts/check_repo_hygiene.py":
            for pat in LOCAL_PATH_PATTERNS:
                if pat.search(content):
                    warnings.append(f"Local environment path detected in: {rel_path}")

    print("========================================")
    print("      Sentinel-Diff Hygiene Report      ")
    print("========================================")
    print(f"Scanned {len(tracked_files)} tracked files.")

    if warnings:
        print("\nWarnings:")
        for w in warnings:
            print(f"  [WARN] {w}")

    if errors:
        print("\nERRORS DETECTED:")
        for err in errors:
            print(f"  [ERROR] {err}")
        print("\nResult: FAILED - Do not publish until issues are resolved.")
        sys.exit(1)

    print("\nResult: PASSED. No secrets, forbidden extensions, or oversized files detected.")
    sys.exit(0)


if __name__ == "__main__":
    check_hygiene()
