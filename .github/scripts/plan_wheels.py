#!/usr/bin/env python3
"""
Discover missing dependency wheels for Open News and emit a build recipe.

Three-tier recipe resolution:
    Tier 1  Chaquopy meta.yaml     (Android — host artifacts, patches, env)
    Tier 2  piwheels apt_deps      (Linux  — system package list)
    Tier 3  Static analysis        (fallback for anything neither index knows)

Outputs:
    --output             wheel-gaps.json
    --plan-output        wheel-build-plan.json
    --discovery-output   wheel-gaps-discovery.json
    $GITHUB_OUTPUT       matrix, has_builds, build_count, rejected_count,
                         prebuilt_count, gap_count
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import html as html_module
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
import zipfile
from collections import defaultdict
from pathlib import Path
from urllib.parse import quote, urljoin

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib

try:
    import yaml  # for Chaquopy meta.yaml
except ImportError:
    yaml = None

import httpx

from packaging.markers import Marker
from packaging.requirements import Requirement
from packaging.specifiers import SpecifierSet
from packaging.tags import android_platforms, compatible_tags, cpython_tags, mac_platforms
from packaging.utils import canonicalize_name, parse_wheel_filename
from packaging.version import Version


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

PYTHON_VERSIONS = ("cp311", "cp312", "cp313", "cp314")
ANDROID_PYTHON_VERSIONS = ("cp313", "cp314")

TARGETS = [
    {"target": "manylinux_x86_64", "family": "manylinux", "architecture": "x86_64",
     "cibw_platform": "linux", "cibw_archs": "x86_64", "runner": "ubuntu-latest",
     "python_versions": PYTHON_VERSIONS, "build_pattern": "manylinux_*",
     "platform_floor": {"type": "glibc", "major": 2, "minor": 28}},
    {"target": "manylinux_aarch64", "family": "manylinux", "architecture": "aarch64",
     "cibw_platform": "linux", "cibw_archs": "aarch64", "runner": "ubuntu-24.04-arm",
     "python_versions": PYTHON_VERSIONS, "build_pattern": "manylinux_*",
     "platform_floor": {"type": "glibc", "major": 2, "minor": 28}},
    {"target": "musllinux_x86_64", "family": "musllinux", "architecture": "x86_64",
     "cibw_platform": "linux", "cibw_archs": "x86_64", "runner": "ubuntu-latest",
     "python_versions": PYTHON_VERSIONS, "build_pattern": "musllinux_*",
     "platform_floor": {"type": "musl", "major": 1, "minor": 2}},
    {"target": "musllinux_aarch64", "family": "musllinux", "architecture": "aarch64",
     "cibw_platform": "linux", "cibw_archs": "aarch64", "runner": "ubuntu-24.04-arm",
     "python_versions": PYTHON_VERSIONS, "build_pattern": "musllinux_*",
     "platform_floor": {"type": "musl", "major": 1, "minor": 2}},
    {"target": "macosx_arm64", "family": "macos", "architecture": "arm64",
     "cibw_platform": "macos", "cibw_archs": "arm64", "runner": "macos-latest",
     "python_versions": PYTHON_VERSIONS, "macos_floor": (14, 0),
     "platform_floor": {"type": "macos", "major": 14, "minor": 0}},
    {"target": "win_amd64", "family": "windows", "architecture": "AMD64",
     "cibw_platform": "windows", "cibw_archs": "AMD64", "runner": "windows-latest",
     "python_versions": PYTHON_VERSIONS},
    {"target": "android_arm64_v8a", "family": "android", "architecture": "arm64_v8a",
     "cibw_platform": "android", "cibw_archs": "arm64_v8a", "runner": "ubuntu-latest",
     "python_versions": ANDROID_PYTHON_VERSIONS},
]

EXTERNAL_INDEXES = [
    {"name": "chaquopy", "type": "simple_html",
     "url_template": "https://chaquo.com/pypi-13.1/{package}/",
     "supports": {"families": {"android"}}},
    {"name": "flet", "type": "simple_html",
     "url_template": "https://pypi.flet.dev/{package}/",
     "supports": {"families": {"android", "ios"}}},
    {"name": "anaconda_pyswift", "type": "anaconda_api",
     "url_template": "https://api.anaconda.org/package/PySwift/{package}",
     "supports": {"families": {"android"}}},
    {"name": "exotic_wheels", "type": "simple_html",
     "url_template": "https://exotic-wheels.github.io/simple/{package}/",
     "supports": {"families": {"musllinux"},
                  "archs": {"armv7l", "aarch64", "ppc64le", "s390x", "riscv64"}}},
    {"name": "piwheels", "type": "simple_html",
     "url_template": "https://www.piwheels.org/simple/{package}/",
     "supports": {"families": {"manylinux"}, "archs": {"armv7l", "armv6l"}}},
    {"name": "pytorch_cpu", "type": "simple_html",
     "url_template": "https://download.pytorch.org/whl/cpu/{package}/",
     "supports": {"families": {"manylinux", "musllinux", "windows", "macos"}}},
    {"name": "nvidia", "type": "simple_html",
     "url_template": "https://pypi.nvidia.com/{package}/",
     "supports": {"families": {"manylinux"}}},
]

# ─── RECIPE SOURCES ───────────────────────────────────────────────────────

CHAQUOPY_META_URL = (
    "https://raw.githubusercontent.com/chaquo/chaquopy/master/"
    "packages/{package}/meta.yaml"
)
CHAQUOPY_PATCH_URL = (
    "https://raw.githubusercontent.com/chaquo/chaquopy/master/"
    "packages/{package}/patches/{patch}"
)
CHAQUOPY_MAVEN_BASE = "https://repo1.maven.org/maven2/com/chaquo/python"

PIWHEELS_JSON_URL = "https://www.piwheels.org/project/{package}/json"

DEB_TO_RPM = {
    "libxml2-dev": "libxml2-devel",
    "libxslt1-dev": "libxslt-devel",
    "libssl-dev": "openssl-devel",
    "libffi-dev": "libffi-devel",
    "zlib1g-dev": "zlib-devel",
    "libjpeg-dev": "libjpeg-turbo-devel",
    "libpng-dev": "libpng-devel",
    "libyaml-dev": "libyaml-devel",
    "libfreetype6-dev": "freetype-devel",
    "gfortran": "gcc-gfortran",
    "libopenblas-dev": "openblas-devel",
    "liblapack-dev": "lapack-devel",
}
DEB_TO_ALPINE = {
    "libxml2-dev": "libxml2-dev",
    "libxslt1-dev": "libxslt-dev",
    "libssl-dev": "openssl-dev",
    "libffi-dev": "libffi-dev",
    "zlib1g-dev": "zlib-dev",
    "libjpeg-dev": "libjpeg-turbo-dev",
    "libpng-dev": "libpng-dev",
    "libyaml-dev": "yaml-dev",
    "libfreetype6-dev": "freetype-dev",
    "gfortran": "gfortran",
    "libopenblas-dev": "openblas-dev",
    "liblapack-dev": "lapack-dev",
}

# Chaquopy patches that commonly exist per package. If a file doesn't
# exist, the download 404s and is skipped at build time.
_CHAQUOPY_COMMON_PATCHES = ("chaquopy.patch", "android.patch", "fix.patch", "build.patch")


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

def log(message: str) -> None:
    print(f"[plan-wheels] {message}", flush=True)


def load_toml(path: Path) -> dict:
    if not path.is_file():
        raise FileNotFoundError(f"Required file not found: {path}")
    with path.open("rb") as f:
        return tomllib.load(f)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def python_version_from_tag(py_tag: str) -> tuple[int, int]:
    if not py_tag.startswith("cp"):
        raise ValueError(f"Unsupported Python tag: {py_tag}")
    digits = py_tag[2:]
    if len(digits) != 3 or not digits.isdigit():
        raise ValueError(f"Invalid CPython tag: {py_tag}")
    return int(digits[0]), int(digits[1:])


def py_tag_sort_key(tag: str) -> tuple[int, int]:
    m = re.match(r"cp(\d)(\d+)", tag)
    if m:
        return int(m.group(1)), int(m.group(2))
    return 0, 0


def index_supports(index: dict, target: dict) -> bool:
    s = index.get("supports", {})
    families = s.get("families")
    archs = s.get("archs")
    if families and target["family"] not in families:
        return False
    if archs and target["architecture"] not in archs:
        return False
    return True


def _serialize_env(env: dict) -> str:
    """Serialize env dict to cibuildwheel CIBW_ENVIRONMENT syntax."""
    if not env:
        return ""
    return " ".join(f"{k}={shlex.quote(str(v))}" for k, v in env.items())


# ---------------------------------------------------------------------------
# Marker environments and tag sets
# ---------------------------------------------------------------------------

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
        sys_platform, platform_system, os_name, machine = "win32", "Windows", "nt", "AMD64"
    elif family == "macos":
        sys_platform, platform_system, os_name, machine = "darwin", "Darwin", "posix", arch
    elif family == "android":
        sys_platform, platform_system, os_name, machine = "android", "Android", "posix", "aarch64"
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
    return [f"musllinux_{floor['major']}_{m}_{arch}"
            for m in range(floor["minor"], 0, -1)]


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
    ordered.extend(compatible_tags(python_version=pv, interpreter=py_tag, platforms=platforms))
    return list(dict.fromkeys(ordered))


# ---------------------------------------------------------------------------
# Runtime dependency resolution
# ---------------------------------------------------------------------------

def version_satisfies(version_text: str, specifier_text: str | None) -> bool:
    if not specifier_text:
        return True
    try:
        return SpecifierSet(specifier_text).contains(Version(version_text), prereleases=True)
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
        matching = [p for p in cands
                    if version_satisfies(p["version"], str(req.specifier))]
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
            matching = [c for c in cands
                        if version_satisfies(c["version"], dep.get("version"))]
            if not matching:
                warnings.append(
                    f"Unresolved locked dependency: {dep_name} "
                    f"({dep.get('version', '')})"
                )
                continue
            stack.extend(matching)

    result.sort(key=lambda i: (canonicalize_name(i["name"]), i["version"]))
    return result, warnings


# ---------------------------------------------------------------------------
# PyPI release inspection
# ---------------------------------------------------------------------------

def fetch_pypi_release(
    client: httpx.Client, package: str, version: str,
    base_url: str, retries: int,
) -> dict | None:
    url = f"{base_url.rstrip('/')}/{quote(package, safe='')}/{quote(version, safe='')}/json"
    for attempt in range(retries + 1):
        try:
            r = client.get(url)
            if r.status_code == 404:
                return None
            if r.status_code == 429 or r.status_code >= 500:
                if attempt < retries:
                    time.sleep(min(2 ** attempt, 10))
                    continue
            r.raise_for_status()
            return r.json()
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
                "reason": "Package release not found on PyPI."}

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
            compatible.append({
                "filename": fname, "url": file_info.get("url"),
                "sha256": digests.get("sha256"),
                "best_matching_tag": str(ordered[0]),
                "matching_tags": [str(t) for t in ordered],
            })
        elif ftype == "sdist":
            sdists.append({
                "filename": fname, "url": file_info.get("url"),
                "sha256": digests.get("sha256"),
            })

    if compatible:
        return {"status": "available", "compatible_wheels": compatible}
    if sdists:
        sdists.sort(key=lambda i: (not i["filename"].endswith(".tar.gz"), i["filename"]))
        return {"status": "build_required", "sdist": sdists[0]}
    return {"status": "source_unavailable",
            "reason": "No compatible upstream wheel and no sdist for this release."}


# ---------------------------------------------------------------------------
# External indexes
# ---------------------------------------------------------------------------

_SIMPLE_ANCHOR_RE = re.compile(
    r'<a\s+[^>]*href="([^"]+)"[^>]*>([^<]+)</a>', re.IGNORECASE,
)


def query_simple_index(client: httpx.Client, url: str) -> list[dict]:
    try:
        r = client.get(url, follow_redirects=True)
        if r.status_code == 404:
            return []
        r.raise_for_status()
    except httpx.HTTPError:
        return []
    out = []
    for href, text in _SIMPLE_ANCHOR_RE.findall(r.text):
        fname = html_module.unescape(text.strip())
        if not fname.endswith(".whl"):
            continue
        abs_url = urljoin(url, href)
        sha = None
        if "#" in abs_url:
            abs_url, frag = abs_url.split("#", 1)
            if frag.startswith("sha256="):
                sha = frag[len("sha256="):]
        out.append({"filename": fname, "url": abs_url, "sha256": sha})
    return out


def query_anaconda_api(client: httpx.Client, url: str) -> list[dict]:
    try:
        r = client.get(url, follow_redirects=True)
        if r.status_code == 404:
            return []
        r.raise_for_status()
        data = r.json()
    except (httpx.HTTPError, json.JSONDecodeError):
        return []
    out = []
    for fi in data.get("files", []):
        base = fi.get("basename", "")
        if not base.endswith(".whl"):
            continue
        attrs = fi.get("attrs") or {}
        if not str(attrs.get("subdir", "")).startswith("android_"):
            continue
        out.append({"filename": base, "url": fi.get("download_url"),
                    "sha256": attrs.get("sha256")})
    return out


def find_external_wheel(
    client: httpx.Client, package: str, version: str,
    target: dict, supported_tags: list,
) -> dict | None:
    supported = set(supported_tags)
    for index in EXTERNAL_INDEXES:
        if not index_supports(index, target):
            continue
        url = index["url_template"].format(package=quote(package, safe=""))
        if index["type"] == "simple_html":
            cands = query_simple_index(client, url)
        elif index["type"] == "anaconda_api":
            cands = query_anaconda_api(client, url)
        else:
            continue
        for cand in cands:
            try:
                wname, wver, _, wtags = parse_wheel_filename(cand["filename"])
            except Exception:
                continue
            if canonicalize_name(str(wname)) != canonicalize_name(package):
                continue
            if wver != Version(version):
                continue
            if not wtags.intersection(supported):
                continue
            return {"index": index["name"], **cand}
    return None


def download_wheel(
    client: httpx.Client, url: str, dest_dir: Path, expected_sha256: str | None,
) -> tuple[Path, str]:
    filename = url.rsplit("/", 1)[-1].split("?")[0].split("#")[0]
    if not filename.endswith(".whl") or "/" in filename or filename.startswith("."):
        raise ValueError(f"Unsafe wheel filename: {filename!r}")
    r = client.get(url, follow_redirects=True)
    r.raise_for_status()
    body = r.content
    digest = sha256_bytes(body)
    if expected_sha256 and digest.lower() != expected_sha256.lower():
        raise ValueError(f"SHA-256 mismatch for {filename}")
    dest = dest_dir / filename
    dest.write_bytes(body)
    return dest, digest


# ---------------------------------------------------------------------------
# Static analysis (Tier 3 fallback)
# ---------------------------------------------------------------------------

_SYSTEM_LIB_HINTS = {
    "libxml2": "libxml2-dev",
    "libxslt": "libxslt1-dev",
    "openssl": "libssl-dev",
    "libffi": "libffi-dev",
    "libjpeg": "libjpeg-dev",
    "libpng": "libpng-dev",
    "zlib": "zlib1g-dev",
    "libyaml": "libyaml-dev",
    "freetype": "libfreetype6-dev",
    "libavformat": "libavformat-dev",
    "portaudio": "portaudio19-dev",
}

_NATIVE_BACKENDS = ("maturin", "scikit_build", "scikit-build", "mesonpy", "setuptools_rust")


def _extract_archive(archive: Path, dest: Path) -> Path:
    dest.mkdir(parents=True, exist_ok=True)
    if tarfile.is_tarfile(archive):
        with tarfile.open(archive) as tf:
            for m in tf.getmembers():
                if m.name.startswith("/") or ".." in m.name.split("/"):
                    raise ValueError(f"Unsafe tar member: {m.name}")
            tf.extractall(dest, filter="data")
    elif zipfile.is_zipfile(archive):
        with zipfile.ZipFile(archive) as zf:
            for item in zf.infolist():
                name = item.filename
                if name.startswith("/") or ".." in name.split("/"):
                    raise ValueError(f"Unsafe zip member: {name}")
            zf.extractall(dest)
    else:
        raise ValueError("Unsupported source archive format")
    entries = list(dest.iterdir())
    return entries[0] if len(entries) == 1 and entries[0].is_dir() else dest


def _detect_extension_via_ast(setup_py: Path) -> bool:
    try:
        tree = ast.parse(setup_py.read_text(errors="replace"))
    except (SyntaxError, OSError):
        return False
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            fn = node.func
            name = fn.id if isinstance(fn, ast.Name) else (fn.attr if isinstance(fn, ast.Attribute) else "")
            if name == "Extension":
                return True
    return False


def _analyze_source_tree(source: Path) -> dict:
    info = {
        "backend": None, "requires": [], "native": False,
        "system_deps": [], "reason": "", "build_type": "pure_python",
        "confidence": "high", "env": {},
    }

    pyproject = source / "pyproject.toml"
    if pyproject.is_file():
        try:
            with pyproject.open("rb") as f:
                pp = tomllib.load(f)
            bs = pp.get("build-system", {})
            info["requires"] = list(bs.get("requires", []))
            info["backend"] = bs.get("build-backend")
        except Exception:
            pass

    backend_lc = (info["backend"] or "").lower()
    if any(b in backend_lc for b in _NATIVE_BACKENDS):
        info["native"] = True
        info["reason"] = f"native backend: {info['backend']}"

    if not info["native"] and info["requires"]:
        reqs = " ".join(info["requires"]).lower()
        if "cython" in reqs:
            info["native"] = True
            info["reason"] = "cython in build-system.requires"

    if not info["native"]:
        setup_py = source / "setup.py"
        if setup_py.is_file():
            if _detect_extension_via_ast(setup_py):
                info["native"] = True
                info["reason"] = "Extension() in setup.py"
            else:
                try:
                    text = setup_py.read_text(errors="replace")
                    if re.search(r"ext_modules\s*=\s*\[", text):
                        info["native"] = True
                        info["reason"] = "ext_modules in setup.py"
                except OSError:
                    pass

    text_blob = ""
    py_files = list(source.rglob("*.py"))[:80]
    for f in py_files:
        try:
            text_blob += f.read_text(errors="replace").lower()
        except OSError:
            continue
    for lib, pkg in _SYSTEM_LIB_HINTS.items():
        if lib in text_blob:
            info["system_deps"].append(pkg)
    info["system_deps"] = sorted(set(info["system_deps"]))

    info["build_type"] = "cibuildwheel" if info["native"] else "pure_python"
    info["confidence"] = "medium" if info["native"] else "high"
    if info["native"] and not info["backend"]:
        info["confidence"] = "low"
    return info


def probe_pure_build(source: Path, timeout: int = 180) -> tuple[bool, str]:
    with tempfile.TemporaryDirectory() as wh:
        env = dict(os.environ)
        env["PIP_DISABLE_PIP_VERSION_CHECK"] = "1"
        try:
            r = subprocess.run(
                [sys.executable, "-m", "pip", "wheel", "--no-deps", "--quiet",
                 "--wheel-dir", wh, str(source)],
                capture_output=True, text=True, timeout=timeout, env=env,
            )
        except subprocess.TimeoutExpired:
            return False, "probe timed out"
        if r.returncode != 0:
            return False, (r.stderr or "")[-500:]
        return True, ""


def analyze_sdist_url(
    client: httpx.Client, url: str, expected_sha256: str | None, do_probe: bool,
) -> dict:
    with tempfile.TemporaryDirectory(prefix="wheel-analysis-") as tmpdir:
        tmp = Path(tmpdir)
        archive = tmp / "sdist"
        try:
            r = client.get(url, follow_redirects=True, timeout=180)
            r.raise_for_status()
            archive.write_bytes(r.content)
            if expected_sha256:
                actual = sha256_bytes(archive.read_bytes())
                if actual.lower() != expected_sha256.lower():
                    raise ValueError("sdist SHA-256 mismatch")
            source = _extract_archive(archive, tmp / "src")
            info = _analyze_source_tree(source)
            if do_probe and info["build_type"] == "pure_python":
                ok, msg = probe_pure_build(source)
                if not ok:
                    info["confidence"] = "low"
                    info["reason"] = f"pure probe failed: {msg[:200]}"
            return info
        except Exception as exc:
            return {
                "build_type": "cibuildwheel", "confidence": "low",
                "reason": f"analysis failed: {exc}",
                "backend": None, "requires": [], "native": None,
                "system_deps": [], "env": {},
            }


# ─── RECIPE SOURCES: Chaquopy ────────────────────────────────────────────

def fetch_chaquopy_meta(client, package, version, retries=2):
    if yaml is None:
        return None
    pkg = package.lower()
    # Chaquopy uses versioned folders; also try unversioned for safety.
    candidates = [
        f"{pkg}-{version}",
        pkg,
        pkg.replace("-", "_"),
        f"{pkg.replace('-', '_')}-{version}",
    ]
    for name in candidates:
        url = CHAQUOPY_META_URL.format(package=name)
        try:
            r = client.get(url, follow_redirects=True, timeout=20)
            if r.status_code == 404:
                continue
            r.raise_for_status()
            meta = yaml.safe_load(r.text) or {}
            return {"recipe_name": name, "meta": meta}
        except httpx.HTTPError:
            continue
    return None

def _parse_req_string(spec: str) -> tuple[str, str | None]:
    spec = (spec or "").strip()
    if not spec:
        return "", None
    for sep in ("==", "=", " "):
        if sep in spec:
            name, _, version = spec.partition(sep)
            return name.strip(), version.strip() or None
    return spec, None


def _chaquopy_artifact_url(name: str, version: str | None) -> str | None:
    if not name.startswith("chaquopy-") or not version:
        return None
    tail = name[len("chaquopy-"):]
    return f"{CHAQUOPY_MAVEN_BASE}/chaquopy-{tail}/{version}/chaquopy-{tail}-{version}.tar.gz"


def _version_confidence(recipe_ver: str | None, lock_ver: str) -> str:
    """Map version proximity to confidence."""
    if not recipe_ver:
        return "low"
    if recipe_ver == lock_ver:
        return "high"
    try:
        rv = Version(recipe_ver)
        lv = Version(lock_ver)
        if rv.major != lv.major:
            return "low"
        if rv.minor != lv.minor:
            return "medium"
        return "medium" if rv.micro != lv.micro else "high"
    except Exception:
        return "low"


def translate_chaquopy_recipe(
    payload: dict, package: str, version: str, target: dict,
) -> dict | None:
    meta = payload.get("meta") or {}
    reqs = meta.get("requirements") or {}
    build_reqs = reqs.get("build") or []
    host_reqs = reqs.get("host") or []
    build_block = meta.get("build") or {}

    host_artifacts: list[dict] = []
    for spec in host_reqs:
        name, ver = _parse_req_string(spec)
        if not name:
            continue
        url = _chaquopy_artifact_url(name, ver)
        host_artifacts.append({
            "name": name,
            "version": ver,
            "artifact_url": url,
            "required": url is not None,  # only chaquopy-* are mandatory
        })

    build_artifacts: list[dict] = []
    for spec in build_reqs:
        name, ver = _parse_req_string(spec)
        if not name:
            continue
        url = _chaquopy_artifact_url(name, ver)
        build_artifacts.append({
            "name": name,
            "version": ver,
            "artifact_url": url,
            "required": False,  # informational; build toolchain usually preinstalled
        })

    env: dict[str, str] = {}
    for entry in build_block.get("script_env") or []:
        if "=" in entry:
            k, _, v = entry.partition("=")
            env[k.strip()] = v.strip()

    patches = [
        {"url": CHAQUOPY_PATCH_URL.format(package=payload["recipe_name"], patch=p),
         "filename": p}
        for p in _CHAQUOPY_COMMON_PATCHES
    ]

    meta_version = ((meta.get("package") or {}).get("version") or "").strip() or None
    confidence = _version_confidence(meta_version, version)

    return {
        "recipe_source": "chaquopy",
        "confidence": confidence,
        "host_requirements": host_artifacts,
        "build_requirements": build_artifacts,
        "patches": patches,
        "system_deps": [],
        "env": env,
        "cibw_before_all": None,
        "cibw_before_all_linux": None,
        "reason": (
            f"Chaquopy recipe ({payload['recipe_name']}"
            f"{', meta version ' + meta_version if meta_version else ''})"
        ),
        "build_type": "cibuildwheel",
    }


def try_chaquopy(
    client: httpx.Client, package: str, version: str, target: dict,
) -> dict | None:
    if target["family"] != "android":
        return None
    payload = fetch_chaquopy_meta(client, package, version)
    if not payload:
        return None
    return translate_chaquopy_recipe(payload, package, version, target)

# ─── RECIPE SOURCES: piwheels ────────────────────────────────────────────

def fetch_piwheels_json(
    client: httpx.Client, package: str, retries: int = 2,
) -> dict | None:
    url = PIWHEELS_JSON_URL.format(package=package.lower().replace("-", "_"))
    for attempt in range(retries + 1):
        try:
            r = client.get(url, follow_redirects=True, timeout=20)
            if r.status_code == 404:
                return None
            r.raise_for_status()
            return r.json()
        except (httpx.HTTPError, json.JSONDecodeError):
            if attempt >= retries:
                return None
            time.sleep(min(2 ** attempt, 5))
    return None


def translate_piwheels_recipe(
    data: dict, package: str, version: str, target: dict,
) -> dict | None:
    releases = data.get("releases") or {}
    release = releases.get(version) or {}
    files = release.get("files") or {}
    apt_deps: set[str] = set()
    for fi in files.values():
        for dep in (fi.get("apt_dependencies") or []):
            apt_deps.add(dep)
    if not apt_deps:
        return None

    if target["family"] == "manylinux":
        names = sorted(DEB_TO_RPM.get(d, d) for d in apt_deps)
        before_all_linux = "dnf install -y " + " ".join(names) + " || true"
    elif target["family"] == "musllinux":
        names = sorted(DEB_TO_ALPINE.get(d, d) for d in apt_deps)
        before_all_linux = "apk add " + " ".join(names) + " || true"
    else:
        return None

    return {
        "recipe_source": "piwheels",
        "confidence": "medium",
        "host_requirements": [],
        "build_requirements": [],
        "patches": [],
        "system_deps": names,
        "env": {},
        "cibw_before_all": None,
        "cibw_before_all_linux": before_all_linux,
        "reason": f"piwheels apt_dependencies ({len(apt_deps)} packages)",
        "build_type": "cibuildwheel",
    }


def try_piwheels(
    client: httpx.Client, package: str, version: str, target: dict,
) -> dict | None:
    if target["family"] not in ("manylinux", "musllinux"):
        return None
    data = fetch_piwheels_json(client, package)
    if not data:
        return None
    return translate_piwheels_recipe(data, package, version, target)


# ─── RESOLVER ────────────────────────────────────────────────────────────

def resolve_recipe(
    client: httpx.Client,
    package: str, version: str, target: dict,
    sdist_url: str, sdist_sha256: str | None,
    do_probe: bool,
    cache: dict[tuple[str, str], dict],
) -> dict:
    """Three-tier cascade: Chaquopy → piwheels → static analysis."""
    cache_key = (canonicalize_name(package), target["target"])
    if cache_key in cache:
        return cache[cache_key]

    r = try_chaquopy(client, package, version, target)
    if r is not None:
        log(f"Recipe: {package} → chaquopy ({r['confidence']})")
        cache[cache_key] = r
        return r

    r = try_piwheels(client, package, version, target)
    if r is not None:
        log(f"Recipe: {package} → piwheels ({r['confidence']})")
        cache[cache_key] = r
        return r

    info = analyze_sdist_url(client, sdist_url, sdist_sha256, do_probe)
    info["recipe_source"] = "static_analysis"
    info.setdefault("host_requirements", [])
    info.setdefault("build_requirements", [])
    info.setdefault("patches", [])
    info.setdefault("cibw_before_all", None)
    info.setdefault("cibw_before_all_linux", None)
    cache[cache_key] = info
    return info


# ---------------------------------------------------------------------------
# Plan assembly
# ---------------------------------------------------------------------------

def _dedupe_by_name(items: list[dict]) -> list[dict]:
    seen = set()
    out = []
    for item in items:
        name = item.get("name") or item.get("filename")
        if name in seen:
            continue
        seen.add(name)
        out.append(item)
    return out


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
        plan.append({
            "package": gap["package"], "version": gap["version"],
            "target": "pure_python", "build_type": "pure_python",
            "cibw_platform": "pure", "cibw_archs": "any",
            "runner": "ubuntu-latest",
            "py_tags": ["py3"], "cibw_build": "py3-none-any",
            "platform_floor": {"type": "any"},
            "source_url": gap.get("sdist_url"),
            "source_sha256": gap.get("sdist_sha256"),
            "confidence": gap.get("confidence", "high"),
            "reason": gap.get("reason", ""),
            "recipe_source": gap.get("recipe_source", "static_analysis"),
            "system_deps": gap.get("system_deps", []),
            "host_requirements_json": "[]",
            "build_requirements_json": "[]",
            "patches_json": "[]",
            "cibw_before_all": "",
            "cibw_before_all_linux": "",
            "cibw_environment_string": "",
            "batch": 1,
        })

    for gap in gaps:
        if gap.get("build_type") != "prebuilt":
            continue
        plan.append({
            "package": gap["package"], "version": gap["version"],
            "target": gap["target"], "build_type": "prebuilt",
            "cibw_platform": gap["cibw_platform"],
            "cibw_archs": gap["cibw_archs"], "runner": gap["runner"],
            "py_tags": [gap["py_tag"]], "cibw_build": "prebuilt",
            "platform_floor": gap.get("platform_floor"),
            "prebuilt_filename": gap.get("prebuilt_filename"),
            "prebuilt_sha256": gap.get("prebuilt_sha256"),
            "prebuilt_url": gap.get("prebuilt_url"),
            "prebuilt_source": gap.get("source"),
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
            "batch": 1,
        })

    groups: dict[tuple, dict[str, dict]] = defaultdict(dict)
    for gap in gaps:
        if gap.get("build_type") != "cibuildwheel":
            continue
        key = (gap["package"], gap["version"], gap["target"],
               gap["cibw_platform"], gap["cibw_archs"], gap["runner"])
        groups[key].setdefault(gap["py_tag"], gap)

    for key in sorted(groups):
        package, version, target, platform, arch, runner = key
        entries = groups[key]
        tags = sorted(entries, key=py_tag_sort_key)

        for offset in range(0, len(tags), max_tags):
            batch = tags[offset:offset + max_tags]
            selected = [entries[t] for t in batch]

            urls = {s.get("sdist_url") for s in selected if s.get("sdist_url")}
            hashes = {s.get("sdist_sha256") for s in selected if s.get("sdist_sha256")}
            if len(urls) > 1 or len(hashes) > 1:
                raise ValueError(f"Inconsistent sdist for {package}=={version}/{target}")

            if platform == "linux" and target.startswith(("manylinux", "musllinux")):
                prefix = "manylinux" if target.startswith("manylinux") else "musllinux"
                selector = " ".join(f"{t}-{prefix}_*" for t in batch)
            else:
                selector = " ".join(f"{t}-*" for t in batch)

            all_deps: set[str] = set()
            for s in selected:
                all_deps.update(s.get("system_deps") or [])
            confidences = [s.get("confidence", "high") for s in selected]
            worst = min(confidences, key=lambda c: {"low": 0, "medium": 1, "high": 2}.get(c, 2))

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
                (s.get("cibw_before_all") for s in selected if s.get("cibw_before_all")),
                "",
            )
            before_all_linux = next(
                (s.get("cibw_before_all_linux") for s in selected if s.get("cibw_before_all_linux")),
                "",
            )
            env = selected[0].get("env") or {}

            plan.append({
                "package": package, "version": version, "target": target,
                "build_type": "cibuildwheel",
                "cibw_platform": platform, "cibw_archs": arch, "runner": runner,
                "py_tags": batch, "cibw_build": selector,
                "platform_floor": selected[0].get("platform_floor"),
                "source_url": next(iter(urls), None),
                "source_sha256": next(iter(hashes), None),
                "confidence": worst,
                "reason": selected[0].get("reason", ""),
                "recipe_source": selected[0].get("recipe_source", "static_analysis"),
                "system_deps": sorted(all_deps),
                "host_requirements_json": json.dumps(host_reqs, separators=(",", ":")),
                "build_requirements_json": json.dumps(build_reqs, separators=(",", ":")),
                "patches_json": json.dumps(patches, separators=(",", ":")),
                "cibw_before_all": before_all or "",
                "cibw_before_all_linux": before_all_linux or "",
                "cibw_environment_string": _serialize_env(env),
                "batch": offset // max_tags + 1,
            })

    return plan


# ---------------------------------------------------------------------------
# Main discovery
# ---------------------------------------------------------------------------

def run_plan(args: argparse.Namespace) -> tuple[list[dict], dict, list[dict]]:
    project_data = load_toml(args.project)
    lock_data = load_toml(args.lock)
    project = project_data.get("project", {})
    if not project:
        raise ValueError(f"No [project] table in {args.project}")
    if "dependencies" in (project.get("dynamic") or []):
        log("WARNING: [project] declares dependencies as dynamic; resolution may be incomplete")

    if args.download_dir is not None:
        args.download_dir.mkdir(parents=True, exist_ok=True)

    targets = []
    for base in TARGETS:
        t = dict(base)
        if t["family"] == "android":
            t["android_api_level"] = args.android_api_level
            t["platform_floor"] = {"type": "android", "api_level": args.android_api_level}
        targets.append(t)

    gaps: list[dict] = []
    available: list[dict] = []
    unbuildable: list[dict] = []
    lock_warnings: list[dict] = []
    rejected: list[str] = []

    release_cache: dict[tuple[str, str], dict | None] = {}
    recipe_cache: dict[tuple[str, str], dict] = {}  # (pkg, target) → recipe
    prebuilt_files: dict[str, tuple[Path, str, str]] = {}

    headers = {"User-Agent": "Open-News-plan-wheels/3.0", "Accept": "*/*"}

    with httpx.Client(timeout=args.timeout, follow_redirects=True, headers=headers) as client:
        for target in targets:
            if args.limit and len(release_cache) >= args.limit:
                log(f"Reached --limit ({args.limit} unique packages)")
                break

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
                    if args.limit and len(release_cache) >= args.limit and (name_norm, version) not in release_cache:
                        continue

                    cache_key = (name_norm, version)
                    if cache_key not in release_cache:
                        log(f"PyPI: {package}=={version}")
                        release_cache[cache_key] = fetch_pypi_release(
                            client, package, version, args.pypi_base_url, args.retries,
                        )

                    result = inspect_release(package, version, release_cache[cache_key], supported)
                    base = {
                        "package": package, "version": version,
                        "target": target["target"], "py_tag": py_tag,
                        "compatibility_profile": target["family"],
                        "platform_floor": target.get("platform_floor"),
                    }

                    if result["status"] == "available":
                        available.append({
                            **base, "status": "available", "source": "pypi",
                            "compatible_wheels": result["compatible_wheels"],
                        })
                        continue

                    if args.download_dir is not None:
                        cand = find_external_wheel(client, package, version, target, supported)
                        if cand is not None:
                            try:
                                url = cand["url"]
                                if url not in prebuilt_files:
                                    local, sha = download_wheel(
                                        client, url, args.download_dir, cand.get("sha256"),
                                    )
                                    prebuilt_files[url] = (local, sha, cand["index"])
                                    log(f"Prebuilt {local.name} from {cand['index']}")
                                local, sha, idx = prebuilt_files[url]
                            except Exception as exc:
                                log(f"External download failed for {package}=={version}: {exc}")
                            else:
                                gaps.append({
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
                                    "sdist_filename": None, "sdist_url": None, "sdist_sha256": None,
                                    "confidence": "high",
                                    "reason": f"prebuilt from {idx}",
                                    "recipe_source": "external_index",
                                    "system_deps": [], "env": {},
                                    "host_requirements": [], "build_requirements": [],
                                    "patches": [], "cibw_before_all": None,
                                    "cibw_before_all_linux": None,
                                })
                                continue

                    if result["status"] == "source_unavailable":
                        unbuildable.append({
                            **base, "status": "source_unavailable",
                            "reason": result["reason"],
                        })
                        continue

                    sdist = result["sdist"]
                    recipe = resolve_recipe(
                        client, package, version, target,
                        sdist["url"], sdist.get("sha256"),
                        not args.no_probe, recipe_cache,
                    )

                    if recipe["build_type"] == "pure_python":
                        gaps.append({
                            "package": package, "version": version,
                            "target": "pure_python", "py_tag": "py3",
                            "compatibility_profile": "pure_python",
                            "platform_floor": {"type": "any"},
                            "build_type": "pure_python",
                            "cibw_platform": "pure", "cibw_archs": "any",
                            "runner": "ubuntu-latest",
                            "cibw_build_id": "pure",
                            "status": "build_required",
                            "source": "pypi_sdist",
                            "sdist_filename": sdist["filename"],
                            "sdist_url": sdist["url"],
                            "sdist_sha256": sdist.get("sha256"),
                            "confidence": recipe["confidence"],
                            "reason": recipe.get("reason") or "pure-python sdist",
                            "recipe_source": recipe.get("recipe_source", "static_analysis"),
                            "system_deps": recipe.get("system_deps", []),
                            "host_requirements": recipe.get("host_requirements", []),
                            "build_requirements": recipe.get("build_requirements", []),
                            "patches": recipe.get("patches", []),
                            "cibw_before_all": recipe.get("cibw_before_all"),
                            "cibw_before_all_linux": recipe.get("cibw_before_all_linux"),
                            "env": recipe.get("env", {}),
                        })
                    else:
                        cibw_id = (f"{py_tag}-{target['build_pattern']}"
                                   if target["family"] in ("manylinux", "musllinux")
                                   else f"{py_tag}-*")
                        gaps.append({
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
                            "confidence": recipe["confidence"],
                            "reason": recipe.get("reason") or "native sdist",
                            "recipe_source": recipe.get("recipe_source", "static_analysis"),
                            "system_deps": recipe.get("system_deps", []),
                            "host_requirements": recipe.get("host_requirements", []),
                            "build_requirements": recipe.get("build_requirements", []),
                            "patches": recipe.get("patches", []),
                            "cibw_before_all": recipe.get("cibw_before_all"),
                            "cibw_before_all_linux": recipe.get("cibw_before_all_linux"),
                            "env": recipe.get("env", {}),
                        })

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

    prebuilt_unique = len({g["prebuilt_filename"] for g in gaps
                           if g.get("build_type") == "prebuilt" and g.get("prebuilt_filename")})

    recipe_sources: dict[str, int] = defaultdict(int)
    for g in gaps:
        recipe_sources[g.get("recipe_source", "static_analysis")] += 1

    report = {
        "schema_version": 8,
        "project": project_name,
        "project_version": project_version,
        "android_api_level": args.android_api_level,
        "policy": {
            "python_versions": list(PYTHON_VERSIONS),
            "android_python_versions": list(ANDROID_PYTHON_VERSIONS),
            "external_indexes": [i["name"] for i in EXTERNAL_INDEXES],
            "recipe_tiers": ["chaquopy", "piwheels", "static_analysis"],
            "hardcoded_packages": False,
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
            "rejected_count": len(rejected),
            "pure_python_count": sum(1 for g in gaps if g.get("build_type") == "pure_python"),
            "cibuildwheel_count": sum(1 for g in gaps if g.get("build_type") == "cibuildwheel"),
            "prebuilt_count": sum(1 for g in gaps if g.get("build_type") == "prebuilt"),
            "prebuilt_unique_files": prebuilt_unique,
            "low_confidence_count": sum(1 for g in gaps if g.get("confidence") == "low"),
            "recipe_sources": dict(recipe_sources),
        },
        "available": available,
        "gaps": gaps,
        "source_unavailable": unbuildable,
        "lock_warnings": lock_warnings,
        "rejected": rejected,
    }
    return plan, report, gaps


# ---------------------------------------------------------------------------
# Output writing
# ---------------------------------------------------------------------------

def write_github_outputs(args: argparse.Namespace, plan: list[dict], report: dict) -> None:
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


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Plan dependency-wheel builds (three-tier recipe resolution).",
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
    p.add_argument("--download-dir", type=Path, default=None)
    p.add_argument("--no-probe", action="store_true")
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--only", type=str, default=None)
    p.add_argument("--no-recipe-tiers", action="store_true",
                   help="Disable Chaquopy/piwheels lookups (static-analysis only).")
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
        args.discovery_output = args.output.with_name(f"{args.output.stem}-discovery.json")
    if args.no_recipe_tiers:
        # monkey-patch to skip tiers
        global try_chaquopy, try_piwheels
        try_chaquopy = lambda *a, **k: None
        try_piwheels = lambda *a, **k: None
    if yaml is None:
        log("NOTE: pyyaml not installed; Chaquopy tier disabled")

    try:
        plan, report, gaps = run_plan(args)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.plan_output.parent.mkdir(parents=True, exist_ok=True)
        args.discovery_output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(gaps, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        args.plan_output.write_text(json.dumps(plan, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        args.discovery_output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        write_github_outputs(args, plan, report)

        s = report["summary"]
        log(f"Plan entries: {len(plan)}")
        log(f"  buildable:   {sum(1 for p in plan if p['build_type'] != 'prebuilt')}")
        log(f"  prebuilt:    {sum(1 for p in plan if p['build_type'] == 'prebuilt')}")
        log(f"  pure_python: {s['pure_python_count']}")
        log(f"  cibuildwheel:{s['cibuildwheel_count']}")
        log(f"  low-conf:    {s['low_confidence_count']}")
        log(f"Recipe sources: {s['recipe_sources']}")
        log(f"Upstream covered:   {s['upstream_wheel_count']}")
        log(f"Source unavailable: {s['source_unavailable_count']}")
        return 0
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())