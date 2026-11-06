"""Validate a dependency wheel produced by the build workflow."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from packaging.utils import parse_wheel_filename
from packaging.version import Version


def normalize_name(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--directory", required=True)
    parser.add_argument("--package", required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--target", required=True)
    parser.add_argument("--python-tag", required=True)
    args = parser.parse_args()

    wheels = sorted(Path(args.directory).glob("*.whl"))

    if not wheels:
        print("No wheels were produced.", file=sys.stderr)
        return 1

    valid = []

    for wheel in wheels:
        try:
            name, version, build, tags = parse_wheel_filename(wheel.name)
        except Exception as exc:
            print(f"Invalid wheel filename {wheel.name}: {exc}", file=sys.stderr)
            continue

        if normalize_name(name) != normalize_name(args.package):
            print(f"Wrong package in wheel: {wheel.name}", file=sys.stderr)
            continue

        if Version(str(version)) != Version(args.version):
            print(f"Wrong version in wheel: {wheel.name}", file=sys.stderr)
            continue

        if not any(tag.interpreter == args.python_tag for tag in tags):
            print(
                f"Wheel does not contain requested interpreter "
                f"{args.python_tag}: {wheel.name}",
                file=sys.stderr,
            )
            continue

        if not any(tag.platform != "any" for tag in tags):
            print(
                f"Expected a platform wheel, got {wheel.name}",
                file=sys.stderr,
            )
            continue

        valid.append(wheel)

    if not valid:
        print("No wheel passed validation.", file=sys.stderr)
        return 1

    for wheel in valid:
        print(f"VALID: {wheel.name}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())