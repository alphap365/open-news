"""Reads uv.lock + pyproject.toml, checks PyPI for existing wheels, emits a
GHA matrix of only the (package, target, py_tag) combinations that are
actually missing — scoped to runtime dependencies only.

Android tag note:
  PyPI uses `android_<api>_<arch>` filenames (e.g. `android_21_arm64_v8a`).
  The API level is forward-compatible at runtime, so we match on the arch
  token alone rather than pinning an API level.

Coverage matching is arch-aware: a `manylinux_x86_64` wheel does NOT
satisfy a `manylinux_aarch64` target. The earlier family-prefix match
("manylinux") produced a silently incomplete matrix.
"""
from __future__ import annotations

import json
import os
import re
import sys
import tomllib

import httpx

# ----------------------------------------------------------------------
# Targets: (label, cibw_platform, cibw_archs, runner, build_id_hint, py_tags)
#   build_id_hint is used only to compose cibuildwheel --build IDs.
#   Coverage matching uses _ARCH_TOKENS[label] instead.
# ----------------------------------------------------------------------
TARGETS = [
    ("manylinux_x86_64",  "linux",   "x86_64",    "ubuntu-latest",  "manylinux",
     ["cp310", "cp311", "cp312", "cp313", "cp314"]),
    ("manylinux_aarch64", "linux",   "aarch64",   "ubuntu-latest",  "manylinux",
     ["cp310", "cp311", "cp312", "cp313", "cp314"]),
    ("musllinux_x86_64",  "linux",   "x86_64",    "ubuntu-latest",  "musllinux",
     ["cp310", "cp311", "cp312", "cp313", "cp314"]),
    ("musllinux_aarch64", "linux",   "aarch64",   "ubuntu-latest",  "musllinux",
     ["cp310", "cp311", "cp312", "cp313", "cp314"]),
    ("macosx_arm64",      "macos",   "arm64",     "macos-latest",   "macosx",
     ["cp310", "cp311", "cp312", "cp313", "cp314"]),
    ("macosx_x86_64",     "macos",   "x86_64",    "macos-latest",   "macosx",
     ["cp310", "cp311", "cp312", "cp313", "cp314"]),
    ("win_amd64",         "windows", "AMD64",     "windows-latest", "win_amd64",
     ["cp310", "cp311", "cp312", "cp313", "cp314"]),
    ("android_arm64_v8a", "android", "arm64_v8a", "ubuntu-latest",  "arm64_v8a",
     ["cp313", "cp314"]),
]

# Per-target wheel-filename pattern. Anchored with (?=[-.]) so
# manylinux_x86_64 cannot match manylinux_aarch64 (and vice versa).
_ARCH_TOKENS = {
    "manylinux_x86_64": re.compile(
        r"(?:^|[-.])(?:manylinux1|manylinux2010|manylinux2014|manylinux_\d+_\d+)_x86_64(?=[-.])"
    ),
    "manylinux_aarch64": re.compile(
        r"(?:^|[-.])(?:manylinux2014|manylinux_\d+_\d+)_aarch64(?=[-.])"
    ),
    "musllinux_x86_64": re.compile(
        r"(?:^|[-.])musllinux_\d+_\d+_x86_64(?=[-.])"
    ),
    "musllinux_aarch64": re.compile(
        r"(?:^|[-.])musllinux_\d+_\d+_aarch64(?=[-.])"
    ),
    # universal2 covers both Apple silicon and Intel.
    "macosx_arm64": re.compile(
        r"(?:^|[-.])macosx_\d+_\d+_(?:arm64|universal2)(?=[-.])"
    ),
    "macosx_x86_64": re.compile(
        r"(?:^|[-.])macosx_\d+_\d+_(?:x86_64|universal2|intel)(?=[-.])"
    ),
    "win_amd64": re.compile(r"(?:^|[-.])win_amd64(?=[-.])"),
    "android_arm64_v8a": re.compile(r"(?:^|[-.])android_\d+_arm64_v8a(?=[-.])"),
}

ABI3_RE = re.compile(r"-(cp\d+)-abi3-")
_REQ_NAME_RE = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)")


def cibw_build_id_for(platform_: str, hint: str, py_tag: str) -> str:
    return f"{py_tag}-{hint}_*" if platform_ == "linux" else f"{py_tag}-*"


# ----------------------------------------------------------------------
# Runtime dependency graph
# ----------------------------------------------------------------------
def _norm(name: str) -> str:
    """PEP 503 name normalisation: Foo_Bar, foo.bar, foo-bar -> foo-bar."""
    return re.sub(r"[-_.]+", "-", name).lower()


def _dep_name_from_requirement(spec: str) -> str | None:
    """Extract the project name from a PEP 508 requirement string.

    Handles `foo`, `foo>=1.0`, `foo[extra]>=1.0`, `foo!=1.0`, `foo~=1.0`,
    `foo===1.0`, `foo @ https://...`, `foo; python_version<"3.10"`.
    """
    head = spec.split(";", 1)[0].split("[", 1)[0].strip()
    m = _REQ_NAME_RE.match(head)
    return m.group(1) if m else None


def load_lock() -> dict:
    with open("uv.lock", "rb") as f:
        return tomllib.load(f)


def get_runtime_roots() -> set[str]:
    with open("pyproject.toml", "rb") as f:
        proj = tomllib.load(f)["project"]
    names = set()
    for dep in proj.get("dependencies", []):
        name = _dep_name_from_requirement(dep)
        if name:
            names.add(_norm(name))
    return names


def walk_dependency_graph(lock: dict, roots: set[str]) -> set[str]:
    pkg_by_name = {_norm(p["name"]): p for p in lock["package"]}
    visited: set[str] = set()
    frontier = list(roots)
    while frontier:
        name = _norm(frontier.pop())
        if name in visited:
            continue
        visited.add(name)
        pkg = pkg_by_name.get(name)
        if pkg is None:
            continue
        for dep in pkg.get("dependencies", []):
            dep_name = _norm(dep["name"])
            if dep_name not in visited:
                frontier.append(dep_name)
    return visited


def load_compiled_packages() -> dict[str, str]:
    """Returns {name: version} for reachable deps that are NOT pure-Python.

    Includes sdist-only packages (wheels == []) — they're the most
    worthwhile candidates for wheel building.
    """
    lock = load_lock()
    reachable = walk_dependency_graph(lock, get_runtime_roots())

    compiled: dict[str, str] = {}
    for pkg in lock["package"]:
        if _norm(pkg["name"]) not in reachable:
            continue
        wheels = pkg.get("wheels", [])
        is_pure = bool(wheels) and all("-none-any.whl" in w["url"] for w in wheels)
        if not is_pure:
            compiled[pkg["name"]] = pkg["version"]
    return compiled


# ----------------------------------------------------------------------
# PyPI wheel-coverage check
# ----------------------------------------------------------------------
def existing_filenames(pkg_name: str, pkg_version: str) -> set[str]:
    """Return PyPI filenames for this version. 404 -> empty set;
    any other non-2xx raises (never confuse a 5xx with 'not published')."""
    resp = httpx.get(
        f"https://pypi.org/pypi/{pkg_name}/{pkg_version}/json",
        timeout=20,
        headers={"User-Agent": "open-news-wheel-gaps/1.1"},
    )
    if resp.status_code == 404:
        return set()
    resp.raise_for_status()
    return {f["filename"] for f in resp.json().get("urls", [])}


def _py_ver(tag: str) -> tuple[int, int] | None:
    """cp312 -> (3, 12); cp39 -> (3, 9). None for non-cp tags."""
    m = re.match(r"cp(\d)(\d+)$", tag)
    return (int(m.group(1)), int(m.group(2))) if m else None


def wheel_covers_py_tag(filename: str, py_tag: str, target_name: str) -> bool:
    """Does `filename` provide `py_tag` for `target_name`?

    Order matters:
      1. Pure-Python wheels cover every target.
      2. Target-specific arch pattern MUST match.
      3. abi3 wheels cover the ABI floor version and every later minor.
      4. Otherwise the exact cp tag must be present.
    """
    if "-none-any.whl" in filename or "py3-none" in filename:
        return True

    pat = _ARCH_TOKENS.get(target_name)
    if pat is None or not pat.search(filename):
        return False

    abi3 = ABI3_RE.search(filename)
    if abi3:
        floor = _py_ver(abi3.group(1))
        want = _py_ver(py_tag)
        return bool(floor and want and want >= floor)

    return py_tag in filename


# ----------------------------------------------------------------------
# Matrix generation
# ----------------------------------------------------------------------
def main() -> int:
    try:
        compiled = load_compiled_packages()
    except FileNotFoundError as exc:
        print(f"Missing lockfile or pyproject: {exc}", file=sys.stderr)
        return 1

    seen: set[tuple[str, str, str, str]] = set()
    matrix: list[dict] = []

    for pkg_name, version in compiled.items():
        try:
            existing = existing_filenames(pkg_name, version)
        except Exception as exc:
            print(f"PyPI lookup failed for {pkg_name}=={version}: {exc}", file=sys.stderr)
            return 1

        for target_name, platform_, archs, runner, hint, py_tags in TARGETS:
            for py_tag in py_tags:
                if any(wheel_covers_py_tag(fn, py_tag, target_name) for fn in existing):
                    continue
                key = (pkg_name, platform_, archs, py_tag)
                if key in seen:
                    continue
                seen.add(key)
                matrix.append({
                    "package": pkg_name,
                    "version": version,
                    "target": target_name,
                    "cibw_platform": platform_,
                    "cibw_archs": archs,
                    "cibw_build_id": cibw_build_id_for(platform_, hint, py_tag),
                    "py_tag": py_tag,
                    "runner": runner,
                })

    has_gaps = "true" if matrix else "false"
    gh_out = os.environ.get("GITHUB_OUTPUT")

    if gh_out:
        with open(gh_out, "a", encoding="utf-8") as f:
            f.write(f"matrix={json.dumps(matrix)}\n")
            f.write(f"has_gaps={has_gaps}\n")
    else:
        print("(GITHUB_OUTPUT not set — running locally, skipping GHA output write)")

    print(f"Found {len(matrix)} missing (package, target, py_tag) combinations.")
    for m in matrix:
        print(" -", m)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())