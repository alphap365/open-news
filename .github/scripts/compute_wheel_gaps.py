"""Detect missing third-party dependency wheels.

Reads uv.lock and pyproject.toml, traverses runtime dependencies, and checks
PyPI for wheel coverage across supported platform/Python combinations.

Responsibilities:
    - Identify reachable compiled dependencies.
    - Check existing PyPI wheel coverage.
    - Emit missing combinations as JSON.
    - Optionally expose the matrix through GitHub Actions outputs.

This script does not decide how a package should be built.
That is the responsibility of plan_wheel_build.py.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib

import httpx


USER_AGENT = "open-news-wheel-gap-detector/1.2"

TARGETS = [
    (
        "manylinux_x86_64", "linux", "x86_64", "ubuntu-latest",
        "manylinux", ["cp310", "cp311", "cp312", "cp313", "cp314"],
    ),
    (
        "manylinux_aarch64", "linux", "aarch64", "ubuntu-latest",
        "manylinux", ["cp310", "cp311", "cp312", "cp313", "cp314"],
    ),
    (
        "musllinux_x86_64", "linux", "x86_64", "ubuntu-latest",
        "musllinux", ["cp310", "cp311", "cp312", "cp313", "cp314"],
    ),
    (
        "musllinux_aarch64", "linux", "aarch64", "ubuntu-latest",
        "musllinux", ["cp310", "cp311", "cp312", "cp313", "cp314"],
    ),
    (
        "macosx_arm64", "macos", "arm64", "macos-latest",
        "macosx", ["cp310", "cp311", "cp312", "cp313", "cp314"],
    ),
    (
        "macosx_x86_64", "macos", "x86_64", "macos-latest",
        "macosx", ["cp310", "cp311", "cp312", "cp313", "cp314"],
    ),
    (
        "win_amd64", "windows", "AMD64", "windows-latest",
        "win_amd64", ["cp310", "cp311", "cp312", "cp313", "cp314"],
    ),
    (
        "android_arm64_v8a", "android", "arm64_v8a", "ubuntu-latest",
        "arm64_v8a", ["cp313", "cp314"],
    ),
]

_ARCH_TOKENS = {
    "manylinux_x86_64": re.compile(
        r"(?:^|[-.])(?:manylinux1|manylinux2010|manylinux2014|"
        r"manylinux_\d+_\d+)_x86_64(?=[-.])"
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
    "macosx_arm64": re.compile(
        r"(?:^|[-.])macosx_\d+_\d+_(?:arm64|universal2)(?=[-.])"
    ),
    "macosx_x86_64": re.compile(
        r"(?:^|[-.])macosx_\d+_\d+_(?:x86_64|universal2|intel)(?=[-.])"
    ),
    "win_amd64": re.compile(r"(?:^|[-.])win_amd64(?=[-.])"),
    "android_arm64_v8a": re.compile(
        r"(?:^|[-.])android_\d+_arm64_v8a(?=[-.])"
    ),
}

ABI3_RE = re.compile(r"-(cp\d+)-abi3-")
REQ_NAME_RE = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)")


def normalize_name(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def dependency_name(requirement: str) -> str | None:
    head = requirement.split(";", 1)[0].split("[", 1)[0].strip()
    match = REQ_NAME_RE.match(head)
    return match.group(1) if match else None


def load_toml(path: str) -> dict[str, Any]:
    with open(path, "rb") as file:
        return tomllib.load(file)


def load_runtime_roots() -> set[str]:
    project = load_toml("pyproject.toml")["project"]

    roots = set()
    for requirement in project.get("dependencies", []):
        name = dependency_name(requirement)
        if name:
            roots.add(normalize_name(name))

    return roots


def walk_dependency_graph(
    lock: dict[str, Any],
    roots: set[str],
) -> set[str]:
    packages = {
        normalize_name(package["name"]): package
        for package in lock.get("package", [])
    }

    visited: set[str] = set()
    pending = list(roots)

    while pending:
        name = normalize_name(pending.pop())

        if name in visited:
            continue

        visited.add(name)

        package = packages.get(name)
        if package is None:
            continue

        for dependency in package.get("dependencies", []):
            dependency_name_ = normalize_name(dependency["name"])

            if dependency_name_ not in visited:
                pending.append(dependency_name_)

    return visited


def load_compiled_packages() -> list[dict[str, str]]:
    lock = load_toml("uv.lock")
    reachable = walk_dependency_graph(lock, load_runtime_roots())

    compiled = []

    for package in lock.get("package", []):
        name = package["name"]

        if normalize_name(name) not in reachable:
            continue

        wheels = package.get("wheels", [])

        is_pure_python = (
            bool(wheels)
            and all(
                "-none-any.whl" in wheel.get("url", "")
                for wheel in wheels
            )
        )

        if not is_pure_python:
            compiled.append({
                "package": name,
                "version": package["version"],
            })

    return compiled


def existing_filenames(
    client: httpx.Client,
    package: str,
    version: str,
    retries: int = 3,
) -> set[str]:
    url = f"https://pypi.org/pypi/{package}/{version}/json"

    for attempt in range(retries):
        try:
            response = client.get(url)

            if response.status_code == 404:
                return set()

            response.raise_for_status()

            return {
                item["filename"]
                for item in response.json().get("urls", [])
            }

        except httpx.HTTPError:
            if attempt + 1 == retries:
                raise

            time.sleep(2 ** attempt)

    return set()


def python_version(tag: str) -> tuple[int, int] | None:
    match = re.fullmatch(r"cp(\d)(\d+)", tag)

    if not match:
        return None

    return int(match.group(1)), int(match.group(2))


def wheel_covers_python(
    filename: str,
    python_tag: str,
    target: str,
) -> bool:
    if "-none-any.whl" in filename or "py3-none" in filename:
        return True

    pattern = _ARCH_TOKENS.get(target)

    if pattern is None or not pattern.search(filename):
        return False

    abi3 = ABI3_RE.search(filename)

    if abi3:
        floor = python_version(abi3.group(1))
        requested = python_version(python_tag)

        return bool(
            floor
            and requested
            and requested >= floor
        )

    # Wheel filenames contain the interpreter tag as a dot-separated field.
    # Checking the filename field avoids accidental substring matches.
    wheel_parts = filename[:-4].split("-")

    return len(wheel_parts) >= 5 and python_tag in wheel_parts[2].split(".")


def cibw_build_id(
    platform: str,
    hint: str,
    python_tag: str,
) -> str:
    if platform == "linux":
        return f"{python_tag}-{hint}_*"

    return f"{python_tag}-*"


def detect_gaps() -> list[dict[str, str]]:
    packages = load_compiled_packages()
    matrix: list[dict[str, str]] = []

    seen: set[tuple[str, str, str, str]] = set()

    with httpx.Client(
        timeout=30,
        headers={"User-Agent": USER_AGENT},
        follow_redirects=True,
    ) as client:

        for package in packages:
            name = package["package"]
            version = package["version"]

            filenames = existing_filenames(client, name, version)

            for (
                target,
                platform,
                archs,
                runner,
                hint,
                python_tags,
            ) in TARGETS:

                for python_tag in python_tags:
                    covered = any(
                        wheel_covers_python(
                            filename,
                            python_tag,
                            target,
                        )
                        for filename in filenames
                    )

                    if covered:
                        continue

                    key = (
                        normalize_name(name),
                        target,
                        python_tag,
                        version,
                    )

                    if key in seen:
                        continue

                    seen.add(key)

                    matrix.append({
                        "package": name,
                        "version": version,
                        "target": target,
                        "cibw_platform": platform,
                        "cibw_archs": archs,
                        "cibw_build_id": cibw_build_id(
                            platform,
                            hint,
                            python_tag,
                        ),
                        "py_tag": python_tag,
                        "runner": runner,
                    })

    return matrix


def write_github_outputs(matrix: list[dict[str, str]]) -> None:
    output_path = os.environ.get("GITHUB_OUTPUT")

    if not output_path:
        return

    payload = json.dumps(matrix, separators=(",", ":"))

    # Multiline-safe output format.
    delimiter = "WHEEL_GAPS_JSON"

    with open(output_path, "a", encoding="utf-8") as output:
        output.write(f"matrix<<{delimiter}\n")
        output.write(payload + "\n")
        output.write(f"{delimiter}\n")
        output.write(f"has_gaps={'true' if matrix else 'false'}\n")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Detect missing runtime dependency wheels."
    )
    parser.add_argument(
        "--output",
        default="wheel-gaps.json",
        help="Path for the JSON gap report.",
    )
    args = parser.parse_args()

    try:
        matrix = detect_gaps()

    except FileNotFoundError as exc:
        print(f"Required project file not found: {exc}", file=sys.stderr)
        return 1

    except (httpx.HTTPError, ValueError, KeyError) as exc:
        print(f"Wheel-gap detection failed: {exc}", file=sys.stderr)
        return 1

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(matrix, indent=2) + "\n",
        encoding="utf-8",
    )

    write_github_outputs(matrix)

    print(f"Detected {len(matrix)} missing wheel combination(s).")

    for item in matrix:
        print(
            f" - {item['package']}=={item['version']} / "
            f"{item['target']} / {item['py_tag']}"
        )

    print(f"JSON report: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())