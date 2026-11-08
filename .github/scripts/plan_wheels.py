"""Plan Open News dependency-wheel builds.

Runtime dependency resolution (uv.lock), PyPI coverage check, external
wheel download for prebuilts, and build-plan emission. Recipe acquisition
and preflight live in recipes.py.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from collections import defaultdict
from pathlib import Path
from urllib.parse import quote

import httpx

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib

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
from recipes import (
    download_wheel,
    find_external_wheel,
    log,
    resolve_recipe,
)

# ─── Configuration ───────────────────────────────────────────────────────

PYTHON_VERSIONS = ("cp311", "cp312", "cp313", "cp314")
ANDROID_PYTHON_VERSIONS = ("cp313", "cp314")

TARGETS = [
    {
        "target": "manylinux_x86_64",
        "family": "manylinux",
        "architecture": "x86_64",
        "cibw_platform": "linux",
        "cibw_archs": "x86_64",
        "runner": "ubuntu-latest",
        "python_versions": PYTHON_VERSIONS,
        "build_pattern": "manylinux_*",
        "platform_floor": {"type": "glibc", "major": 2, "minor": 28},
    },
    {
        "target": "manylinux_aarch64",
        "family": "manylinux",
        "architecture": "aarch64",
        "cibw_platform": "linux",
        "cibw_archs": "aarch64",
        "runner": "ubuntu-24.04-arm",
        "python_versions": PYTHON_VERSIONS,
        "build_pattern": "manylinux_*",
        "platform_floor": {"type": "glibc", "major": 2, "minor": 28},
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
        "platform_floor": {"type": "musl", "major": 1, "minor": 2},
    },
    {
        "target": "musllinux_aarch64",
        "family": "musllinux",
        "architecture": "aarch64",
        "cibw_platform": "linux",
        "cibw_archs": "aarch64",
        "runner": "ubuntu-24.04-arm",
        "python_versions": PYTHON_VERSIONS,
        "build_pattern": "musllinux_*",
        "platform_floor": {"type": "musl", "major": 1, "minor": 2},
    },
    {
        "target": "macosx_arm64",
        "family": "macos",
        "architecture": "arm64",
        "cibw_platform": "macos",
        "cibw_archs": "arm64",
        "runner": "macos-latest",
        "python_versions": PYTHON_VERSIONS,
        "macos_floor": (14, 0),
        "platform_floor": {"type": "macos", "major": 14, "minor": 0},
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
        "python_versions": ANDROID_PYTHON_VERSIONS,
    },
]


# ─── Utilities ───────────────────────────────────────────────────────────


def load_toml(path: Path) -> dict:
    if not path.is_file():
        raise FileNotFoundError(f"Required file not found: {path}")
    with path.open("rb") as f:
        return tomllib.load(f)


def python_version_from_tag(py_tag: str) -> tuple[int, int]:
    if not py_tag.startswith("cp"):
        raise ValueError(f"Unsupported Python tag: {py_tag}")
    digits = py_tag[2:]
    if len(digits) != 3 or not digits.isdigit():
        raise ValueError(f"Invalid CPython tag: {py_tag}")
    return int(digits[0]), int(digits[1:])


def py_tag_sort_key(tag: str) -> tuple[int, int]:
    m = re.match(r"cp(\d)(\d+)", tag)
    return (int(m.group(1)), int(m.group(2))) if m else (0, 0)


# ─── Marker environments and tag sets ────────────────────────────────────


def marker_matches(marker_text: str | None, environment: dict) -> bool:
    if not marker_text:
        return True
    try:
        return Marker(marker_text).evaluate(environment=environment)
    except Exception as exc:
        log(f"WARNING: cannot evaluate marker {marker_text!r}: {exc}")
        return True


def make_marker_environment(target: dict, py_tag: str) -> dict:
    major, minor = python_version_from_tag(py_tag)
    family = target["family"]
    arch = target["architecture"]

    if family == "windows":
        sys_platform, platform_system, os_name, machine = (
            "win32",
            "Windows",
            "nt",
            "AMD64",
        )
    elif family == "macos":
        sys_platform, platform_system, os_name, machine = (
            "darwin",
            "Darwin",
            "posix",
            arch,
        )
    elif family == "android":
        sys_platform, platform_system, os_name, machine = (
            "android",
            "Android",
            "posix",
            "aarch64",
        )
    else:
        sys_platform, platform_system, os_name = "linux", "Linux", "posix"
        machine = "aarch64" if arch == "arm64_v8a" else arch

    full = f"{major}.{minor}.0"
    return {
        "implementation_name": "cpython",
        "implementation_version": full,
        "os_name": os_name,
        "platform_machine": machine,
        "platform_release": "0",
        "platform_system": platform_system,
        "platform_version": "0",
        "python_full_version": full,
        "python_version": f"{major}.{minor}",
        "sys_platform": sys_platform,
        "platform_python_implementation": "CPython",
        "extra": "",
    }


def manylinux_platform_tags(target: dict) -> list[str]:
    arch = target["architecture"]
    floor = target["platform_floor"]
    if floor["major"] != 2:
        raise ValueError("Only glibc 2.x policies are supported.")
    floor_minor = floor["minor"]
    tags = [f"manylinux_2_{m}_{arch}" for m in range(floor_minor, 3, -1)]
    if floor_minor <= 17:
        tags.append(f"manylinux2014_{arch}")
    if arch == "x86_64":
        if floor_minor <= 12:
            tags.append("manylinux2010_x86_64")
        if floor_minor <= 5:
            tags.append("manylinux1_x86_64")
    return list(dict.fromkeys(tags))


def musllinux_platform_tags(target: dict) -> list[str]:
    arch = target["architecture"]
    floor = target["platform_floor"]
    return [
        f"musllinux_{floor['major']}_{m}_{arch}" for m in range(floor["minor"], 0, -1)
    ]


def get_platform_tags(target: dict, android_api_level: int) -> list[str]:
    fam = target["family"]
    arch = target["architecture"]
    if fam == "manylinux":
        return manylinux_platform_tags(target)
    if fam == "musllinux":
        return musllinux_platform_tags(target)
    if fam == "macos":
        return list(mac_platforms(version=target["macos_floor"], arch=arch))
    if fam == "windows":
        return ["win_amd64"]
    if fam == "android":
        return list(android_platforms(api_level=android_api_level, abi=arch))
    raise ValueError(f"Unknown target family: {fam}")


def get_supported_tags(target: dict, py_tag: str, android_api_level: int) -> list:
    pv = python_version_from_tag(py_tag)
    platforms = get_platform_tags(target, android_api_level)
    ordered = list(cpython_tags(python_version=pv, abis=[py_tag], platforms=platforms))
    ordered.extend(
        compatible_tags(python_version=pv, interpreter=py_tag, platforms=platforms)
    )
    return list(dict.fromkeys(ordered))


# ─── Runtime dependency resolution ───────────────────────────────────────


def version_satisfies(version_text: str, specifier_text: str | None) -> bool:
    if not specifier_text:
        return True
    try:
        return SpecifierSet(specifier_text).contains(
            Version(version_text), prereleases=True
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
    lock_packages = lock.get("package", [])
    by_name: dict[str, list[dict]] = {}
    for pkg in lock_packages:
        name = pkg.get("name")
        version = pkg.get("version")
        if name and version:
            by_name.setdefault(canonicalize_name(name), []).append(pkg)

    stack: list[dict] = []
    warnings: list[str] = []

    for req_text in project.get("dependencies", []):
        try:
            req = Requirement(req_text)
        except Exception as exc:
            warnings.append(f"Invalid project dependency {req_text!r}: {exc}")
            continue
        if req.marker and not req.marker.evaluate(environment=environment):
            continue
        cands = by_name.get(canonicalize_name(req.name), [])
        matching = [
            p for p in cands if version_satisfies(p["version"], str(req.specifier))
        ]
        if not matching:
            warnings.append(f"No matching uv.lock entry for {req.name}")
            continue
        stack.extend(matching)

    visited: set[tuple] = set()
    result: list[dict] = []

    while stack:
        pkg = stack.pop()
        ident = package_identity(pkg)
        if ident in visited:
            continue
        visited.add(ident)
        result.append(pkg)

        for dep in pkg.get("dependencies", []):
            if not isinstance(dep, dict):
                continue
            if not marker_matches(dep.get("marker"), environment):
                continue
            dep_name = dep.get("name")
            if not dep_name:
                continue
            cands = by_name.get(canonicalize_name(dep_name), [])
            matching = [
                c for c in cands if version_satisfies(c["version"], dep.get("version"))
            ]
            if not matching:
                warnings.append(
                    f"Unresolved locked dependency: {dep_name} "
                    f"({dep.get('version', '')})"
                )
                continue
            stack.extend(matching)

    result.sort(key=lambda i: (canonicalize_name(i["name"]), i["version"]))
    return result, warnings


# ─── PyPI release inspection ─────────────────────────────────────────────


def fetch_pypi_release(
    client: httpx.Client,
    package: str,
    version: str,
    base_url: str,
    retries: int,
) -> dict | None:
    url = f"{base_url.rstrip('/')}/{quote(package, safe='')}/{quote(version, safe='')}/json"
    for attempt in range(retries + 1):
        try:
            r = client.get(url)
            if r.status_code == 404:
                return None
            if r.status_code == 429 or r.status_code >= 500:
                if attempt < retries:
                    time.sleep(min(2**attempt, 10))
                    continue
            r.raise_for_status()
            return r.json()
        except httpx.HTTPError:
            if attempt >= retries:
                raise
            time.sleep(min(2**attempt, 10))
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
            "reason": "Package release not found on PyPI.",
        }

    supported = set(supported_tags)
    rank = {tag: i for i, tag in enumerate(supported_tags)}
    compatible = []
    sdists = []

    for file_info in release.get("urls", []):
        fname = file_info.get("filename", "")
        ftype = file_info.get("packagetype", "")
        digests = file_info.get("digests") or {}

        if ftype == "bdist_wheel":
            try:
                wname, wver, _, wtags = parse_wheel_filename(fname)
            except Exception:
                continue
            if canonicalize_name(str(wname)) != canonicalize_name(package):
                continue
            if wver != Version(version):
                continue
            matches = wtags.intersection(supported)
            if not matches:
                continue
            ordered = sorted(matches, key=lambda t: rank[t])
            compatible.append(
                {
                    "filename": fname,
                    "url": file_info.get("url"),
                    "sha256": digests.get("sha256"),
                    "best_matching_tag": str(ordered[0]),
                    "matching_tags": [str(t) for t in ordered],
                }
            )
        elif ftype == "sdist":
            sdists.append(
                {
                    "filename": fname,
                    "url": file_info.get("url"),
                    "sha256": digests.get("sha256"),
                }
            )

    if compatible:
        return {"status": "available", "compatible_wheels": compatible}
    if sdists:
        sdists.sort(
            key=lambda i: (not i["filename"].endswith(".tar.gz"), i["filename"])
        )
        return {"status": "build_required", "sdist": sdists[0]}
    return {
        "status": "source_unavailable",
        "reason": "No compatible upstream wheel and no sdist for this release.",
    }


# ─── Plan assembly ───────────────────────────────────────────────────────


def _dedupe_by_name(items: list[dict]) -> list[dict]:
    seen: set[str] = set()
    out = []
    for item in items:
        name = item.get("name") or item.get("filename") or ""
        if name in seen:
            continue
        seen.add(name)
        out.append(item)
    return out


def _serialize_env(env: dict[str, str]) -> str:
    """Serialize env dict to CIBW_ENVIRONMENT syntax.

    Values are double-quoted so that $VAR and $(...) expand inside the
    shell that sources CIBW_ENVIRONMENT. Single quotes would suppress
    expansion, which is exactly what we need here (dynamic paths).
    """
    parts = []
    for k, v in env.items():
        escaped = v.replace('"', '\\"')
        parts.append(f'{k}="{escaped}"')
    return " ".join(parts)


def build_plan_from_gaps(gaps: list[dict], max_tags: int) -> list[dict]:
    plan: list[dict] = []
    seen_pure: set[tuple[str, str]] = set()

    for gap in gaps:
        if gap.get("build_type") != "pure_python":
            continue
        key = (gap["package"], gap["version"])
        if key in seen_pure:
            continue
        seen_pure.add(key)
        plan.append(
            {
                "package": gap["package"],
                "version": gap["version"],
                "target": "pure_python",
                "build_type": "pure_python",
                "cibw_platform": "pure",
                "cibw_archs": "any",
                "runner": "ubuntu-latest",
                "py_tags": ["py3"],
                "cibw_build": "py3-none-any",
                "platform_floor": {"type": "any"},
                "source_url": gap.get("sdist_url"),
                "source_sha256": gap.get("sdist_sha256"),
                "confidence": gap.get("confidence", "high"),
                "reason": gap.get("reason", ""),
                "recipe_source": gap.get("recipe_source", "static"),
                "system_deps": gap.get("system_deps", []),
                "host_requirements_json": "[]",
                "build_requirements_json": "[]",
                "patches_json": "[]",
                "cibw_before_all": "",
                "cibw_before_all_linux": "",
                "cibw_environment_string": "",
                "repair_command": "",
                "batch": 1,
            }
        )

    for gap in gaps:
        if gap.get("build_type") != "prebuilt":
            continue
        plan.append(
            {
                "package": gap["package"],
                "version": gap["version"],
                "target": gap["target"],
                "build_type": "prebuilt",
                "cibw_platform": gap["cibw_platform"],
                "cibw_archs": gap["cibw_archs"],
                "runner": gap["runner"],
                "py_tags": [gap["py_tag"]],
                "cibw_build": "prebuilt",
                "platform_floor": gap.get("platform_floor"),
                "prebuilt_filename": gap.get("prebuilt_filename"),
                "prebuilt_sha256": gap.get("prebuilt_sha256"),
                "prebuilt_url": gap.get("prebuilt_url"),
                "prebuilt_source": gap.get("source"),
                "requested_version": gap.get("requested_version"),
                "shipped_version": gap.get("shipped_version"),
                "version_delta": gap.get("version_delta"),
                "runtime_risk": gap.get("runtime_risk"),
                "confidence": "high",
                "reason": gap.get("reason", ""),
                "recipe_source": "external_index",
                "system_deps": [],
                "host_requirements_json": "[]",
                "build_requirements_json": "[]",
                "patches_json": "[]",
                "cibw_before_all": "",
                "cibw_before_all_linux": "",
                "cibw_environment_string": "",
                "repair_command": "",
                "batch": 1,
            }
        )

    groups: dict[tuple, dict[str, dict]] = defaultdict(dict)
    for gap in gaps:
        if gap.get("build_type") != "cibuildwheel":
            continue
        key = (
            gap["package"],
            gap["version"],
            gap["target"],
            gap["cibw_platform"],
            gap["cibw_archs"],
            gap["runner"],
        )
        groups[key].setdefault(gap["py_tag"], gap)

    for key in sorted(groups):
        package, version, target, platform, arch, runner = key
        entries = groups[key]
        tags = sorted(entries, key=py_tag_sort_key)

        for offset in range(0, len(tags), max_tags):
            batch = tags[offset : offset + max_tags]
            selected = [entries[t] for t in batch]

            urls = {s.get("sdist_url") for s in selected if s.get("sdist_url")}
            hashes = {s.get("sdist_sha256") for s in selected if s.get("sdist_sha256")}
            if len(urls) > 1 or len(hashes) > 1:
                raise ValueError(
                    f"Inconsistent sdist for {package}=={version}/{target}"
                )

            if platform == "linux" and target.startswith(("manylinux", "musllinux")):
                prefix = "manylinux" if target.startswith("manylinux") else "musllinux"
                selector = " ".join(f"{t}-{prefix}_*" for t in batch)
            else:
                selector = " ".join(f"{t}-*" for t in batch)

            all_deps: set[str] = set()
            for s in selected:
                all_deps.update(s.get("system_deps") or [])
            confidences = [s.get("confidence", "high") for s in selected]
            worst = min(
                confidences, key=lambda c: {"low": 0, "medium": 1, "high": 2}.get(c, 2)
            )

            host_reqs = _dedupe_by_name(
                [r for s in selected for r in (s.get("host_requirements") or [])]
            )
            build_reqs = _dedupe_by_name(
                [r for s in selected for r in (s.get("build_requirements") or [])]
            )
            patches = _dedupe_by_name(
                [p for s in selected for p in (s.get("patches") or [])]
            )

            before_all = next(
                (
                    s.get("cibw_before_all")
                    for s in selected
                    if s.get("cibw_before_all")
                ),
                "",
            )
            before_all_linux = next(
                (
                    s.get("cibw_before_all_linux")
                    for s in selected
                    if s.get("cibw_before_all_linux")
                ),
                "",
            )
            repair = next(
                (s.get("repair_command") for s in selected if s.get("repair_command")),
                "",
            )
            env = selected[0].get("env") or {}

            plan.append(
                {
                    "package": package,
                    "version": version,
                    "target": target,
                    "build_type": "cibuildwheel",
                    "cibw_platform": platform,
                    "cibw_archs": arch,
                    "runner": runner,
                    "py_tags": batch,
                    "cibw_build": selector,
                    "platform_floor": selected[0].get("platform_floor"),
                    "source_url": next(iter(urls), None),
                    "source_sha256": next(iter(hashes), None),
                    "confidence": worst,
                    "reason": selected[0].get("reason", ""),
                    "recipe_source": selected[0].get("recipe_source", "static"),
                    "system_deps": sorted(all_deps),
                    "host_requirements_json": json.dumps(
                        host_reqs, separators=(",", ":")
                    ),
                    "build_requirements_json": json.dumps(
                        build_reqs, separators=(",", ":")
                    ),
                    "patches_json": json.dumps(patches, separators=(",", ":")),
                    "cibw_before_all": before_all or "",
                    "cibw_before_all_linux": before_all_linux or "",
                    "cibw_environment_string": _serialize_env(env),
                    "repair_command": repair or "",
                    "batch": offset // max_tags + 1,
                }
            )

    return plan


# ─── Main discovery ──────────────────────────────────────────────────────


def run_plan(args: argparse.Namespace) -> tuple[list[dict], dict, list[dict]]:
    project_data = load_toml(args.project)
    lock_data = load_toml(args.lock)
    project = project_data.get("project", {})
    if not project:
        raise ValueError(f"No [project] table in {args.project}")
    if "dependencies" in (project.get("dynamic") or []):
        log(
            "WARNING: [project] declares dependencies as dynamic; resolution may be incomplete"
        )

    if args.download_dir is not None:
        args.download_dir.mkdir(parents=True, exist_ok=True)

    targets = []
    for base in TARGETS:
        t = dict(base)
        if t["family"] == "android":
            t["android_api_level"] = args.android_api_level
            t["platform_floor"] = {
                "type": "android",
                "api_level": args.android_api_level,
            }
        targets.append(t)

    gaps: list[dict] = []
    available: list[dict] = []
    unbuildable: list[dict] = []
    lock_warnings: list[dict] = []
    rejected: list[str] = []

    release_cache: dict[tuple[str, str], dict | None] = {}
    prebuilt_files: dict[str, tuple[Path, str, str]] = {}

    headers = {"User-Agent": "Open-News-plan-wheels/4.0", "Accept": "*/*"}

    with httpx.Client(
        timeout=args.timeout, follow_redirects=True, headers=headers
    ) as client:
        for target in targets:
            log(f"Target: {target['target']}")
            for py_tag in target["python_versions"]:
                env = make_marker_environment(target, py_tag)
                packages, warnings = resolve_runtime_packages(project, lock_data, env)
                for w in warnings:
                    lock_warnings.append(
                        {"target": target["target"], "py_tag": py_tag, "warning": w}
                    )

                supported = get_supported_tags(target, py_tag, args.android_api_level)

                for pkg in packages:
                    package = pkg["name"]
                    version = pkg["version"]
                    name_norm = canonicalize_name(package)

                    if args.only and canonicalize_name(args.only) != name_norm:
                        continue

                    cache_key = (name_norm, version)
                    if cache_key not in release_cache:
                        log(f"PyPI: {package}=={version}")
                        release_cache[cache_key] = fetch_pypi_release(
                            client,
                            package,
                            version,
                            args.pypi_base_url,
                            args.retries,
                        )

                    result = inspect_release(
                        package, version, release_cache[cache_key], supported
                    )
                    base = {
                        "package": package,
                        "version": version,
                        "target": target["target"],
                        "py_tag": py_tag,
                        "compatibility_profile": target["family"],
                        "platform_floor": target.get("platform_floor"),
                    }

                    # 1. PyPI exact wheel
                    if result["status"] == "available":
                        available.append(
                            {
                                **base,
                                "status": "available",
                                "source": "pypi",
                                "compatible_wheels": result["compatible_wheels"],
                            }
                        )
                        continue

                    # 2. External index (exact → patch → minor)
                    if args.download_dir is not None:
                        cand = find_external_wheel(
                            client,
                            package,
                            version,
                            target,
                            supported,
                            allow_deltas=("patch", "minor"),
                        )
                        if cand is not None and cand.get("runtime_risk") != "high":
                            try:
                                url = cand["url"]
                                if url not in prebuilt_files:
                                    local, sha = download_wheel(
                                        client,
                                        url,
                                        args.download_dir,
                                        cand.get("sha256"),
                                    )
                                    prebuilt_files[url] = (local, sha, cand["index"])
                                    log(
                                        f"Prebuilt {local.name} from {cand['index']} "
                                        f"({cand['version_delta']} drift, risk={cand['runtime_risk']})"
                                    )
                                local, sha, idx = prebuilt_files[url]
                            except Exception as exc:
                                log(
                                    f"External download failed for {package}=={version}: {exc}"
                                )
                            else:
                                gaps.append(
                                    {
                                        **base,
                                        "build_type": "prebuilt",
                                        "cibw_platform": target["cibw_platform"],
                                        "cibw_archs": target["cibw_archs"],
                                        "runner": target["runner"],
                                        "cibw_build_id": "prebuilt",
                                        "status": "build_required",
                                        "source": idx,
                                        "prebuilt_filename": local.name,
                                        "prebuilt_sha256": sha,
                                        "prebuilt_url": url,
                                        "requested_version": cand["requested_version"],
                                        "shipped_version": cand["shipped_version"],
                                        "version_delta": cand["version_delta"],
                                        "runtime_risk": cand["runtime_risk"],
                                        "sdist_filename": None,
                                        "sdist_url": None,
                                        "sdist_sha256": None,
                                        "confidence": "high",
                                        "reason": f"prebuilt from {idx} ({cand['version_delta']} drift)",
                                    }
                                )
                                continue

                    # 3. No sdist → unbuildable
                    if result["status"] == "source_unavailable":
                        unbuildable.append(
                            {
                                **base,
                                "status": "source_unavailable",
                                "reason": result["reason"],
                            }
                        )
                        continue

                    # 4. Recipe ladder
                    sdist = result["sdist"]
                    recipe, kind, rejects = resolve_recipe(
                        client,
                        package,
                        version,
                        target,
                        sdist["url"],
                        sdist.get("sha256"),
                        do_probe=not args.no_probe,
                    )

                    if recipe.build_type == "pure_python":
                        gaps.append(
                            {
                                "package": package,
                                "version": version,
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
                                "sdist_sha256": sdist.get("sha256"),
                                "confidence": recipe.confidence,
                                "reason": recipe.reason,
                                "recipe_source": recipe.source,
                                "system_deps": recipe.system_deps,
                                "host_requirements": recipe.host_artifacts,
                                "build_requirements": [],
                                "patches": recipe.patches,
                                "cibw_before_all": recipe.before_all,
                                "cibw_before_all_linux": recipe.before_all_linux,
                                "repair_command": recipe.repair_command,
                                "env": recipe.env,
                                "preflight_rejects": rejects,
                            }
                        )
                    else:
                        cibw_id = (
                            f"{py_tag}-{target['build_pattern']}"
                            if target["family"] in ("manylinux", "musllinux")
                            else f"{py_tag}-*"
                        )
                        gaps.append(
                            {
                                **base,
                                "build_type": "cibuildwheel",
                                "cibw_platform": target["cibw_platform"],
                                "cibw_archs": target["cibw_archs"],
                                "cibw_build_id": cibw_id,
                                "runner": target["runner"],
                                "status": "build_required",
                                "source": "pypi_sdist",
                                "sdist_filename": sdist["filename"],
                                "sdist_url": sdist["url"],
                                "sdist_sha256": sdist.get("sha256"),
                                "confidence": recipe.confidence,
                                "reason": recipe.reason,
                                "recipe_source": recipe.source,
                                "system_deps": recipe.system_deps,
                                "host_requirements": recipe.host_artifacts,
                                "build_requirements": [],
                                "patches": recipe.patches,
                                "cibw_before_all": recipe.before_all,
                                "cibw_before_all_linux": recipe.before_all_linux,
                                "repair_command": recipe.repair_command,
                                "env": recipe.env,
                                "preflight_rejects": rejects,
                            }
                        )

    for gap in unbuildable:
        rejected.append(f"{gap['package']}=={gap['version']}: {gap.get('reason', '')}")

    def sort_key(item: dict) -> tuple:
        return (item["package"].lower(), item["target"], item["py_tag"])

    gaps.sort(key=sort_key)
    available.sort(key=sort_key)
    unbuildable.sort(key=sort_key)

    plan = build_plan_from_gaps(gaps, args.max_python_tags_per_job)

    project_name = project.get("name", "unknown")
    project_version = project.get("version", "unknown")

    prebuilt_unique = len(
        {
            g["prebuilt_filename"]
            for g in gaps
            if g.get("build_type") == "prebuilt" and g.get("prebuilt_filename")
        }
    )

    recipe_sources: dict[str, int] = defaultdict(int)
    for g in gaps:
        recipe_sources[g.get("recipe_source", "static")] += 1

    preflight_failures = sum(1 for g in gaps if g.get("preflight_rejects"))

    report = {
        "schema_version": 9,
        "project": project_name,
        "project_version": project_version,
        "android_api_level": args.android_api_level,
        "policy": {
            "python_versions": list(PYTHON_VERSIONS),
            "android_python_versions": list(ANDROID_PYTHON_VERSIONS),
            "recipe_tiers": ["local", "chaquopy", "flet", "termux", "static"],
            "prebuilt_deltas": ["exact", "patch", "minor"],
            "hardcoded_packages": False,
        },
        "targets": [
            {
                "target": t["target"],
                "architecture": t["architecture"],
                "python_versions": list(t["python_versions"]),
                "runner": t["runner"],
                "platform_floor": t.get("platform_floor"),
            }
            for t in targets
        ],
        "summary": {
            "missing_wheel_count": len(gaps),
            "upstream_wheel_count": len(available),
            "source_unavailable_count": len(unbuildable),
            "lock_warning_count": len(lock_warnings),
            "rejected_count": len(rejected),
            "pure_python_count": sum(
                1 for g in gaps if g.get("build_type") == "pure_python"
            ),
            "cibuildwheel_count": sum(
                1 for g in gaps if g.get("build_type") == "cibuildwheel"
            ),
            "prebuilt_count": sum(1 for g in gaps if g.get("build_type") == "prebuilt"),
            "prebuilt_unique_files": prebuilt_unique,
            "low_confidence_count": sum(
                1 for g in gaps if g.get("confidence") == "low"
            ),
            "preflight_failure_count": preflight_failures,
            "recipe_sources": dict(recipe_sources),
        },
        "available": available,
        "gaps": gaps,
        "source_unavailable": unbuildable,
        "lock_warnings": lock_warnings,
        "rejected": rejected,
    }
    return plan, report, gaps


# ─── Output writing ──────────────────────────────────────────────────────


def write_github_outputs(
    args: argparse.Namespace, plan: list[dict], report: dict
) -> None:
    output_file = os.environ.get("GITHUB_OUTPUT")
    if not output_file:
        return
    buildable = [p for p in plan if p.get("build_type") != "prebuilt"]
    outputs = {
        "matrix": json.dumps(buildable, separators=(",", ":")),
        "has_builds": "true" if buildable else "false",
        "build_count": str(len(buildable)),
        "gap_count": str(report["summary"]["missing_wheel_count"]),
        "rejected_count": str(report["summary"]["rejected_count"]),
        "prebuilt_count": str(report["summary"]["prebuilt_unique_files"]),
    }
    with open(output_file, "a", encoding="utf-8") as f:
        for key, value in outputs.items():
            f.write(f"{key}={value}\n")


# ─── CLI ─────────────────────────────────────────────────────────────────


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Plan dependency-wheel builds (recipe ladder + preflight).",
    )
    p.add_argument("--project", type=Path, default=Path("pyproject.toml"))
    p.add_argument("--lock", type=Path, default=Path("uv.lock"))
    p.add_argument("--output", type=Path, default=Path("wheel-gaps.json"))
    p.add_argument("--plan-output", type=Path, default=Path("wheel-build-plan.json"))
    p.add_argument("--discovery-output", type=Path, default=None)
    p.add_argument("--android-api-level", type=int, default=24)
    p.add_argument("--pypi-base-url", default="https://pypi.org/pypi")
    p.add_argument("--timeout", type=float, default=30.0)
    p.add_argument("--retries", type=int, default=3)
    p.add_argument("--max-python-tags-per-job", type=int, default=5)
    p.add_argument(
        "--download-dir",
        type=Path,
        default=None,
        help="Enables external-index wheel lookups and prebuilt downloads.",
    )
    p.add_argument(
        "--no-probe", action="store_true", help="Skip the pure-Python build probe."
    )
    p.add_argument("--only", type=str, default=None)
    return p.parse_args()


def main() -> int:
    args = parse_args()
    if args.android_api_level < 16:
        print("ERROR: --android-api-level must be >= 16.", file=sys.stderr)
        return 2
    if args.retries < 0:
        print("ERROR: --retries cannot be negative.", file=sys.stderr)
        return 2
    if args.discovery_output is None:
        args.discovery_output = args.output.with_name(
            f"{args.output.stem}-discovery.json"
        )

    try:
        plan, report, gaps = run_plan(args)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.plan_output.parent.mkdir(parents=True, exist_ok=True)
        args.discovery_output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(gaps, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        args.plan_output.write_text(
            json.dumps(plan, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        args.discovery_output.write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        write_github_outputs(args, plan, report)

        s = report["summary"]
        log(f"Plan entries: {len(plan)}")
        log(f"  buildable:    {sum(1 for p in plan if p['build_type'] != 'prebuilt')}")
        log(f"  prebuilt:     {sum(1 for p in plan if p['build_type'] == 'prebuilt')}")
        log(f"  pure_python:  {s['pure_python_count']}")
        log(f"  cibuildwheel: {s['cibuildwheel_count']}")
        log(f"  low-conf:     {s['low_confidence_count']}")
        log(f"  preflight-fail: {s['preflight_failure_count']}")
        log(f"Recipe sources: {s['recipe_sources']}")
        log(f"Upstream covered:   {s['upstream_wheel_count']}")
        log(f"Source unavailable: {s['source_unavailable_count']}")
        return 0
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
