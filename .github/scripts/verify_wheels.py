#!/usr/bin/env python3
"""Verify dependency wheels against wheel-build-plan.json."""

from __future__ import annotations

import argparse
import base64
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
        required = ("package", "version", "target", "py_tags", "cibw_archs")
        missing = [key for key in required if key not in build]
        if missing:
            raise ValueError(
                f"Build entry {index} is missing fields: {', '.join(missing)}"
            )
        if not isinstance(build["py_tags"], list) or not build["py_tags"]:
            raise ValueError(f"Build entry {index} has an invalid py_tags field.")
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
    names = {info.filename for info in archive.infolist() if not info.is_dir()}
    record_files = [n for n in names if n.endswith(".dist-info/RECORD")]
    if len(record_files) != 1:
        return [f"Expected exactly one .dist-info/RECORD; found {len(record_files)}."]
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
                errors.append(f"Missing hash for non-RECORD file: {filename}")
            continue
        try:
            algorithm, expected_hash = hash_value.split("=", 1)
            digest = hashlib.new(algorithm)
            digest.update(archive.read(filename))
            actual_encoded = (
                base64.urlsafe_b64encode(digest.digest()).rstrip(b"=").decode("ascii")
            )
            if actual_encoded != expected_hash:
                errors.append(f"RECORD hash mismatch: {filename}")
        except (ValueError, KeyError) as exc:
            errors.append(f"Invalid RECORD hash for {filename}: {exc}")
            continue
        if size_value:
            try:
                if len(archive.read(filename)) != int(size_value):
                    errors.append(f"RECORD size mismatch: {filename}")
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
    result["tags"] = sorted(str(t) for t in tags)

    try:
        with zipfile.ZipFile(path) as archive:
            bad_member = archive.testzip()
            if bad_member:
                result["errors"].append(f"Corrupt ZIP member: {bad_member}")
            names = archive.namelist()
            for name in names:
                if not safe_archive_path(name):
                    result["errors"].append(f"Unsafe archive path: {name}")

            metadata_files = [n for n in names if n.endswith(".dist-info/METADATA")]
            wheel_files = [n for n in names if n.endswith(".dist-info/WHEEL")]

            if len(metadata_files) != 1:
                result["errors"].append(
                    "Expected exactly one .dist-info/METADATA file."
                )
            else:
                metadata_text = archive.read(metadata_files[0]).decode(
                    "utf-8", errors="replace"
                )
                metadata = Parser().parsestr(metadata_text)
                metadata_name = metadata.get("Name")
                metadata_version = metadata.get("Version")
                if not metadata_name:
                    result["errors"].append("METADATA has no Name field.")
                elif canonicalize_name(metadata_name) != result["package"]:
                    result["errors"].append(
                        "METADATA package name does not match filename."
                    )
                if not metadata_version:
                    result["errors"].append("METADATA has no Version field.")
                else:
                    try:
                        if Version(metadata_version) != version:
                            result["errors"].append(
                                "METADATA version does not match filename."
                            )
                    except InvalidVersion:
                        result["errors"].append("METADATA contains an invalid version.")

            if len(wheel_files) != 1:
                result["errors"].append("Expected exactly one .dist-info/WHEEL file.")
            else:
                wheel_text = archive.read(wheel_files[0]).decode(
                    "utf-8", errors="replace"
                )
                wm = Parser().parsestr(wheel_text)
                internal_tags = set(wm.get_all("Tag", []))
                filename_tags = {str(t) for t in tags}
                if not internal_tags:
                    result["errors"].append("WHEEL metadata has no Tag fields.")
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
    if requested == "py3":
        return (
            wheel_tag.interpreter in ("py3", "py2.py3")
            and wheel_tag.abi == "none"
            and wheel_tag.platform == "any"
        )
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
            return int(match.group(1)) <= int(requested[2:])
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


_MANYLINUX_RE = re.compile(r"^manylinux_(\d+)_(\d+)_")
_MANYLINUX_LEGACY = {
    "manylinux2014": (2, 17),
    "manylinux2010": (2, 12),
    "manylinux1": (2, 5),
}
_MUSLLINUX_RE = re.compile(r"^musllinux_(\d+)_(\d+)_")
_MACOSX_RE = re.compile(r"^macosx_(\d+)_(\d+)_")
_ANDROID_RE = re.compile(r"^android_(\d+)_")


def parse_manylinux_tag(platform: str) -> tuple[int, int] | None:
    match = _MANYLINUX_RE.match(platform)
    if match:
        return int(match.group(1)), int(match.group(2))
    for prefix, version in _MANYLINUX_LEGACY.items():
        if platform.startswith(f"{prefix}_"):
            return version
    return None


def parse_musllinux_tag(platform: str) -> tuple[int, int] | None:
    match = _MUSLLINUX_RE.match(platform)
    return (int(match.group(1)), int(match.group(2))) if match else None


def parse_macos_tag(platform: str) -> tuple[int, int] | None:
    match = _MACOSX_RE.match(platform)
    return (int(match.group(1)), int(match.group(2))) if match else None


def parse_android_tag(platform: str) -> int | None:
    match = _ANDROID_RE.match(platform)
    return int(match.group(1)) if match else None


def platform_tag_matches(
    wheel_tag: Any,
    target: str,
    archs: str | list[str],
    floor: dict | None,
) -> bool:
    platform = wheel_tag.platform.lower()
    target = target.lower()

    if platform == "any":
        return True

    if isinstance(archs, str):
        expected_archs = [
            i.strip() for i in archs.replace(",", " ").split() if i.strip()
        ]
    else:
        expected_archs = [str(i) for i in archs]
    expected = {normalize_arch(i) for i in expected_archs}
    if not expected:
        return False

    floor = floor or {}
    floor_type = floor.get("type")

    if target == "pure_python":
        return platform == "any"

    if target.startswith("android"):
        if "android_" not in platform:
            return False
        api = parse_android_tag(platform)
        if api is None:
            return False
        target_api = floor.get("api_level")
        if target_api is not None and api > int(target_api):
            return False
        return any(
            arch in platform
            for arch in ("arm64_v8a", "armeabi_v7a", "x86_64", "x86")
            if normalize_arch(arch) in expected
        )

    if target.startswith("manylinux"):
        if "manylinux" not in platform:
            return False
        if floor_type == "glibc":
            version = parse_manylinux_tag(platform)
            if version is None:
                return False
            if version > (int(floor.get("major", 2)), int(floor.get("minor", 0))):
                return False

    elif target.startswith("musllinux"):
        if "musllinux" not in platform:
            return False
        if floor_type == "musl":
            version = parse_musllinux_tag(platform)
            if version is None:
                return False
            if version > (int(floor.get("major", 1)), int(floor.get("minor", 0))):
                return False

    elif target.startswith("macos"):
        if "macosx" not in platform:
            return False
        if floor_type == "macos":
            version = parse_macos_tag(platform)
            if version is None:
                return False
            if version > (int(floor.get("major", 0)), int(floor.get("minor", 0))):
                return False

    elif target.startswith("win"):
        if not platform.startswith("win_"):
            return False

    else:
        if target not in platform:
            return False

    if "universal2" in platform:
        return expected.issubset({"x86_64", "arm64"})

    platform_arches = {
        "x86_64": "x86_64" in platform,
        "arm64": ("arm64" in platform or "aarch64" in platform),
        "x86": ("i686" in platform or platform.endswith("_x86")),
    }
    return any(platform_arches.get(arch, arch in platform) for arch in expected)


def wheel_matches_build(
    wheel: dict[str, Any],
    build: dict[str, Any],
    requested_python: str,
) -> bool:
    if not wheel["valid"]:
        return False
    if wheel["package"] != canonicalize_name(build["package"]):
        return False
    expected_version = build["version"]
    if build.get("build_type") == "prebuilt":
        expected_version = build.get("shipped_version")
        if not expected_version or wheel["file"] != build.get("prebuilt_filename"):
            return False
    try:
        if Version(wheel["version"]) != Version(str(expected_version)):
            return False
    except InvalidVersion:
        return False
    try:
        _distribution, _version, _build, tags = parse_wheel_filename(wheel["file"])
    except Exception:
        return False

    floor = build.get("platform_floor")
    for tag in tags:
        if not python_tag_matches(tag, requested_python):
            continue
        if platform_tag_matches(tag, str(build["target"]), build["cibw_archs"], floor):
            return True
    return False


def verify_plan(
    builds: list[dict[str, Any]],
    wheels: list[dict[str, Any]],
) -> dict[str, Any]:
    results, missing, expected_risks = [], [], []
    matched_files: set[str] = set()

    for build in builds:
        package = canonicalize_name(str(build["package"]))
        version = str(build["version"])
        target = str(build["target"])
        confidence = build.get("confidence", "high")

        for py_tag in build["py_tags"]:
            matching = [w for w in wheels if wheel_matches_build(w, build, str(py_tag))]
            for wheel in matching:
                matched_files.add(wheel["file"])

            entry = {
                "package": package,
                "version": version,
                "target": target,
                "python": str(py_tag),
                "confidence": confidence,
                "wheels": [w["file"] for w in matching],
            }

            # ─── ANDROID DEMOTION ───
            # Android cross-compile is inherently uncertain; a failed
            # build on Android with medium confidence should not block
            # the bundle. Low confidence already demotes below.
            is_android = target.startswith("android")
            if matching:
                entry["status"] = "verified"
            elif confidence == "low":
                entry["status"] = "expected_risk"
                expected_risks.append(entry)
            elif is_android and confidence == "medium":
                entry["status"] = "expected_risk"
                expected_risks.append(entry)
            else:
                entry["status"] = "missing"
                missing.append(entry)

            results.append(entry)

    invalid_wheels = [w for w in wheels if not w["valid"]]
    unmatched_wheels = [
        w["file"] for w in wheels if w["valid"] and w["file"] not in matched_files
    ]

    return {
        "success": not missing and not invalid_wheels,
        "summary": {
            "planned_combinations": len(results),
            "verified_combinations": sum(
                1 for r in results if r["status"] == "verified"
            ),
            "missing_combinations": len(missing),
            "expected_risk_combinations": len(expected_risks),
            "wheel_files": len(wheels),
            "invalid_wheels": len(invalid_wheels),
            "unmatched_wheels": len(unmatched_wheels),
        },
        "combinations": results,
        "missing": missing,
        "expected_risks": expected_risks,
        "invalid_wheels": invalid_wheels,
        "unmatched_wheels": unmatched_wheels,
        "wheels": wheels,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--wheel-dir", type=Path, default=Path("dist"))
    parser.add_argument("--plan", type=Path, default=Path("wheel-build-plan.json"))
    parser.add_argument("--output", type=Path, default=Path("wheel-verification.json"))
    parser.add_argument("--allow-unmatched", action="store_true")
    args = parser.parse_args()

    try:
        builds = load_plan(args.plan)
        if not args.wheel_dir.is_dir():
            raise ValueError(f"Wheel directory does not exist: {args.wheel_dir}")
        wheel_paths = sorted(args.wheel_dir.glob("*.whl"))
        wheels = [verify_archive(path) for path in wheel_paths]
        report = verify_plan(builds, wheels)

        if args.allow_unmatched:
            report["success"] = not report["missing"] and not report["invalid_wheels"]

        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )

        s = report["summary"]
        print(f"Planned combinations: {s['planned_combinations']}")
        print(f"Verified combinations: {s['verified_combinations']}")
        print(f"Missing combinations: {s['missing_combinations']}")
        print(
            f"Expected risk (low confidence / Android medium): {s['expected_risk_combinations']}"
        )
        print(f"Invalid wheels: {s['invalid_wheels']}")
        print(f"Unmatched wheels: {s['unmatched_wheels']}")

        if report["missing"]:
            print("\nMissing combinations:")
            for item in report["missing"]:
                print(
                    f"  - {item['package']}=={item['version']} "
                    f"{item['target']} {item['python']}"
                )
        if report["expected_risks"]:
            print("\nExpected-risk combinations:")
            for item in report["expected_risks"]:
                print(
                    f"  - {item['package']}=={item['version']} "
                    f"{item['target']} {item['python']} ({item['confidence']})"
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
