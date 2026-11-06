"""Plan dependency-wheel builds from compute_wheel_gaps.py output.

The planner separates detection from build strategy.

Current capabilities:
    generic:
        Eligible for the generic cibuildwheel path.

    recipe_required:
        Requires a package-specific native dependency recipe.

    unsupported:
        No build profile exists for the requested target.

This is intentionally conservative. A package being native does not mean
that a generic cibuildwheel invocation can successfully build it.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any


PROFILES: dict[str, dict[str, str]] = {
    "manylinux_x86_64": {
        "runner": "ubuntu-latest",
        "cibw_platform": "linux",
        "cibw_archs": "x86_64",
    },
    "manylinux_aarch64": {
        "runner": "ubuntu-latest",
        "cibw_platform": "linux",
        "cibw_archs": "aarch64",
    },
    "musllinux_x86_64": {
        "runner": "ubuntu-latest",
        "cibw_platform": "linux",
        "cibw_archs": "x86_64",
    },
    "musllinux_aarch64": {
        "runner": "ubuntu-latest",
        "cibw_platform": "linux",
        "cibw_archs": "aarch64",
    },
    "macosx_arm64": {
        "runner": "macos-latest",
        "cibw_platform": "macos",
        "cibw_archs": "arm64",
    },
    "macosx_x86_64": {
        "runner": "macos-latest",
        "cibw_platform": "macos",
        "cibw_archs": "x86_64",
    },
    "win_amd64": {
        "runner": "windows-latest",
        "cibw_platform": "windows",
        "cibw_archs": "AMD64",
    },
    "android_arm64_v8a": {
        "runner": "ubuntu-latest",
        "cibw_platform": "android",
        "cibw_archs": "arm64_v8a",
    },
}

# These packages are known to need additional handling in at least some
# target combinations. This is not a permanent denylist: recipes will
# eventually make individual combinations eligible.
RECIPE_REQUIRED = {
    "cffi": "libffi headers and target library may be required",
    "cryptography": "Rust/OpenSSL target configuration may be required",
    "lxml": "libxml2 and libxslt target libraries may be required",
    "numpy": "target-specific compiler and BLAS configuration may be required",
    "scipy": "Fortran/compiler and BLAS/LAPACK dependencies may be required",
    "pillow": "optional image libraries may require target provisioning",
}

EXCLUDED_PACKAGES = {
    # lxml is intentionally not built by the generic workflow.
    # It must be handled by a dedicated recipe.
    "lxml",
}


def normalize_name(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def classify(item: dict[str, Any]) -> tuple[str, str]:
    name = normalize_name(item["package"])

    if name in EXCLUDED_PACKAGES:
        return (
            "recipe_required",
            "Package is excluded from the generic builder.",
        )

    if name in RECIPE_REQUIRED:
        return "recipe_required", RECIPE_REQUIRED[name]

    return (
        "generic",
        "No special build recipe is currently registered.",
    )


def validate_gap(item: dict[str, Any]) -> None:
    required = {
        "package",
        "version",
        "target",
        "cibw_platform",
        "cibw_archs",
        "cibw_build_id",
        "py_tag",
        "runner",
    }

    missing = required.difference(item)

    if missing:
        raise ValueError(
            f"Gap entry is missing fields {sorted(missing)}: {item}"
        )


def plan(gaps: list[dict[str, Any]]) -> dict[str, Any]:
    buildable: list[dict[str, Any]] = []
    deferred: list[dict[str, Any]] = []

    for original in gaps:
        validate_gap(original)

        item = dict(original)
        target = item["target"]

        profile = PROFILES.get(target)

        if profile is None:
            item["status"] = "unsupported"
            item["reason"] = f"No build profile exists for target {target}."
            deferred.append(item)
            continue

        classification, reason = classify(item)

        item.update(profile)
        item["classification"] = classification
        item["reason"] = reason

        if classification == "generic":
            item["status"] = "planned"
            buildable.append(item)
        else:
            item["status"] = "recipe_required"
            deferred.append(item)

    return {
        "schema_version": 1,
        "requested_count": len(gaps),
        "planned_count": len(buildable),
        "deferred_count": len(deferred),
        "builds": buildable,
        "deferred": deferred,
    }


def write_github_outputs(result: dict[str, Any]) -> None:
    output_path = os.environ.get("GITHUB_OUTPUT")

    if not output_path:
        return

    matrix = {"include": result["builds"]}
    payload = json.dumps(matrix, separators=(",", ":"))
    delimiter = "WHEEL_BUILD_MATRIX"

    with open(output_path, "a", encoding="utf-8") as output:
        output.write(f"matrix<<{delimiter}\n")
        output.write(payload + "\n")
        output.write(f"{delimiter}\n")

        output.write(f"count={len(result['builds'])}\n")
        output.write(f"requested_count={result['requested_count']}\n")
        output.write(f"deferred_count={result['deferred_count']}\n")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", default="build-plan.json")
    parser.add_argument("--matrix-output", default="build-matrix.json")
    args = parser.parse_args()

    try:
        gaps = json.loads(
            Path(args.input).read_text(encoding="utf-8")
        )

        if not isinstance(gaps, list):
            raise ValueError("Input JSON must contain a list.")

        result = plan(gaps)

    except (OSError, json.JSONDecodeError, ValueError, KeyError) as exc:
        print(f"Planning failed: {exc}", file=sys.stderr)
        return 1

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(result, indent=2) + "\n",
        encoding="utf-8",
    )

    matrix_output = Path(args.matrix_output)
    matrix_output.parent.mkdir(parents=True, exist_ok=True)
    matrix_output.write_text(
        json.dumps({"include": result["builds"]}, indent=2) + "\n",
        encoding="utf-8",
    )

    write_github_outputs(result)

    print(
        f"Requested: {result['requested_count']}; "
        f"planned: {result['planned_count']}; "
        f"deferred: {result['deferred_count']}"
    )

    for item in result["deferred"]:
        print(
            f"DEFERRED: {item['package']}=={item['version']} / "
            f"{item['target']} / {item['py_tag']}: {item['reason']}"
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())