"""Reads uv.lock + pyproject.toml, checks PyPI for existing wheels, emits a
GHA matrix of only the (package, target, py_tag) combinations that are
actually missing — scoped to runtime dependencies only.

Confirmed via `cibuildwheel --platform android --help`:
  - Android's only supported --archs value is `arm64_v8a` (no armv7/x86_64/x86).
  - Android build identifiers start at cp313 (CPython's Android port floor).
"""
import json
import os
import re
import tomllib

import httpx

# ----------------------------------------------------------------------
# Targets: (label, cibw_platform, cibw_archs, runner, pypi_tag_hint, py_tags)
# ----------------------------------------------------------------------
TARGETS = [
    ("manylinux_x86_64",  "linux",   "x86_64",    "ubuntu-latest",  "manylinux",
     ["cp310", "cp311", "cp312", "cp313"]),
    ("manylinux_aarch64", "linux",   "aarch64",   "ubuntu-latest",  "manylinux",
     ["cp310", "cp311", "cp312", "cp313"]),
    ("musllinux_x86_64",  "linux",   "x86_64",    "ubuntu-latest",  "musllinux",
     ["cp310", "cp311", "cp312", "cp313"]),
    ("macosx_arm64",      "macos",   "arm64",     "macos-latest",   "macosx",
     ["cp310", "cp311", "cp312", "cp313"]),
    ("macosx_x86_64",     "macos",   "x86_64",    "macos-latest",   "macosx",
     ["cp310", "cp311", "cp312", "cp313"]),
    ("win_amd64",         "windows", "AMD64",     "windows-latest", "win_amd64",
     ["cp310", "cp311", "cp312", "cp313"]),
    # Android: arm64_v8a is the ONLY supported --archs value for this
    # platform in cibuildwheel today, and cp313 is CPython-on-Android's
    # actual floor — confirmed by hand, not assumed. Do not add
    # armv7/x86_64/x86 rows here until cibuildwheel actually supports them.
    ("android_arm64_v8a", "android", "arm64_v8a", "ubuntu-latest",  "android_24_arm64_v8a",
     ["cp313"]),
]

ABI3_RE = re.compile(r"-(cp3\d+)-abi3-")


# ----------------------------------------------------------------------
# Runtime dependency graph (excludes dev/test tooling)
# ----------------------------------------------------------------------
def load_lock():
    with open("uv.lock", "rb") as f:
        return tomllib.load(f)


def get_runtime_roots():
    with open("pyproject.toml", "rb") as f:
        proj = tomllib.load(f)["project"]
    deps = proj.get("dependencies", [])
    names = set()
    for d in deps:
        name = d.split(";")[0].split("=")[0].split(">")[0].split("<")[0].split("[")[0].strip()
        names.add(name.lower().replace("_", "-"))
    return names


def walk_dependency_graph(lock, roots):
    pkg_by_name = {p["name"].lower(): p for p in lock["package"]}
    visited = set()
    frontier = list(roots)
    while frontier:
        name = frontier.pop()
        if name in visited:
            continue
        visited.add(name)
        pkg = pkg_by_name.get(name)
        if pkg is None:
            continue
        for dep in pkg.get("dependencies", []):
            dep_name = dep["name"].lower()
            if dep_name not in visited:
                frontier.append(dep_name)
    return visited


def load_compiled_packages():
    lock = load_lock()
    roots = get_runtime_roots()
    reachable = walk_dependency_graph(lock, roots)

    compiled = {}
    for pkg in lock["package"]:
        name = pkg["name"].lower()
        if name not in reachable:
            continue
        wheels = pkg.get("wheels", [])
        is_pure = bool(wheels) and all("-none-any.whl" in w["url"] for w in wheels)
        if wheels and not is_pure:
            compiled[pkg["name"]] = pkg["version"]
    return compiled


# ----------------------------------------------------------------------
# PyPI wheel-coverage check
# ----------------------------------------------------------------------
def existing_filenames(pkg_name, pkg_version):
    resp = httpx.get(f"https://pypi.org/pypi/{pkg_name}/{pkg_version}/json", timeout=20)
    if resp.status_code != 200:
        return set()
    return {f["filename"] for f in resp.json().get("urls", [])}


def wheel_covers_py_tag(filename: str, py_tag: str, target_hint: str) -> bool:
    if target_hint not in filename:
        return False
    if "-none-any.whl" in filename or "py3-none" in filename:
        return True
    abi3_match = ABI3_RE.search(filename)
    if abi3_match:
        min_ver = int(abi3_match.group(1)[2:])
        target_ver = int(py_tag[2:])
        return target_ver >= min_ver
    return py_tag in filename


# ----------------------------------------------------------------------
# Matrix generation
# ----------------------------------------------------------------------
def main():
    compiled = load_compiled_packages()
    seen = set()
    matrix = []

    for pkg_name, version in compiled.items():
        existing = existing_filenames(pkg_name, version)
        for target_name, platform_, archs, runner, tag_hint, py_tags in TARGETS:
            for py_tag in py_tags:
                covered = any(
                    wheel_covers_py_tag(fn, py_tag, tag_hint) for fn in existing
                )
                if covered:
                    continue
                key = (pkg_name, platform_, archs, py_tag)
                if key in seen:
                    continue
                seen.add(key)
                matrix.append({
                    "package": pkg_name,
                    "version": version,
                    "cibw_platform": platform_,
                    "cibw_archs": archs,
                    "cibw_build_id": f"{py_tag}-*",
                    "py_tag": py_tag,   # clean, no wildcard — safe for artifact names
                    "runner": runner,
                })

    has_gaps = "true" if matrix else "false"
    gh_out = os.environ.get("GITHUB_OUTPUT")

    if gh_out:
        with open(gh_out, "a") as f:
            f.write(f"matrix={json.dumps(matrix)}\n")
            f.write(f"has_gaps={has_gaps}\n")
    else:
        print("(GITHUB_OUTPUT not set — running locally, skipping GHA output write)")

    print(f"Found {len(matrix)} missing (package, target) combinations.")
    for m in matrix:
        print(" -", m)


if __name__ == "__main__":
    main()