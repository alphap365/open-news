#!/usr/bin/env python3
"""
Create a reproducible Open News dependency-wheel bundle.

Bundle layout:
    manifest.json
    SHA256SUMS.txt
    wheels/
        package_a-1.0-cp313-...whl
        package_b-2.0-py3-none-any.whl

The Open News version is always read from pyproject.toml.

Optional verification:
    --verification-report wheel-verification.json

When supplied, the report must indicate success and contain no invalid
or missing wheel combinations.

Usage:
    python .github/scripts/bundle_wheels.py \
        --wheel-dir dist \
        --output dependency-build/open-news-dependencies.zip \
        --project-file pyproject.toml \
        --verification-report wheel-verification.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tomllib
import zipfile
from pathlib import Path
from typing import Any

try:
    from packaging.utils import canonicalize_name, parse_wheel_filename
except ImportError:
    print(
        "ERROR: packaging is required. Install it with: "
        "python -m pip install packaging",
        file=sys.stderr,
    )
    raise SystemExit(2)


BUNDLE_SCHEMA_VERSION = 1
ZIP_TIMESTAMP = (1980, 1, 1, 0, 0, 0)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()

    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)

    return digest.hexdigest()


def read_project_metadata(path: Path) -> dict[str, str]:
    if not path.is_file():
        raise ValueError(f"Project file does not exist: {path}")

    try:
        with path.open("rb") as file:
            data = tomllib.load(file)
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise ValueError(f"Cannot read {path}: {exc}") from exc

    project = data.get("project")

    if not isinstance(project, dict):
        raise ValueError(f"{path} does not contain a [project] section.")

    name = project.get("name")
    version = project.get("version")

    if not isinstance(name, str) or not name.strip():
        raise ValueError("pyproject.toml has no valid project.name.")

    if not isinstance(version, str) or not version.strip():
        raise ValueError("pyproject.toml has no static project.version.")

    return {
        "name": name,
        "canonical_name": canonicalize_name(name),
        "version": version,
    }


def load_verification_report(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise ValueError(f"Verification report does not exist: {path}")

    try:
        report = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Cannot read verification report: {exc}") from exc

    if not isinstance(report, dict):
        raise ValueError("Verification report must be a JSON object.")

    if report.get("success") is not True:
        raise ValueError(
            "Wheel verification did not pass. Refusing to create the dependency bundle."
        )

    if report.get("missing"):
        raise ValueError("Verification report contains missing combinations.")

    if report.get("invalid_wheels"):
        raise ValueError("Verification report contains invalid wheels.")

    return report


def discover_wheels(wheel_dir: Path) -> list[Path]:
    if not wheel_dir.is_dir():
        raise ValueError(f"Wheel directory does not exist: {wheel_dir}")

    wheels = sorted(
        path
        for path in wheel_dir.rglob("*.whl")
        if path.is_file() and not path.is_symlink()
    )

    if not wheels:
        raise ValueError(f"No wheel files found in {wheel_dir}")

    filenames: set[str] = set()

    for wheel in wheels:
        if wheel.name in filenames:
            raise ValueError(f"Duplicate wheel filename found: {wheel.name}")

        filenames.add(wheel.name)

    return wheels


def inspect_wheel(path: Path) -> dict[str, Any]:
    try:
        distribution, version, build, tags = parse_wheel_filename(path.name)
    except Exception as exc:
        raise ValueError(f"Invalid wheel filename {path.name}: {exc}") from exc

    try:
        with zipfile.ZipFile(path) as archive:
            bad_member = archive.testzip()

            if bad_member:
                raise ValueError(f"Corrupt ZIP member in {path.name}: {bad_member}")

            metadata_files = [
                name
                for name in archive.namelist()
                if name.endswith(".dist-info/METADATA")
            ]

            if len(metadata_files) != 1:
                raise ValueError(f"{path.name}: expected exactly one METADATA file.")

            from email.parser import Parser

            metadata_text = archive.read(metadata_files[0]).decode(
                "utf-8", errors="replace"
            )

            metadata = Parser().parsestr(metadata_text)

            metadata_name = metadata.get("Name")
            metadata_version = metadata.get("Version")

            if not metadata_name or not metadata_version:
                raise ValueError(f"{path.name}: METADATA is missing Name or Version.")

            if canonicalize_name(metadata_name) != canonicalize_name(distribution):
                raise ValueError(f"{path.name}: METADATA name does not match filename.")

            if metadata_version != str(version):
                # Version normalization can make equivalent spellings differ.
                from packaging.version import Version

                if Version(metadata_version) != version:
                    raise ValueError(
                        f"{path.name}: METADATA version does not match filename."
                    )

    except (OSError, zipfile.BadZipFile, UnicodeDecodeError) as exc:
        raise ValueError(f"Cannot inspect wheel {path.name}: {exc}") from exc

    return {
        "filename": path.name,
        "distribution": str(distribution),
        "canonical_distribution": canonicalize_name(distribution),
        "version": str(version),
        "build": list(build) if build else None,
        "tags": sorted(str(tag) for tag in tags),
        "size": path.stat().st_size,
        "sha256": sha256_file(path),
    }


def validate_verification_coverage(
    report: dict[str, Any],
    wheel_records: list[dict[str, Any]],
) -> None:
    """
    Ensure every wheel being packaged was present and valid in the
    supplied verification report.
    """

    report_wheels = report.get("wheels")

    if not isinstance(report_wheels, list):
        raise ValueError("Verification report has no valid 'wheels' list.")

    valid_names = {
        item.get("file")
        for item in report_wheels
        if isinstance(item, dict) and item.get("valid") is True
    }

    missing_from_report = [
        item["filename"]
        for item in wheel_records
        if item["filename"] not in valid_names
    ]

    if missing_from_report:
        raise ValueError(
            "These bundle wheels were not verified successfully: "
            + ", ".join(missing_from_report)
        )


def zip_write_bytes(
    archive: zipfile.ZipFile,
    name: str,
    content: bytes,
) -> None:
    info = zipfile.ZipInfo(name, date_time=ZIP_TIMESTAMP)
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = 0o100644 << 16
    info.create_system = 3

    archive.writestr(info, content)


def zip_write_file(
    archive: zipfile.ZipFile,
    path: Path,
    archive_name: str,
) -> None:
    info = zipfile.ZipInfo(archive_name, date_time=ZIP_TIMESTAMP)
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = 0o100644 << 16
    info.create_system = 3

    with path.open("rb") as source:
        archive.writestr(info, source.read())


def create_bundle(
    *,
    wheels: list[Path],
    output: Path,
    project: dict[str, str],
    verification_report: dict[str, Any] | None,
) -> dict[str, Any]:
    records = [inspect_wheel(path) for path in wheels]

    if verification_report is not None:
        validate_verification_coverage(
            verification_report,
            records,
        )

    manifest = {
        "schema_version": BUNDLE_SCHEMA_VERSION,
        "project": {
            "name": project["name"],
            "version": project["version"],
        },
        "bundle": {
            "format": "zip",
            "wheel_count": len(records),
            "verification_used": verification_report is not None,
        },
        "wheels": records,
    }

    manifest_bytes = (
        json.dumps(
            manifest,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")

    checksum_lines = [
        f"{record['sha256']}  wheels/{record['filename']}" for record in records
    ]

    checksum_bytes = ("\n".join(checksum_lines) + "\n").encode("utf-8")

    output.parent.mkdir(parents=True, exist_ok=True)

    temporary_output = output.with_name(output.name + ".tmp")

    try:
        with zipfile.ZipFile(
            temporary_output,
            mode="w",
            compression=zipfile.ZIP_DEFLATED,
            compresslevel=9,
        ) as archive:
            zip_write_bytes(
                archive,
                "manifest.json",
                manifest_bytes,
            )

            zip_write_bytes(
                archive,
                "SHA256SUMS.txt",
                checksum_bytes,
            )

            for wheel in wheels:
                zip_write_file(
                    archive,
                    wheel,
                    f"wheels/{wheel.name}",
                )

        # Verify the completed ZIP before replacing the destination.
        with zipfile.ZipFile(temporary_output, "r") as archive:
            bad_member = archive.testzip()

            if bad_member:
                raise ValueError(f"Generated bundle is corrupt: {bad_member}")

            required_files = {
                "manifest.json",
                "SHA256SUMS.txt",
            }

            missing = required_files.difference(archive.namelist())

            if missing:
                raise ValueError(
                    "Generated bundle is missing: " + ", ".join(sorted(missing))
                )

        os.replace(temporary_output, output)

    finally:
        if temporary_output.exists():
            temporary_output.unlink()

    return {
        "output": str(output),
        "project": project["name"],
        "version": project["version"],
        "wheel_count": len(records),
        "size": output.stat().st_size,
        "sha256": sha256_file(output),
        "verification_used": verification_report is not None,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Create an Open News dependency-wheel bundle."
    )

    parser.add_argument(
        "--wheel-dir",
        type=Path,
        default=Path("dist"),
        help="Directory containing dependency wheels.",
    )

    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output ZIP path. Defaults to a versioned bundle filename.",
    )

    parser.add_argument(
        "--project-file",
        type=Path,
        default=Path("pyproject.toml"),
        help="Open News pyproject.toml file.",
    )

    parser.add_argument(
        "--verification-report",
        type=Path,
        default=None,
        help="Optional wheel-verification.json report.",
    )

    args = parser.parse_args()

    try:
        project = read_project_metadata(args.project_file)

        output = args.output or Path(
            f"dependency-build/"
            f"{project['canonical_name']}-dependencies-"
            f"{project['version']}.zip"
        )

        verification_report = None

        if args.verification_report:
            verification_report = load_verification_report(args.verification_report)

        wheels = discover_wheels(args.wheel_dir)

        result = create_bundle(
            wheels=wheels,
            output=output,
            project=project,
            verification_report=verification_report,
        )

        print("Dependency bundle created successfully.")
        print(f"  Project: {result['project']}")
        print(f"  Version: {result['version']}")
        print(f"  Wheels: {result['wheel_count']}")
        print(f"  Size: {result['size']} bytes")
        print(f"  SHA-256: {result['sha256']}")
        print(f"  Verification: {result['verification_used']}")
        print(f"  Output: {result['output']}")

        return 0

    except (ValueError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
