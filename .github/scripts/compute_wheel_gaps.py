
#!/usr/bin/env python3
"""
Discover missing third-party dependency wheels for Open News.

Responsibilities:
- Read runtime dependencies from pyproject.toml and uv.lock.
- Evaluate dependency markers for each target environment.
- Query exact package releases on PyPI.
- Parse wheel filenames using packaging.
- Determine compatibility using Python, ABI and platform tags.
- Recognize abi3, macOS universal2 and Android API-level compatibility.
- Emit missing-wheel requests in the existing matrix format.
- Preserve GitHub Actions outputs: matrix and has_gaps.

The primary output remains a JSON list for plan_wheel_build.py.
A separate discovery report records available and unbuildable combinations.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from urllib.parse import quote

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib

import httpx

from packaging.markers import Marker
from packaging.requirements import Requirement
from packaging.specifiers import SpecifierSet
from packaging.tags import (
    android_platforms,
    compatible_tags,
    cpython_tags,
    mac_platforms,
)
from packaging.utils import (
    canonicalize_name,
    parse_wheel_filename,
)
from packaging.version import Version


# ---------------------------------------------------------------------------
# Target policy
# ---------------------------------------------------------------------------

PYTHON_VERSIONS = ("cp310", "cp311", "cp312", "cp313", "cp314")

# These are compatibility floors, not claims that every machine runs
# precisely this OS version.
#
# Keep these values aligned with the actual build images/configuration
# in build.yml.
#
# manylinux: glibc >= 2.17
# musllinux: musl >= 1.2
# macOS Intel: >= 10.9
# macOS ARM64: >= 11.0
# Android: API >= 24 (cibuildwheel's documented default)

BASE_TARGETS = [
    {
        "target": "manylinux_x86_64",
        "family": "manylinux",
        "architecture": "x86_64",
        "cibw_platform": "linux",
        "cibw_archs": "x86_64",
        "runner": "ubuntu-latest",
        "python_versions": PYTHON_VERSIONS,
        "build_pattern": "manylinux_*",
        "glibc_floor": (2, 17),
    },
    {
        "target": "manylinux_aarch64",
        "family": "manylinux",
        "architecture": "aarch64",
        "cibw_platform": "linux",
        "cibw_archs": "aarch64",
        "runner": "ubuntu-latest",
        "python_versions": PYTHON_VERSIONS,
        "build_pattern": "manylinux_*",
        "glibc_floor": (2, 17),
    },
    {
        "target": "musllinux_x86_64",
        "family": "musllinux",
        "architecture": "x86_64",
        "cibw_platform": "linux",
        "cibw_archs": "x86_64",
        "runner": "ubuntu-latest",
        "python_versions": PYTHON_VERSIONS,
        "build_pattern": "musllinux_*",
        "musl_floor": (1, 2),
    },
    {
        "target": "musllinux_aarch64",
        "family": "musllinux",
        "architecture": "aarch64",
        "cibw_platform": "linux",
        "cibw_archs": "aarch64",
        "runner": "ubuntu-latest",
        "python_versions": PYTHON_VERSIONS,
        "build_pattern": "musllinux_*",
        "musl_floor": (1, 2),
    },
    {
        "target": "macosx_arm64",
        "family": "macos",
        "architecture": "arm64",
        "cibw_platform": "macos",
        "cibw_archs": "arm64",
        "runner": "macos-latest",
        "python_versions": PYTHON_VERSIONS,
        "macos_floor": (11, 0),
    },
    {
        "target": "macosx_x86_64",
        "family": "macos",
        "architecture": "x86_64",
        "cibw_platform": "macos",
        "cibw_archs": "x86_64",
        "runner": "macos-latest",
        "python_versions": PYTHON_VERSIONS,
        "macos_floor": (10, 9),
    },
    {
        "target": "win_amd64",
        "family": "windows",
        "architecture": "AMD64",
        "cibw_platform": "windows",
        "cibw_archs": "AMD64",
        "runner": "windows-latest",
        "python_versions": PYTHON_VERSIONS,
    },
    {
        "target": "android_arm64_v8a",
        "family": "android",
        "architecture": "arm64_v8a",
        "cibw_platform": "android",
        "cibw_archs": "arm64_v8a",
        "runner": "ubuntu-latest",
        "python_versions": ("cp313", "cp314"),
    },
]


# ---------------------------------------------------------------------------
# General helpers
# ---------------------------------------------------------------------------

def log(message: str) -> None:
    print(f"[wheel-discovery] {message}", flush=True)


def load_toml(path: Path) -> dict:
    if not path.is_file():
        raise FileNotFoundError(f"Required file not found: {path}")

    with path.open("rb") as file:
        return tomllib.load(file)


def python_version_from_tag(py_tag: str) -> tuple[int, int]:
    if not py_tag.startswith("cp"):
        raise ValueError(f"Unsupported Python tag: {py_tag}")

    digits = py_tag[2:]

    if len(digits) != 3 or not digits.isdigit():
        raise ValueError(f"Invalid CPython tag: {py_tag}")

    return int(digits[0]), int(digits[1:])


def marker_matches(marker_text: str | None, environment: dict) -> bool:
    if not marker_text:
        return True

    try:
        return Marker(marker_text).evaluate(environment=environment)
    except Exception as exc:
        # Do not silently discard a dependency because its marker
        # could not be evaluated.
        log(f"WARNING: Cannot evaluate marker {marker_text!r}: {exc}")
        return True


def make_marker_environment(
    target: dict,
    py_tag: str,
) -> dict:
    major, minor = python_version_from_tag(py_tag)
    family = target["family"]
    architecture = target["architecture"]

    if family == "windows":
        sys_platform = "win32"
        platform_system = "Windows"
        os_name = "nt"
        platform_machine = "AMD64"

    elif family == "macos":
        sys_platform = "darwin"
        platform_system = "Darwin"
        os_name = "posix"
        platform_machine = architecture

    else:
        # Android's Python marker environment is Linux-like.
        sys_platform = "linux"
        platform_system = "Linux"
        os_name = "posix"

        if architecture == "arm64_v8a":
            platform_machine = "aarch64"
        else:
            platform_machine = architecture

    full_version = f"{major}.{minor}.0"

    return {
        "implementation_name": "cpython",
        "implementation_version": full_version,
        "os_name": os_name,
        "platform_machine": platform_machine,
        "platform_release": "0",
        "platform_system": platform_system,
        "platform_version": "0",
        "python_full_version": full_version,
        "python_version": f"{major}.{minor}",
        "sys_platform": sys_platform,
        "platform_python_implementation": "CPython",
        "extra": "",
    }


# ---------------------------------------------------------------------------
# Target compatibility tags
# ---------------------------------------------------------------------------

def manylinux_platform_tags(target: dict) -> list[str]:
    """
    Generate manylinux tags compatible with the configured glibc floor.

    The target floor is deliberately explicit. A wheel requiring a newer
    glibc version must not be treated as compatible with an older target.
    """
    architecture = target["architecture"]
    floor_major, floor_minor = target["glibc_floor"]

    if floor_major != 2:
        raise ValueError("Only glibc 2.x policies are currently supported.")

    result = [
        f"manylinux_2_{minor}_{architecture}"
        for minor in range(floor_minor, 4, -1)
    ]

    # Legacy aliases.
    if floor_minor <= 17:
        result.append(f"manylinux2014_{architecture}")

    if architecture == "x86_64":
        if floor_minor <= 12:
            result.append("manylinux2010_x86_64")
        if floor_minor <= 5:
            result.append("manylinux1_x86_64")

    return list(dict.fromkeys(result))


def musllinux_platform_tags(target: dict) -> list[str]:
    """
    Generate musllinux tags compatible with the configured musl floor.
    """
    architecture = target["architecture"]
    floor_major, floor_minor = target["musl_floor"]

    result = [
        f"musllinux_{floor_major}_{minor}_{architecture}"
        for minor in range(floor_minor, 0, -1)
    ]

    return result


def get_platform_tags(
    target: dict,
    android_api_level: int,
) -> list[str]:
    family = target["family"]
    architecture = target["architecture"]

    if family == "manylinux":
        return manylinux_platform_tags(target)

    if family == "musllinux":
        return musllinux_platform_tags(target)

    if family == "macos":
        return list(
            mac_platforms(
                version=target["macos_floor"],
                arch=architecture,
            )
        )

    if family == "windows":
        return ["win_amd64"]

    if family == "android":
        return list(
            android_platforms(
                api_level=android_api_level,
                abi=architecture,
            )
        )

    raise ValueError(f"Unknown target family: {family}")


def get_supported_tags(
    target: dict,
    py_tag: str,
    android_api_level: int,
) -> list:
    """
    Generate the tags accepted by one exact target/Python combination.

    cpython_tags handles exact CPython ABI and abi3 compatibility.
    compatible_tags adds generic Python and pure-Python compatibility.
    """
    python_version = python_version_from_tag(py_tag)
    platform_tags = get_platform_tags(target, android_api_level)

    ordered_tags = list(
        cpython_tags(
            python_version=python_version,
            abis=[py_tag],
            platforms=platform_tags,
        )
    )

    ordered_tags.extend(
        compatible_tags(
            python_version=python_version,
            interpreter=py_tag,
            platforms=platform_tags,
        )
    )

    # Preserve preference order while removing duplicates.
    return list(dict.fromkeys(ordered_tags))


# ---------------------------------------------------------------------------
# Runtime dependency graph from uv.lock
# ---------------------------------------------------------------------------

def version_satisfies(
    version_text: str,
    specifier_text: str | None,
) -> bool:
    if not specifier_text:
        return True

    try:
        return SpecifierSet(specifier_text).contains(
            Version(version_text),
            prereleases=True,
        )
    except Exception:
        return False


def package_identity(package: dict) -> tuple:
    return (
        canonicalize_name(package["name"]),
        package["version"],
        json.dumps(package.get("source", {}), sort_keys=True),
    )


def resolve_runtime_packages(
    project: dict,
    lock: dict,
    environment: dict,
) -> tuple[list[dict], list[str]]:
    """
    Walk the locked runtime dependency graph for one marker environment.

    Optional development groups are intentionally excluded.
    """
    lock_packages = lock.get("package", [])

    by_name: dict[str, list[dict]] = {}

    for package in lock_packages:
        name = package.get("name")
        version = package.get("version")

        if not name or not version:
            continue

        key = canonicalize_name(name)
        by_name.setdefault(key, []).append(package)

    stack: list[dict] = []
    warnings: list[str] = []

    for requirement_text in project.get("dependencies", []):
        try:
            requirement = Requirement(requirement_text)
        except Exception as exc:
            warnings.append(
                f"Invalid project dependency {requirement_text!r}: {exc}"
            )
            continue

        if requirement.marker and not requirement.marker.evaluate(
            environment=environment
        ):
            continue

        candidates = by_name.get(
            canonicalize_name(requirement.name),
            [],
        )

        matching = [
            package
            for package in candidates
            if version_satisfies(
                package["version"],
                str(requirement.specifier),
            )
        ]

        if not matching:
            warnings.append(
                f"No matching uv.lock entry for {requirement.name}"
            )
            continue

        stack.extend(matching)

    visited: set[tuple] = set()
    result: list[dict] = []

    while stack:
        package = stack.pop()
        identity = package_identity(package)

        if identity in visited:
            continue

        visited.add(identity)
        result.append(package)

        for dependency in package.get("dependencies", []):
            if not isinstance(dependency, dict):
                continue

            if not marker_matches(
                dependency.get("marker"),
                environment,
            ):
                continue

            dependency_name = dependency.get("name")

            if not dependency_name:
                continue

            candidates = by_name.get(
                canonicalize_name(dependency_name),
                [],
            )

            matching = [
                candidate
                for candidate in candidates
                if version_satisfies(
                    candidate["version"],
                    dependency.get("version"),
                )
            ]

            if not matching:
                warnings.append(
                    f"Unresolved locked dependency: "
                    f"{dependency_name} ({dependency.get('version', '')})"
                )
                continue

            stack.extend(matching)

    result.sort(
        key=lambda item: (
            canonicalize_name(item["name"]),
            item["version"],
        )
    )

    return result, warnings


# ---------------------------------------------------------------------------
# PyPI discovery
# ---------------------------------------------------------------------------

def fetch_pypi_release(
    client: httpx.Client,
    package: str,
    version: str,
    base_url: str,
    retries: int,
) -> dict | None:
    package_url = quote(package, safe="")
    version_url = quote(version, safe="")

    url = f"{base_url.rstrip('/')}/{package_url}/{version_url}/json"

    for attempt in range(retries + 1):
        try:
            response = client.get(url)

            if response.status_code == 404:
                return None

            if response.status_code == 429 or response.status_code >= 500:
                if attempt < retries:
                    delay = min(2 ** attempt, 10)
                    log(
                        f"PyPI returned HTTP {response.status_code}; "
                        f"retrying in {delay}s"
                    )
                    time.sleep(delay)
                    continue

            response.raise_for_status()
            return response.json()

        except httpx.HTTPError:
            if attempt >= retries:
                raise

            time.sleep(min(2 ** attempt, 10))

    return None


def inspect_release(
    package: str,
    version: str,
    release: dict | None,
    supported_tags: list,
) -> dict:
    if release is None:
        return {
            "status": "source_unavailable",
            "reason": "Exact package release was not found on PyPI.",
        }

    supported_tag_set = set(supported_tags)
    tag_rank = {
        tag: index
        for index, tag in enumerate(supported_tags)
    }

    compatible_wheels = []
    source_distributions = []

    for file_info in release.get("urls", []):
        filename = file_info.get("filename", "")
        file_type = file_info.get("packagetype", "")
        digests = file_info.get("digests") or {}

        if file_type == "bdist_wheel":
            try:
                wheel_name, wheel_version, _, wheel_tags = (
                    parse_wheel_filename(filename)
                )
            except Exception:
                continue

            if canonicalize_name(str(wheel_name)) != canonicalize_name(package):
                continue

            if wheel_version != Version(version):
                continue

            matching_tags = wheel_tags.intersection(supported_tag_set)

            if not matching_tags:
                continue

            ordered_matches = sorted(
                matching_tags,
                key=lambda tag: tag_rank[tag],
            )

            compatible_wheels.append({
                "filename": filename,
                "url": file_info.get("url"),
                "sha256": digests.get("sha256"),
                "best_matching_tag": str(ordered_matches[0]),
                "matching_tags": [
                    str(tag) for tag in ordered_matches
                ],
            })

        elif file_type == "sdist":
            source_distributions.append({
                "filename": filename,
                "url": file_info.get("url"),
                "sha256": digests.get("sha256"),
            })

    compatible_wheels.sort(
        key=lambda item: tag_rank.get(
            next(
                (
                    tag
                    for tag in supported_tags
                    if str(tag) == item["best_matching_tag"]
                ),
                None,
            ),
            len(tag_rank),
        )
    )

    if compatible_wheels:
        return {
            "status": "available",
            "compatible_wheels": compatible_wheels,
        }

    if source_distributions:
        # Prefer .tar.gz, then other supported source archive formats.
        source_distributions.sort(
            key=lambda item: (
                not item["filename"].endswith(".tar.gz"),
                item["filename"],
            )
        )

        return {
            "status": "build_required",
            "sdist": source_distributions[0],
        }

    return {
        "status": "source_unavailable",
        "reason": (
            "No compatible upstream wheel and no source distribution "
            "were found for this exact release."
        ),
    }


# ---------------------------------------------------------------------------
# Main discovery engine
# ---------------------------------------------------------------------------

def discover(
    project_path: Path,
    lock_path: Path,
    android_api_level: int,
    pypi_base_url: str,
    timeout: float,
    retries: int,
) -> tuple[list[dict], dict]:
    project_data = load_toml(project_path)
    lock_data = load_toml(lock_path)

    project = project_data.get("project", {})

    if not project:
        raise ValueError(
            f"No [project] table found in {project_path}"
        )

    project_name = project.get("name", "unknown-project")
    project_version = project.get("version", "unknown")

    targets = []

    for base_target in BASE_TARGETS:
        target = dict(base_target)

        if target["family"] == "android":
            target["android_api_level"] = android_api_level

        targets.append(target)

    gaps: list[dict] = []
    available: list[dict] = []
    unbuildable: list[dict] = []
    lock_warnings: list[dict] = []

    release_cache: dict[tuple[str, str], dict | None] = {}

    headers = {
        "User-Agent": "Open-News-Dependency-Wheel-Builder/1.1",
        "Accept": "application/json",
    }

    with httpx.Client(
        timeout=timeout,
        follow_redirects=True,
        headers=headers,
    ) as client:

        for target in targets:
            log(f"Target: {target['target']}")

            for py_tag in target["python_versions"]:
                environment = make_marker_environment(
                    target,
                    py_tag,
                )

                packages, warnings = resolve_runtime_packages(
                    project,
                    lock_data,
                    environment,
                )

                for warning in warnings:
                    lock_warnings.append({
                        "target": target["target"],
                        "py_tag": py_tag,
                        "warning": warning,
                    })

                supported_tags = get_supported_tags(
                    target,
                    py_tag,
                    android_api_level,
                )

                for package_info in packages:
                    package = package_info["name"]
                    version = package_info["version"]
                    normalized_name = canonicalize_name(package)

                    cache_key = (normalized_name, version)

                    if cache_key not in release_cache:
                        log(f"Checking PyPI: {package}=={version}")

                        release_cache[cache_key] = fetch_pypi_release(
                            client=client,
                            package=package,
                            version=version,
                            base_url=pypi_base_url,
                            retries=retries,
                        )

                    release = release_cache[cache_key]

                    result = inspect_release(
                        package=package,
                        version=version,
                        release=release,
                        supported_tags=supported_tags,
                    )

                    base_record = {
                        "package": package,
                        "version": version,
                        "target": target["target"],
                        "py_tag": py_tag,
                        "compatibility_profile": target["family"],
                    }

                    if target["family"] == "android":
                        base_record["android_api_level"] = android_api_level

                    if result["status"] == "available":
                        available.append({
                            **base_record,
                            "status": "available",
                            "source": "pypi",
                            "compatible_wheels": result[
                                "compatible_wheels"
                            ],
                        })
                        continue

                    if result["status"] == "source_unavailable":
                        unbuildable.append({
                            **base_record,
                            "status": "source_unavailable",
                            "reason": result["reason"],
                        })
                        continue

                    # Preserve the existing matrix fields expected by
                    # plan_wheel_build.py and build.yml.
                    if target["family"] in ("manylinux", "musllinux"):
                        cibw_build_id = (
                            f"{py_tag}-{target['build_pattern']}"
                        )
                    else:
                        cibw_build_id = f"{py_tag}-*"

                    sdist = result["sdist"]

                    gap = {
                        **base_record,
                        "cibw_platform": target["cibw_platform"],
                        "cibw_archs": target["cibw_archs"],
                        "cibw_build_id": cibw_build_id,
                        "runner": target["runner"],
                        "status": "build_required",
                        "source": "pypi_sdist",
                        "sdist_filename": sdist["filename"],
                        "sdist_url": sdist["url"],
                        "sdist_sha256": sdist["sha256"],
                    }

                    gaps.append(gap)

    gaps.sort(
        key=lambda item: (
            item["package"].lower(),
            item["target"],
            item["py_tag"],
        )
    )

    available.sort(
        key=lambda item: (
            item["package"].lower(),
            item["target"],
            item["py_tag"],
        )
    )

    unbuildable.sort(
        key=lambda item: (
            item["package"].lower(),
            item["target"],
            item["py_tag"],
        )
    )

    discovery_report = {
        "schema_version": 2,
        "project": project_name,
        "project_version": project_version,
        "android_api_level": android_api_level,
        "targets": [
            {
                "target": target["target"],
                "architecture": target["architecture"],
                "python_versions": list(target["python_versions"]),
                "runner": target["runner"],
            }
            for target in targets
        ],
        "summary": {
            "missing_wheel_count": len(gaps),
            "upstream_wheel_count": len(available),
            "source_unavailable_count": len(unbuildable),
            "lock_warning_count": len(lock_warnings),
        },
        "available": available,
        "gaps": gaps,
        "source_unavailable": unbuildable,
        "lock_warnings": lock_warnings,
    }

    return gaps, discovery_report


# ---------------------------------------------------------------------------
# GitHub Actions output
# ---------------------------------------------------------------------------

def write_github_outputs(
    gaps: list[dict],
    discovery_report: dict,
    discovery_path: Path,
) -> None:
    output_file = os.environ.get("GITHUB_OUTPUT")

    if not output_file:
        return

    matrix = {
        "include": gaps,
    }

    outputs = {
        "matrix": json.dumps(matrix, separators=(",", ":")),
        "has_gaps": "true" if gaps else "false",
        "gap_count": str(len(gaps)),
        "available_count": str(
            discovery_report["summary"]["upstream_wheel_count"]
        ),
        "unbuildable_count": str(
            discovery_report["summary"]["source_unavailable_count"]
        ),
        "discovery_file": str(discovery_path),
    }

    with open(output_file, "a", encoding="utf-8") as file:
        for key, value in outputs.items():
            file.write(f"{key}={value}\n")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Discover missing dependency wheels using PyPI metadata "
            "and Python packaging compatibility tags."
        )
    )

    parser.add_argument(
        "--project",
        type=Path,
        default=Path("pyproject.toml"),
    )

    parser.add_argument(
        "--lock",
        type=Path,
        default=Path("uv.lock"),
    )

    parser.add_argument(
        "--output",
        type=Path,
        default=Path("wheel-gaps.json"),
        help="Primary missing-wheel JSON output.",
    )

    parser.add_argument(
        "--discovery-output",
        type=Path,
        default=None,
        help="Full discovery report. Defaults beside --output.",
    )

    parser.add_argument(
        "--android-api-level",
        type=int,
        default=24,
        help="Minimum Android API level used for compatibility checks.",
    )

    parser.add_argument(
        "--pypi-base-url",
        default="https://pypi.org/pypi",
    )

    parser.add_argument(
        "--timeout",
        type=float,
        default=30.0,
    )

    parser.add_argument(
        "--retries",
        type=int,
        default=3,
    )

    return parser.parse_args()


def main() -> int:
    args = parse_args()

    if args.android_api_level < 16:
        print(
            "ERROR: Android API level must be at least 16.",
            file=sys.stderr,
        )
        return 2

    if args.retries < 0:
        print("ERROR: retries cannot be negative.", file=sys.stderr)
        return 2

    if args.discovery_output is None:
        args.discovery_output = args.output.with_name(
            f"{args.output.stem}-discovery.json"
        )

    try:
        gaps, discovery_report = discover(
            project_path=args.project,
            lock_path=args.lock,
            android_api_level=args.android_api_level,
            pypi_base_url=args.pypi_base_url,
            timeout=args.timeout,
            retries=args.retries,
        )

        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.discovery_output.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        # Keep this a JSON list: plan_wheel_build.py consumes it.
        args.output.write_text(
            json.dumps(gaps, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

        args.discovery_output.write_text(
            json.dumps(
                discovery_report,
                indent=2,
                sort_keys=True,
            ) + "\n",
            encoding="utf-8",
        )

        write_github_outputs(
            gaps,
            discovery_report,
            args.discovery_output,
        )

        summary = discovery_report["summary"]

        log("Discovery completed.")
        log(f"Missing wheel combinations: {summary['missing_wheel_count']}")
        log(f"Compatible upstream wheels: {summary['upstream_wheel_count']}")
        log(
            "Source unavailable: "
            f"{summary['source_unavailable_count']}"
        )
        log(f"Lock warnings: {summary['lock_warning_count']}")
        log(f"Gap report: {args.output}")
        log(f"Full report: {args.discovery_output}")

        return 0

    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
