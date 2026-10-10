#!/usr/bin/env python3
"""Fail-closed validation for an explicitly requested package release."""

from __future__ import annotations

import argparse
import os
import re
import sys
import tomllib
from pathlib import Path

try:
    from packaging.version import InvalidVersion, Version
except ImportError as exc:  # pragma: no cover - CI installs packaging with build tools
    raise SystemExit("Missing 'packaging'. Install it with: python -m pip install packaging") from exc


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", required=True, help="Version explicitly confirmed by the operator")
    parser.add_argument("--tag", required=True, help="Selected Git tag, e.g. v1.1.0a1")
    parser.add_argument("--channel", choices=("testpypi",), required=True)
    args = parser.parse_args()

    with Path("pyproject.toml").open("rb") as handle:
        project_version = str(tomllib.load(handle)["project"]["version"])

    tag_version = args.tag[1:] if args.tag.startswith("v") else args.tag
    if not re.fullmatch(r"v?[A-Za-z0-9][A-Za-z0-9.!+_-]*", args.tag):
        print(f"Refusing: invalid tag format {args.tag!r}.", file=sys.stderr)
        return 1

    try:
        parsed = Version(project_version)
    except InvalidVersion:
        print(f"Refusing: pyproject version {project_version!r} is not valid PEP 440.", file=sys.stderr)
        return 1

    if args.version != project_version:
        print(
            f"Refusing: confirmation {args.version!r} does not match pyproject version {project_version!r}.",
            file=sys.stderr,
        )
        return 1
    if tag_version != project_version:
        print(f"Refusing: tag version {tag_version!r} does not match pyproject version {project_version!r}.", file=sys.stderr)
        return 1
    if not (parsed.is_prerelease or parsed.is_devrelease):
        print(f"Refusing: {project_version} is not a prerelease/dev version; this workflow only permits TestPyPI prereleases.", file=sys.stderr)
        return 1

    output = os.environ.get("GITHUB_OUTPUT")
    if output:
        with open(output, "a", encoding="utf-8") as handle:
            handle.write(f"version={project_version}\n")
    print(f"Validated TestPyPI prerelease: {project_version} ({args.tag}).")
    print("This workflow has no production PyPI publishing destination.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
