# verify_artifacts.py
#!/usr/bin/env python3
"""Check that a build produced one wheel and one source distribution."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

try:
    from packaging.version import InvalidVersion, Version
    _HAS_PACKAGING = True
except ImportError:
    _HAS_PACKAGING = False


def _version_present(name: str, version: str) -> bool:
    # Token-boundary match on the raw version string.
    if re.search(rf"(?<![0-9A-Za-z]){re.escape(version)}(?![0-9A-Za-z])", name):
        return True
    # PEP 440 canonical check covers cases like `1.1.0-rc1` -> `1.1.0rc1`
    # in the built filename while the pyproject string stayed un-canonical.
    if _HAS_PACKAGING:
        try:
            canonical = str(Version(version))
        except InvalidVersion:
            return False
        if canonical != version and canonical in name:
            return True
    return False


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dist", type=Path, default=Path("dist"))
    parser.add_argument("--version", required=True)
    args = parser.parse_args()

    if not args.dist.is_dir():
        print(f"Missing distribution directory: {args.dist}", file=sys.stderr)
        return 1

    files = sorted(path for path in args.dist.iterdir() if path.is_file())
    wheels = [path for path in files if path.suffix == ".whl"]
    sdists = [path for path in files if path.name.endswith((".tar.gz", ".zip"))]
    unexpected = [path for path in files if path not in wheels and path not in sdists]

    if len(wheels) != 1 or len(sdists) != 1 or unexpected:
        print("Expected exactly one wheel and one source distribution; no other files are allowed.", file=sys.stderr)
        print("Found:", *(str(path) for path in files), sep="\n  ", file=sys.stderr)
        return 1

    for artifact in wheels + sdists:
        if not _version_present(artifact.name, args.version):
            print(f"Artifact version does not match {args.version}: {artifact.name}", file=sys.stderr)
            return 1

    print("Verified build artifacts:")
    for artifact in wheels + sdists:
        print(f" - {artifact.name} ({artifact.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())