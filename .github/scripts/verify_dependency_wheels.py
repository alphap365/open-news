
#!/usr/bin/env python3
"""
Verify dependency wheels against wheel-build-plan.json.

Checks:
- Wheel filename and package/version identity.
- Python and platform compatibility with each planned build.
- Internal METADATA and WHEEL metadata.
- ZIP archive path safety.
- RECORD file hashes and sizes.
- Missing planned package/Python combinations.

Usage:
    python .github/scripts/verify_dependency_wheels.py \
        --wheel-dir dist \
        --plan wheel-build-plan.json \
        --output wheel-verification.json

Exit code:
    0: all planned combinations verified
    1: verification errors or missing wheels
    2: invalid input or configuration
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import re
import sys
import zipfile

from email.parser import Parser
from pathlib import Path, PurePosixPath
from typing import Any

from packaging.utils import canonicalize_name, parse_wheel_filename
from packaging.version import InvalidVersion, Version


def load_json(path: Path) -> Any:
    try:
        with path.open("r", encoding="utf-8") as file:
            return json.load(file)
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Cannot read JSON file {path}: {exc}") from exc


def load_plan(path: Path) -> list[dict[str, Any]]:
    data = load_json(path)

    if isinstance(data, list):
        builds = data
    elif isinstance(data, dict):
        builds = data.get("builds", data.get("matrix", []))
    else:
        raise ValueError("Build plan must be a JSON list or object.")

    if not isinstance(builds, list):
        raise ValueError("Build plan's builds field must be a list.")

    for index, build in enumerate(builds):
        if not isinstance(build, dict):
            raise ValueError(f"Build entry {index} must be an object.")

        required = (
            "package",
            "version",
            "target",
            "py_tags",
            "cibw_archs",
        )

        missing = [key for key in required if key not in build]
        if missing:
            raise ValueError(
                f"Build entry {index} is missing fields: {', '.join(missing)}"
            )

        if not isinstance(build["py_tags"], list) or not build["py_tags"]:
            raise ValueError(
                f"Build entry {index} has an invalid py_tags field."
            )

    return builds


def safe_archive_path(name: str) -> bool:
    path = PurePosixPath(name)

    if path.is_absolute():
        return False

    if ".." in path.parts:
        return False

    if re.match(r"^[A-Za-z]:", name):
        return False

    return True


def verify_record(archive: zipfile.ZipFile) -> list[str]:
    errors: list[str] = []

    names = set(archive.namelist())
    record_files = [
        name for name in names
        if name.endswith(".dist-info/RECORD")
    ]

    if len(record_files) != 1:
        return [
            f"Expected exactly one .dist-info/RECORD; found {len(record_files)}."
        ]

    record_name = record_files[0]

    try:
        content = archive.read(record_name).decode("utf-8")
        rows = list(csv.reader(io.StringIO(content)))
    except (KeyError, UnicodeDecodeError, csv.Error) as exc:
        return [f"Cannot read RECORD: {exc}"]

    recorded: set[str] = set()

    for row in rows:
        if len(row) != 3:
            errors.append(f"Invalid RECORD row: {row!r}")
            continue

        filename, hash_value, size_value = row
        recorded.add(filename)

        if filename not in names:
            errors.append(f"RECORD references missing file: {filename}")
            continue

        if not hash_value:
            if filename != record_name:
                errors.append(
                    f"Missing hash for non-RECORD file: {filename}"
                )
            continue

        try:
            algorithm, expected_hash = hash_value.split("=", 1)
            digest = hashlib.new(algorithm)
            digest.update(archive.read(filename))
            actual_hash = digest.digest()

            import base64
            actual_encoded = (
                base64.urlsafe_b64encode(actual_hash)
                .rstrip(b"=")
                .decode("ascii")
            )

            if actual_encoded != expected_hash:
                errors.append(f"RECORD hash mismatch: {filename}")

        except (ValueError, KeyError) as exc:
            errors.append(f"Invalid RECORD hash for {filename}: {exc}")
            continue

        if size_value:
            try:
                actual_size = len(archive.read(filename))
                if actual_size != int(size_value):
                    errors.append(
                        f"RECORD size mismatch: {filename}"
                    )
            except ValueError:
                errors.append(f"Invalid RECORD size for {filename}")

    for name in names:
        if name not in recorded:
            errors.append(f"File missing from RECORD: {name}")

    return errors


def verify_archive(path: Path) -> dict[str, Any]:
    result: dict[str, Any] = {
        "file": path.name,
        "valid": False,
        "errors": [],
        "package": None,
        "version": None,
        "tags": [],
    }

    try:
        distribution, version, _build, tags = parse_wheel_filename(path.name)
    except Exception as exc:
        result["errors"].append(f"Invalid wheel filename: {exc}")
        return result

    result["package"] = canonicalize_name(distribution)
    result["version"] = str(version)
    result["tags"] = sorted(str(tag) for tag in tags)

    try:
        with zipfile.ZipFile(path) as archive:
            bad_member = archive.testzip()

            if bad_member:
                result["errors"].append(
                    f"Corrupt ZIP member: {bad_member}"
                )

            names = archive.namelist()

            for name in names:
                if not safe_archive_path(name):
                    result["errors"].append(
                        f"Unsafe archive path: {name}"
                    )

            metadata_files = [
                name for name in names
                if name.endswith(".dist-info/METADATA")
            ]
            wheel_files = [
                name for name in names
                if name.endswith(".dist-info/WHEEL")
            ]

            if len(metadata_files) != 1:
                result["errors"].append(
                    "Expected exactly one .dist-info/METADATA file."
                )
            else:
                metadata_text = archive.read(
                    metadata_files[0]
                ).decode("utf-8", errors="replace")
                metadata = Parser().parsestr(metadata_text)

                metadata_name = metadata.get("Name")
                metadata_version = metadata.get("Version")

                if not metadata_name:
                    result["errors"].append(
                        "METADATA has no Name field."
                    )
                elif canonicalize_name(metadata_name) != result["package"]:
                    result["errors"].append(
                        "METADATA package name does not match filename."
                    )

                if not metadata_version:
                    result["errors"].append(
                        "METADATA has no Version field."
                    )
                else:
                    try:
                        if Version(metadata_version) != version:
                            result["errors"].append(
                                "METADATA version does not match filename."
                            )
                    except InvalidVersion:
                        result["errors"].append(
                            "METADATA contains an invalid version."
                        )

            if len(wheel_files) != 1:
                result["errors"].append(
                    "Expected exactly one .dist-info/WHEEL file."
                )
            else:
                wheel_text = archive.read(
                    wheel_files[0]
                ).decode("utf-8", errors="replace")
                wheel_metadata = Parser().parsestr(wheel_text)

                internal_tags = set(wheel_metadata.get_all("Tag", []))
                filename_tags = {str(tag) for tag in tags}

                if not internal_tags:
                    result["errors"].append(
                        "WHEEL metadata has no Tag fields."
                    )
                elif internal_tags != filename_tags:
                    result["errors"].append(
                        "WHEEL metadata tags do not match filename tags."
                    )

            result["errors"].extend(verify_record(archive))

    except (OSError, zipfile.BadZipFile, RuntimeError) as exc:
        result["errors"].append(f"Cannot inspect wheel archive: {exc}")

    result["valid"] = not result["errors"]
    return result


def python_tag_matches(wheel_tag: Any, requested: str) -> bool:
    """
    Check whether a wheel Python tag can satisfy a planned CPython version.

    Supports:
    - Exact CPython tags, e.g. cp313.
    - abi3 wheels built for an earlier CPython version.
    - Pure Python py3-none-any wheels.
    """

    if not re.fullmatch(r"cp3\d{2}", requested):
        return False

    if wheel_tag.interpreter == requested:
        return True

    if (
        wheel_tag.interpreter == "py3"
        and wheel_tag.abi == "none"
        and wheel_tag.platform == "any"
    ):
        return True

    if wheel_tag.abi == "abi3":
        match = re.fullmatch(r"cp3(\d{2})", wheel_tag.interpreter)

        if match:
            wheel_minor = int(match.group(1))
            requested_minor = int(requested[2:])

            return wheel_minor <= requested_minor

    return False


def normalize_arch(value: str) -> str:
    value = value.lower().strip()

    aliases = {
        "aarch64": "arm64",
        "arm64_v8a": "arm64",
        "arm64-v8a": "arm64",
        "x86_64": "x86_64",
        "amd64": "x86_64",
        "x64": "x86_64",
        "i686": "x86",
        "i386": "x86",
        "x86": "x86",
    }

    return aliases.get(value, value)


def platform_tag_matches(
    wheel_tag: Any,
    target: str,
    archs: str | list[str],
) -> bool:
    platform = wheel_tag.platform.lower()
    target = target.lower()

    if isinstance(archs, str):
        expected_archs = [
            item.strip()
            for item in archs.replace(",", " ").split()
            if item.strip()
        ]
    else:
        expected_archs = [str(item) for item in archs]

    expected = {normalize_arch(item) for item in expected_archs}

    if not expected:
        return False

    if target.startswith("android"):
        if "android_" not in platform:
            return False

        return any(
            arch in platform
            for arch in ("arm64_v8a", "armeabi_v7a", "x86_64", "x86")
            if normalize_arch(arch) in expected
        )

    if target.startswith("manylinux"):
        if "manylinux" not in platform:
            return False

    elif target.startswith("musllinux"):
        if "musllinux" not in platform:
            return False

    elif target.startswith("macos"):
        if "macosx" not in platform:
            return False

    elif target.startswith("win"):
        if not platform.startswith("win_"):
            return False

    else:
        # Generic targets must still match their requested architecture.
        if target not in platform:
            return False

    if "universal2" in platform:
        return expected.issubset({"x86_64", "arm64"})

    platform_arches = {
        "x86_64": "x86_64" in platform,
        "arm64": (
            "arm64" in platform
            or "aarch64" in platform
        ),
        "x86": (
            "i686" in platform
            or platform.endswith("_x86")
        ),
    }

    return any(
        platform_arches.get(arch, arch in platform)
        for arch in expected
    )


def wheel_matches_build(
    wheel: dict[str, Any],
    build: dict[str, Any],
    requested_python: str,
) -> bool:
    if not wheel["valid"]:
        return False

    if wheel["package"] != canonicalize_name(build["package"]):
        return False

    try:
        if Version(wheel["version"]) != Version(str(build["version"])):
            return False
    except InvalidVersion:
        return False

    try:
        _distribution, _version, _build, tags = parse_wheel_filename(
            wheel["file"]
        )
    except Exception:
        return False

    for tag in tags:
        if not python_tag_matches(tag, requested_python):
            continue

        if platform_tag_matches(
            tag,
            str(build["target"]),
            build["cibw_archs"],
        ):
            return True

    return False


def verify_plan(
    builds: list[dict[str, Any]],
    wheels: list[dict[str, Any]],
) -> dict[str, Any]:
    results = []
    missing = []
    matched_files: set[str] = set()

    for build in builds:
        package = canonicalize_name(str(build["package"]))
        version = str(build["version"])
        target = str(build["target"])

        for py_tag in build["py_tags"]:
            requested_python = str(py_tag)

            matching = [
                wheel
                for wheel in wheels
                if wheel_matches_build(
                    wheel,
                    build,
                    requested_python,
                )
            ]

            for wheel in matching:
                matched_files.add(wheel["file"])

            entry = {
                "package": package,
                "version": version,
                "target": target,
                "python": requested_python,
                "status": "verified" if matching else "missing",
                "wheels": [wheel["file"] for wheel in matching],
            }

            results.append(entry)

            if not matching:
                missing.append(entry)

    invalid_wheels = [
        wheel for wheel in wheels if not wheel["valid"]
    ]

    unmatched_wheels = [
        wheel["file"]
        for wheel in wheels
        if wheel["valid"] and wheel["file"] not in matched_files
    ]

    return {
        "success": not missing and not invalid_wheels,
        "summary": {
            "planned_combinations": len(results),
            "verified_combinations": len(results) - len(missing),
            "missing_combinations": len(missing),
            "wheel_files": len(wheels),
            "invalid_wheels": len(invalid_wheels),
            "unmatched_wheels": len(unmatched_wheels),
        },
        "combinations": results,
        "missing": missing,
        "invalid_wheels": invalid_wheels,
        "unmatched_wheels": unmatched_wheels,
        "wheels": wheels,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify built dependency wheels against a build plan."
    )

    parser.add_argument(
        "--wheel-dir",
        type=Path,
        default=Path("dist"),
        help="Directory containing built wheels (default: dist).",
    )
    parser.add_argument(
        "--plan",
        type=Path,
        default=Path("wheel-build-plan.json"),
        help="Build plan JSON file.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("wheel-verification.json"),
        help="Verification report output path.",
    )
    parser.add_argument(
        "--allow-unmatched",
        action="store_true",
        help="Do not fail solely because valid wheels match no planned build.",
    )

    args = parser.parse_args()

    try:
        builds = load_plan(args.plan)

        if not args.wheel_dir.is_dir():
            raise ValueError(
                f"Wheel directory does not exist: {args.wheel_dir}"
            )

        wheel_paths = sorted(args.wheel_dir.glob("*.whl"))

        wheels = [
            verify_archive(path)
            for path in wheel_paths
        ]

        report = verify_plan(builds, wheels)

        if args.allow_unmatched:
            report["success"] = (
                not report["missing"]
                and not report["invalid_wheels"]
            )

        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

        summary = report["summary"]

        print("Dependency wheel verification")
        print(f"  Planned combinations: {summary['planned_combinations']}")
        print(f"  Verified combinations: {summary['verified_combinations']}")
        print(f"  Missing combinations: {summary['missing_combinations']}")
        print(f"  Wheel files: {summary['wheel_files']}")
        print(f"  Invalid wheels: {summary['invalid_wheels']}")
        print(f"  Unmatched wheels: {summary['unmatched_wheels']}")
        print(f"  Report: {args.output}")

        if report["missing"]:
            print("\nMissing combinations:")
            for item in report["missing"]:
                print(
                    f"  - {item['package']}=={item['version']} "
                    f"{item['target']} {item['python']}"
                )

        if report["invalid_wheels"]:
            print("\nInvalid wheels:")
            for wheel in report["invalid_wheels"]:
                print(f"  - {wheel['file']}")
                for error in wheel["errors"]:
                    print(f"      {error}")

        if report["success"]:
            print("\nVerification passed.")
            return 0

        print("\nVerification failed.")
        return 1

    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
