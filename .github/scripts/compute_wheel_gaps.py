#!/usr/bin/env python3
"""Discover missing third-party dependency wheels for Open News."""

from __future__ import annotations

import argparse
import hashlib
import html as html_module
import json
import os
import re
import sys
import time
from pathlib import Path
from urllib.parse import quote, urljoin

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
from packaging.utils import canonicalize_name, parse_wheel_filename
from packaging.version import Version


PYTHON_VERSIONS = ("cp311", "cp312", "cp313", "cp314")
ANDROID_PYTHON_VERSIONS = ("cp313", "cp314")

NATIVE_PACKAGES = {
    "cryptography", "cffi", "lxml", "primp", "selectolax",
    "numpy", "pillow", "pyyaml", "ujson", "orjson",
    "pydantic-core", "regex", "uvloop", "httptools",
    "watchfiles", "pyzmq", "pandas", "psycopg2", "psycopg2-binary",
}

ANDROID_UNSUPPORTED_PACKAGES = {
    "cryptography", "cffi", "lxml", "primp", "selectolax",
}


# ---------------------------------------------------------------------------
# External wheel indexes
#
# Consulted only when PyPI has no compatible wheel for the target.
# First hit wins. Everything returned here is downloaded during
# discovery and shipped as a `prebuilt` gap.
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# External wheel indexes
#
# Consulted for any target when PyPI has no compatible wheel.
# `supports` restricts each index to the families / architectures it
# actually serves, so piwheels is never queried for win_arm64 and
# win_arm64-wheels is never queried for musllinux.
#
# Verify each `url_template` before deploying: some indexes serve
# PEP 503 under /simple/{package}/, others (Chaquopy) at the root.
# ---------------------------------------------------------------------------

EXTERNAL_INDEXES = [
    {
        "name": "chaquopy",
        "type": "simple_html",
        "url_template": "https://chaquo.com/pypi-13.1/{package}/",
        "supports": {"families": {"android"}},
    },
    {
        "name": "flet",
        "type": "simple_html",
        "url_template": "https://pypi.flet.dev/{package}/",
        "supports": {"families": {"android", "ios"}},
    },
    {
        "name": "anaconda_pyswift",
        "type": "anaconda_api",
        "url_template": "https://api.anaconda.org/package/PySwift/{package}",
        "supports": {"families": {"android"}},
    },
    {
        "name": "exotic_wheels",
        "type": "simple_html",
        "url_template": "https://exotic-wheels.github.io/simple/{package}/",
        "supports": {
            "families": {"musllinux"},
            "archs": {"armv7l", "aarch64", "ppc64le", "s390x", "riscv64"},
        },
    },
    {
        "name": "piwheels",
        "type": "simple_html",
        "url_template": "https://www.piwheels.org/simple/{package}/",
        "supports": {
            "families": {"manylinux"},
            "archs": {"armv7l", "armv6l"},
        },
    },
    {
        "name": "pytorch_cpu",
        "type": "simple_html",
        "url_template": "https://download.pytorch.org/whl/cpu/{package}/",
        "supports": {
            "families": {"manylinux", "musllinux", "windows", "macos"},
        },
    },
    {
        "name": "nvidia",
        "type": "simple_html",
        "url_template": "https://pypi.nvidia.com/{package}/",
        "supports": {"families": {"manylinux"}},
    },
    # GitHub-releases index (win_arm64-wheels) requires a dedicated
    # query type; add it when you start targeting win_arm64.
]

BASE_TARGETS = [
    {
        "target": "manylinux_x86_64", "family": "manylinux",
        "architecture": "x86_64", "cibw_platform": "linux",
        "cibw_archs": "x86_64", "runner": "ubuntu-latest",
        "python_versions": PYTHON_VERSIONS, "build_pattern": "manylinux_*",
        "glibc_floor": (2, 28),
        "platform_floor": {"type": "glibc", "major": 2, "minor": 28},
    },
    {
        "target": "manylinux_aarch64", "family": "manylinux",
        "architecture": "aarch64", "cibw_platform": "linux",
        "cibw_archs": "aarch64", "runner": "ubuntu-24.04-arm",
        "python_versions": PYTHON_VERSIONS, "build_pattern": "manylinux_*",
        "glibc_floor": (2, 28),
        "platform_floor": {"type": "glibc", "major": 2, "minor": 28},
    },
    {
        "target": "musllinux_x86_64", "family": "musllinux",
        "architecture": "x86_64", "cibw_platform": "linux",
        "cibw_archs": "x86_64", "runner": "ubuntu-latest",
        "python_versions": PYTHON_VERSIONS, "build_pattern": "musllinux_*",
        "musl_floor": (1, 2),
        "platform_floor": {"type": "musl", "major": 1, "minor": 2},
    },
    {
        "target": "musllinux_aarch64", "family": "musllinux",
        "architecture": "aarch64", "cibw_platform": "linux",
        "cibw_archs": "aarch64", "runner": "ubuntu-24.04-arm",
        "python_versions": PYTHON_VERSIONS, "build_pattern": "musllinux_*",
        "musl_floor": (1, 2),
        "platform_floor": {"type": "musl", "major": 1, "minor": 2},
    },
    {
        "target": "macosx_arm64", "family": "macos",
        "architecture": "arm64", "cibw_platform": "macos",
        "cibw_archs": "arm64", "runner": "macos-latest",
        "python_versions": PYTHON_VERSIONS, "macos_floor": (14, 0),
        "platform_floor": {"type": "macos", "major": 14, "minor": 0},
    },
    {
        "target": "win_amd64", "family": "windows",
        "architecture": "AMD64", "cibw_platform": "windows",
        "cibw_archs": "AMD64", "runner": "windows-latest",
        "python_versions": PYTHON_VERSIONS,
    },
    {
        "target": "android_arm64_v8a", "family": "android",
        "architecture": "arm64_v8a", "cibw_platform": "android",
        "cibw_archs": "arm64_v8a", "runner": "ubuntu-latest",
        "python_versions": ANDROID_PYTHON_VERSIONS,
    },
]


def log(message: str) -> None:
    print(f"[wheel-discovery] {message}", flush=True)


def load_toml(path: Path) -> dict:
    if not path.is_file():
        raise FileNotFoundError(f"Required file not found: {path}")
    with path.open("rb") as file:
        return tomllib.load(file)

def index_supports(index: dict, target: dict) -> bool:
    supports = index.get("supports", {})
    families = supports.get("families")
    archs = supports.get("archs")
    if families and target["family"] not in families:
        return False
    if archs and target["architecture"] not in archs:
        return False
    return True

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
        log(f"WARNING: Cannot evaluate marker {marker_text!r}: {exc}")
        return True


def make_marker_environment(target: dict, py_tag: str) -> dict:
    major, minor = python_version_from_tag(py_tag)
    family = target["family"]
    architecture = target["architecture"]

    if family == "windows":
        sys_platform, platform_system, os_name = "win32", "Windows", "nt"
        platform_machine = "AMD64"
    elif family == "macos":
        sys_platform, platform_system, os_name = "darwin", "Darwin", "posix"
        platform_machine = architecture
    elif family == "android":
        sys_platform, platform_system, os_name = "android", "Android", "posix"
        platform_machine = "aarch64"
    else:
        sys_platform, platform_system, os_name = "linux", "Linux", "posix"
        platform_machine = "aarch64" if architecture == "arm64_v8a" else architecture

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


def manylinux_platform_tags(target: dict) -> list[str]:
    architecture = target["architecture"]
    floor_major, floor_minor = target["glibc_floor"]
    if floor_major != 2:
        raise ValueError("Only glibc 2.x policies are currently supported.")
    result = [
        f"manylinux_2_{minor}_{architecture}"
        for minor in range(floor_minor, 4, -1)
    ]
    if floor_minor <= 17:
        result.append(f"manylinux2014_{architecture}")
    if architecture == "x86_64":
        if floor_minor <= 12:
            result.append("manylinux2010_x86_64")
        if floor_minor <= 5:
            result.append("manylinux1_x86_64")
    return list(dict.fromkeys(result))


def musllinux_platform_tags(target: dict) -> list[str]:
    architecture = target["architecture"]
    floor_major, floor_minor = target["musl_floor"]
    return [
        f"musllinux_{floor_major}_{minor}_{architecture}"
        for minor in range(floor_minor, 0, -1)
    ]


def get_platform_tags(target: dict, android_api_level: int) -> list[str]:
    family = target["family"]
    architecture = target["architecture"]
    if family == "manylinux":
        return manylinux_platform_tags(target)
    if family == "musllinux":
        return musllinux_platform_tags(target)
    if family == "macos":
        return list(mac_platforms(version=target["macos_floor"], arch=architecture))
    if family == "windows":
        return ["win_amd64"]
    if family == "android":
        return list(android_platforms(api_level=android_api_level, abi=architecture))
    raise ValueError(f"Unknown target family: {family}")


def get_supported_tags(target: dict, py_tag: str, android_api_level: int) -> list:
    python_version = python_version_from_tag(py_tag)
    platform_tags = get_platform_tags(target, android_api_level)
    ordered_tags = list(cpython_tags(
        python_version=python_version, abis=[py_tag], platforms=platform_tags,
    ))
    ordered_tags.extend(compatible_tags(
        python_version=python_version, interpreter=py_tag, platforms=platform_tags,
    ))
    return list(dict.fromkeys(ordered_tags))


def version_satisfies(version_text: str, specifier_text: str | None) -> bool:
    if not specifier_text:
        return True
    try:
        return SpecifierSet(specifier_text).contains(
            Version(version_text), prereleases=True,
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
    project: dict, lock: dict, environment: dict,
) -> tuple[list[dict], list[str]]:
    lock_packages = lock.get("package", [])
    by_name: dict[str, list[dict]] = {}
    for package in lock_packages:
        name = package.get("name")
        version = package.get("version")
        if not name or not version:
            continue
        by_name.setdefault(canonicalize_name(name), []).append(package)

    stack: list[dict] = []
    warnings: list[str] = []

    for requirement_text in project.get("dependencies", []):
        try:
            requirement = Requirement(requirement_text)
        except Exception as exc:
            warnings.append(f"Invalid project dependency {requirement_text!r}: {exc}")
            continue
        if requirement.marker and not requirement.marker.evaluate(environment=environment):
            continue
        candidates = by_name.get(canonicalize_name(requirement.name), [])
        matching = [
            p for p in candidates
            if version_satisfies(p["version"], str(requirement.specifier))
        ]
        if not matching:
            warnings.append(f"No matching uv.lock entry for {requirement.name}")
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
            if not marker_matches(dependency.get("marker"), environment):
                continue
            dependency_name = dependency.get("name")
            if not dependency_name:
                continue
            candidates = by_name.get(canonicalize_name(dependency_name), [])
            matching = [
                c for c in candidates
                if version_satisfies(c["version"], dependency.get("version"))
            ]
            if not matching:
                warnings.append(
                    f"Unresolved locked dependency: {dependency_name} "
                    f"({dependency.get('version', '')})"
                )
                continue
            stack.extend(matching)

    result.sort(key=lambda i: (canonicalize_name(i["name"]), i["version"]))
    return result, warnings


def fetch_pypi_release(
    client: httpx.Client, package: str, version: str,
    base_url: str, retries: int,
) -> dict | None:
    url = f"{base_url.rstrip('/')}/{quote(package, safe='')}/{quote(version, safe='')}/json"
    for attempt in range(retries + 1):
        try:
            response = client.get(url)
            if response.status_code == 404:
                return None
            if response.status_code == 429 or response.status_code >= 500:
                if attempt < retries:
                    time.sleep(min(2 ** attempt, 10))
                    continue
            response.raise_for_status()
            return response.json()
        except httpx.HTTPError:
            if attempt >= retries:
                raise
            time.sleep(min(2 ** attempt, 10))
    return None


def inspect_release(
    package: str, version: str, release: dict | None, supported_tags: list,
) -> dict:
    if release is None:
        return {"status": "source_unavailable",
                "reason": "Exact package release was not found on PyPI."}

    supported_tag_set = set(supported_tags)
    tag_rank = {tag: i for i, tag in enumerate(supported_tags)}
    compatible_wheels = []
    source_distributions = []

    for file_info in release.get("urls", []):
        filename = file_info.get("filename", "")
        file_type = file_info.get("packagetype", "")
        digests = file_info.get("digests") or {}

        if file_type == "bdist_wheel":
            try:
                wheel_name, wheel_version, _, wheel_tags = parse_wheel_filename(filename)
            except Exception:
                continue
            if canonicalize_name(str(wheel_name)) != canonicalize_name(package):
                continue
            if wheel_version != Version(version):
                continue
            matching_tags = wheel_tags.intersection(supported_tag_set)
            if not matching_tags:
                continue
            ordered = sorted(matching_tags, key=lambda t: tag_rank[t])
            compatible_wheels.append({
                "filename": filename, "url": file_info.get("url"),
                "sha256": digests.get("sha256"),
                "best_matching_tag": str(ordered[0]),
                "matching_tags": [str(t) for t in ordered],
            })
        elif file_type == "sdist":
            source_distributions.append({
                "filename": filename, "url": file_info.get("url"),
                "sha256": digests.get("sha256"),
            })

    if compatible_wheels:
        return {"status": "available", "compatible_wheels": compatible_wheels}

    if source_distributions:
        source_distributions.sort(
            key=lambda i: (not i["filename"].endswith(".tar.gz"), i["filename"])
        )
        return {"status": "build_required", "sdist": source_distributions[0]}

    return {"status": "source_unavailable",
            "reason": "No compatible upstream wheel and no source distribution "
                      "were found for this exact release."}


# ---------------------------------------------------------------------------
# External index lookup + download
# ---------------------------------------------------------------------------

_SIMPLE_ANCHOR_RE = re.compile(
    r'<a\s+[^>]*href="([^"]+)"[^>]*>([^<]+)</a>', re.IGNORECASE,
)


def query_simple_index(
    client: httpx.Client, url: str,
) -> list[dict]:
    """Return [{'filename','url','sha256'}] from a PEP 503 HTML index."""
    try:
        response = client.get(url, follow_redirects=True)
        if response.status_code == 404:
            return []
        response.raise_for_status()
    except httpx.HTTPError:
        return []

    results = []
    for href, text in _SIMPLE_ANCHOR_RE.findall(response.text):
        filename = html_module.unescape(text.strip())
        if not filename.endswith(".whl"):
            continue
        absolute = urljoin(url, href)
        sha = None
        if "#" in absolute:
            absolute, frag = absolute.split("#", 1)
            if frag.startswith("sha256="):
                sha = frag[len("sha256="):]
        results.append({"filename": filename, "url": absolute, "sha256": sha})
    return results


def query_anaconda_api(
    client: httpx.Client, url: str,
) -> list[dict]:
    """Return [{'filename','url','sha256'}] from an Anaconda package API."""
    try:
        response = client.get(url, follow_redirects=True)
        if response.status_code == 404:
            return []
        response.raise_for_status()
        data = response.json()
    except (httpx.HTTPError, json.JSONDecodeError):
        return []

    results = []
    for file_info in data.get("files", []):
        basename = file_info.get("basename", "")
        if not basename.endswith(".whl"):
            continue
        subdir = (file_info.get("attrs") or {}).get("subdir", "")
        if not subdir.startswith("android_"):
            continue
        results.append({
            "filename": basename,
            "url": file_info.get("download_url"),
            "sha256": (file_info.get("attrs") or {}).get("sha256"),
        })
    return results


def find_external_wheel(
    client: httpx.Client,
    package: str,
    version: str,
    target: dict,
    supported_tags: list,
) -> dict | None:
    supported = set(supported_tags)
    for index in EXTERNAL_INDEXES:
        if not index_supports(index, target):
            continue
        url = index["url_template"].format(package=quote(package, safe=""))
        if index["type"] == "simple_html":
            candidates = query_simple_index(client, url)
        elif index["type"] == "anaconda_api":
            candidates = query_anaconda_api(client, url)
        else:
            continue

        for candidate in candidates:
            try:
                wname, wver, _, wtags = parse_wheel_filename(candidate["filename"])
            except Exception:
                continue
            if canonicalize_name(str(wname)) != canonicalize_name(package):
                continue
            if wver != Version(version):
                continue
            if not wtags.intersection(supported):
                continue
            return {
                "index": index["name"],
                "filename": candidate["filename"],
                "url": candidate["url"],
                "sha256": candidate.get("sha256"),
            }
    return None

def download_wheel(
    client: httpx.Client,
    url: str,
    dest_dir: Path,
    expected_sha256: str | None,
) -> tuple[Path, str]:
    """Fetch a wheel and verify its hash. Return (path, sha256)."""
    filename = url.rsplit("/", 1)[-1].split("?")[0].split("#")[0]
    if not filename.endswith(".whl"):
        raise ValueError(f"Not a wheel URL: {url}")
    if "/" in filename or filename.startswith("."):
        raise ValueError(f"Unsafe wheel filename: {filename!r}")

    response = client.get(url, follow_redirects=True)
    response.raise_for_status()
    body = response.content

    digest = hashlib.sha256(body).hexdigest()
    if expected_sha256 and digest.lower() != expected_sha256.lower():
        raise ValueError(
            f"SHA-256 mismatch for {filename}: "
            f"expected {expected_sha256}, got {digest}"
        )

    dest = dest_dir / filename
    dest.write_bytes(body)
    return dest, digest


# ---------------------------------------------------------------------------
# Main discovery
# ---------------------------------------------------------------------------

def discover(
    project_path: Path, lock_path: Path, android_api_level: int,
    pypi_base_url: str, timeout: float, retries: int,
    download_dir: Path | None,
) -> tuple[list[dict], dict]:
    project_data = load_toml(project_path)
    lock_data = load_toml(lock_path)

    project = project_data.get("project", {})
    if not project:
        raise ValueError(f"No [project] table found in {project_path}")

    project_name = project.get("name", "unknown-project")
    project_version = project.get("version", "unknown")

    targets = []
    for base_target in BASE_TARGETS:
        target = dict(base_target)
        if target["family"] == "android":
            target["android_api_level"] = android_api_level
            target["platform_floor"] = {"type": "android", "api_level": android_api_level}
        targets.append(target)

    gaps: list[dict] = []
    available: list[dict] = []
    unbuildable: list[dict] = []
    lock_warnings: list[dict] = []

    release_cache: dict[tuple[str, str], dict | None] = {}
    seen_pure: set[tuple[str, str]] = set()
    # URL -> (path, sha256); shared across targets so a wheel that
    # covers cp313-abi3 for both cp313 and cp314 downloads once.
    downloaded: dict[str, tuple[Path, str, str]] = {}  # url -> (path, sha, index)

    if download_dir is not None:
        download_dir.mkdir(parents=True, exist_ok=True)

    headers = {
        "User-Agent": "Open-News-Dependency-Wheel-Builder/1.5",
        "Accept": "*/*",
    }

    with httpx.Client(timeout=timeout, follow_redirects=True, headers=headers) as client:
        for target in targets:
            log(f"Target: {target['target']}")
            for py_tag in target["python_versions"]:
                environment = make_marker_environment(target, py_tag)
                packages, warnings = resolve_runtime_packages(project, lock_data, environment)
                for warning in warnings:
                    lock_warnings.append({
                        "target": target["target"], "py_tag": py_tag,
                        "warning": warning,
                    })

                supported_tags = get_supported_tags(target, py_tag, android_api_level)

                for package_info in packages:
                    package = package_info["name"]
                    version = package_info["version"]
                    normalized_name = canonicalize_name(package)

                    cache_key = (normalized_name, version)
                    if cache_key not in release_cache:
                        log(f"Checking PyPI: {package}=={version}")
                        release_cache[cache_key] = fetch_pypi_release(
                            client=client, package=package, version=version,
                            base_url=pypi_base_url, retries=retries,
                        )

                    release = release_cache[cache_key]
                    result = inspect_release(package, version, release, supported_tags)

                    base_record = {
                        "package": package, "version": version,
                        "target": target["target"], "py_tag": py_tag,
                        "compatibility_profile": target["family"],
                        "platform_floor": target.get("platform_floor"),
                    }

                    # 1. PyPI compatible wheel
                    if result["status"] == "available":
                        available.append({**base_record, "status": "available",
                                         "source": "pypi",
                                         "compatible_wheels": result["compatible_wheels"]})
                        continue

                    # 2. External index → download during discovery
                    if download_dir is not None:
                        candidate = find_external_wheel(
                            client, package, version, target, supported_tags,
                        )
                        if candidate is not None:
                            url = candidate["url"]
                            local: Path | None = None
                            sha: str | None = None
                            index_name: str | None = None
                            try:
                                if url not in downloaded:
                                    local, sha = download_wheel(
                                        client, url, download_dir,
                                        candidate.get("sha256"),
                                    )
                                    downloaded[url] = (local, sha, candidate["index"])
                                    log(f"Downloaded {local.name} from "
                                        f"{candidate['index']} ({sha[:12]}…)")
                                local, sha, index_name = downloaded[url]
                            except Exception as exc:
                                log(f"External download failed for "
                                    f"{package}=={version}: {exc}")
                                candidate = None

                            if (
                                candidate is not None
                                and local is not None
                                and sha is not None
                                and index_name is not None
                            ):
                                gaps.append({
                                    **base_record,
                                    "build_type": "prebuilt",
                                    "cibw_platform": target["cibw_platform"],
                                    "cibw_archs": target["cibw_archs"],
                                    "runner": target["runner"],
                                    "cibw_build_id": "prebuilt",
                                    "status": "build_required",
                                    "source": index_name,
                                    "prebuilt_filename": local.name,
                                    "prebuilt_sha256": sha,
                                    "prebuilt_url": url,
                                    "sdist_filename": None,
                                    "sdist_url": None,
                                    "sdist_sha256": None,
                                })
                                continue

                    # 3. Known-unsupported on Android
                    if (
                        target["family"] == "android"
                        and normalized_name in ANDROID_UNSUPPORTED_PACKAGES
                    ):
                        unbuildable.append({
                            **base_record,
                            "status": "source_unavailable",
                            "reason": "Known unsupported on Android; "
                                      "no external wheel found.",
                        })
                        continue

                    # 4. No sdist either
                    if result["status"] == "source_unavailable":
                        unbuildable.append({**base_record,
                                           "status": "source_unavailable",
                                           "reason": result["reason"]})
                        continue

                    # 5. Build from sdist
                    sdist = result["sdist"]
                    is_pure = normalized_name not in NATIVE_PACKAGES

                    if is_pure:
                        if (normalized_name, version) in seen_pure:
                            continue
                        seen_pure.add((normalized_name, version))
                        gaps.append({
                            "package": package, "version": version,
                            "target": "pure_python",
                            "py_tag": "py3",
                            "compatibility_profile": "pure_python",
                            "platform_floor": {"type": "any"},
                            "build_type": "pure_python",
                            "cibw_platform": "pure",
                            "cibw_archs": "any",
                            "runner": "ubuntu-latest",
                            "cibw_build_id": "pure",
                            "status": "build_required",
                            "source": "pypi_sdist",
                            "sdist_filename": sdist["filename"],
                            "sdist_url": sdist["url"],
                            "sdist_sha256": sdist["sha256"],
                        })
                    else:
                        if target["family"] in ("manylinux", "musllinux"):
                            cibw_build_id = f"{py_tag}-{target['build_pattern']}"
                        else:
                            cibw_build_id = f"{py_tag}-*"
                        gaps.append({
                            **base_record,
                            "build_type": "cibuildwheel",
                            "cibw_platform": target["cibw_platform"],
                            "cibw_archs": target["cibw_archs"],
                            "cibw_build_id": cibw_build_id,
                            "runner": target["runner"],
                            "status": "build_required",
                            "source": "pypi_sdist",
                            "sdist_filename": sdist["filename"],
                            "sdist_url": sdist["url"],
                            "sdist_sha256": sdist["sha256"],
                        })

    def sort_key(item):
        return (item["package"].lower(), item["target"], item["py_tag"])

    gaps.sort(key=sort_key)
    available.sort(key=sort_key)
    unbuildable.sort(key=sort_key)

    discovery_report = {
        "schema_version": 6,
        "project": project_name,
        "project_version": project_version,
        "android_api_level": android_api_level,
        "policy": {
            "python_versions": list(PYTHON_VERSIONS),
            "android_python_versions": list(ANDROID_PYTHON_VERSIONS),
            "glibc_floor": [2, 28], "musl_floor": [1, 2],
            "macos_floor": [14, 0],
            "android_api_floor": android_api_level,
            "android_unsupported_packages": sorted(ANDROID_UNSUPPORTED_PACKAGES),
            "native_packages": sorted(NATIVE_PACKAGES),
            "external_indexes": [i["name"] for i in EXTERNAL_INDEXES],
            "macos_x86_64": "excluded",
        },
        "targets": [
            {"target": t["target"], "architecture": t["architecture"],
             "python_versions": list(t["python_versions"]),
             "runner": t["runner"], "platform_floor": t.get("platform_floor")}
            for t in targets
        ],
        "summary": {
            "missing_wheel_count": len(gaps),
            "upstream_wheel_count": len(available),
            "source_unavailable_count": len(unbuildable),
            "lock_warning_count": len(lock_warnings),
            "pure_python_count": sum(1 for g in gaps if g.get("build_type") == "pure_python"),
            "cibuildwheel_count": sum(1 for g in gaps if g.get("build_type") == "cibuildwheel"),
            "prebuilt_count": sum(1 for g in gaps if g.get("build_type") == "prebuilt"),
            "prebuilt_unique_files": len(downloaded),
        },
        "available": available,
        "gaps": gaps,
        "source_unavailable": unbuildable,
        "lock_warnings": lock_warnings,
    }

    return gaps, discovery_report


def write_github_outputs(gaps, report, discovery_path):
    output_file = os.environ.get("GITHUB_OUTPUT")
    if not output_file:
        return
    outputs = {
        "matrix": json.dumps({"include": gaps}, separators=(",", ":")),
        "has_gaps": "true" if gaps else "false",
        "gap_count": str(len(gaps)),
        "available_count": str(report["summary"]["upstream_wheel_count"]),
        "unbuildable_count": str(report["summary"]["source_unavailable_count"]),
        "prebuilt_count": str(report["summary"]["prebuilt_unique_files"]),
        "discovery_file": str(discovery_path),
    }
    with open(output_file, "a", encoding="utf-8") as file:
        for key, value in outputs.items():
            file.write(f"{key}={value}\n")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", type=Path, default=Path("pyproject.toml"))
    parser.add_argument("--lock", type=Path, default=Path("uv.lock"))
    parser.add_argument("--output", type=Path, default=Path("wheel-gaps.json"))
    parser.add_argument("--discovery-output", type=Path, default=None)
    parser.add_argument("--android-api-level", type=int, default=24)
    parser.add_argument("--pypi-base-url", default="https://pypi.org/pypi")
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--retries", type=int, default=3)
    parser.add_argument(
        "--download-dir", type=Path, default=None,
        help=(
            "If set, external indexes are queried and matching wheels "
            "are downloaded here. Without this flag, external indexes "
            "are not consulted."
        ),
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.android_api_level < 16:
        print("ERROR: Android API level must be at least 16.", file=sys.stderr)
        return 2
    if args.retries < 0:
        print("ERROR: retries cannot be negative.", file=sys.stderr)
        return 2
    if args.discovery_output is None:
        args.discovery_output = args.output.with_name(f"{args.output.stem}-discovery.json")

    try:
        gaps, report = discover(
            project_path=args.project, lock_path=args.lock,
            android_api_level=args.android_api_level,
            pypi_base_url=args.pypi_base_url,
            timeout=args.timeout, retries=args.retries,
            download_dir=args.download_dir,
        )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.discovery_output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(gaps, indent=2, sort_keys=True) + "\n",
                               encoding="utf-8")
        args.discovery_output.write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        write_github_outputs(gaps, report, args.discovery_output)

        s = report["summary"]
        log(f"Missing wheel combinations: {s['missing_wheel_count']}")
        log(f"  pure_python: {s['pure_python_count']}")
        log(f"  cibuildwheel: {s['cibuildwheel_count']}")
        log(f"  prebuilt (external): {s['prebuilt_count']} entries / "
            f"{s['prebuilt_unique_files']} files")
        log(f"Compatible upstream wheels: {s['upstream_wheel_count']}")
        log(f"Source unavailable: {s['source_unavailable_count']}")
        return 0
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())