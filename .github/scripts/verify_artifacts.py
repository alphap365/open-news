#!/usr/bin/env python3
"""Check that a build produced one wheel and one source distribution."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


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

    normalized_version = args.version.replace("-", "_").replace(".", ".")
    for artifact in wheels + sdists:
        if not re.search(rf"(?<![0-9A-Za-z]){re.escape(args.version)}(?![0-9A-Za-z])", artifact.name):
            # Wheel filenames normalize separators; perform a conservative normalized fallback.
            compact_name = artifact.name.replace("-", "_")
            compact_version = normalized_version.replace("-", "_")
            if compact_version not in compact_name:
                print(f"Artifact version does not match {args.version}: {artifact.name}", file=sys.stderr)
                return 1

    print("Verified build artifacts:")
    for artifact in wheels + sdists:
        print(f" - {artifact.name} ({artifact.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
