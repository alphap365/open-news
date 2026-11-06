#!/usr/bin/env python3
"""Create a cibuildwheel build matrix from discovered wheel gaps."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import defaultdict
from pathlib import Path


def arguments():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="wheel-gaps.json")
    parser.add_argument("--output", default="wheel-build-plan.json")
    parser.add_argument("--max-python-tags-per-job", type=int, default=5)
    parser.add_argument("--strict", action="store_true")
    return parser.parse_args()


def load_gaps(path):
    with open(path, encoding="utf-8") as file:
        data = json.load(file)

    if isinstance(data, list):
        return data

    if isinstance(data, dict):
        return data.get("gaps", data.get("missing_wheels", []))

    raise ValueError("Invalid discovery JSON format")


def normalize(gap, index):
    if not isinstance(gap, dict):
        raise ValueError(f"Gap {index} is not an object")

    required = ["package", "version", "target", "py_tag"]
    missing = [key for key in required if not gap.get(key)]

    if missing:
        raise ValueError(
            f"Gap {index}: missing fields: {', '.join(missing)}"
        )

    package = str(gap["package"])
    version = str(gap["version"])
    target = str(gap["target"])
    py_tag = str(gap["py_tag"])

    if not re.fullmatch(r"cp\d{2,3}", py_tag):
        raise ValueError(f"Invalid Python tag: {py_tag}")

    if not re.fullmatch(r"[A-Za-z0-9_.+-]+", package):
        raise ValueError(f"Invalid package name: {package}")

    if gap.get("sdist_available") is False:
        raise ValueError(f"{package}=={version}: no source distribution")

    if gap.get("status") in {"deferred", "source_unavailable", "unbuildable"}:
        raise ValueError(
            f"{package}=={version}: discovery marked it unbuildable"
        )

    platform = gap.get("cibw_platform")
    arch = gap.get("cibw_archs")
    runner = gap.get("runner")

    if not platform or not arch or not runner:
        raise ValueError(
            f"{package}=={version}: missing platform, architecture or runner"
        )

    return {
        "package": package,
        "version": version,
        "target": target,
        "py_tag": py_tag,
        "cibw_platform": platform,
        "cibw_archs": arch,
        "runner": runner,
        "platform_floor": gap.get("platform_floor"),
        "source_url": gap.get("sdist_url") or gap.get("source_url"),
        "source_sha256": gap.get("sdist_sha256")
        or gap.get("source_sha256"),
    }


def make_plan(gaps, max_tags):
    if max_tags < 1:
        raise ValueError("max-python-tags-per-job must be positive")

    groups = defaultdict(dict)

    for gap in gaps:
        key = (
            gap["package"],
            gap["version"],
            gap["target"],
            gap["cibw_platform"],
            gap["cibw_archs"],
            gap["runner"],
        )
        groups[key].setdefault(gap["py_tag"], gap)

    plan = []

    for key in sorted(groups):
        package, version, target, platform, arch, runner = key
        entries = groups[key]

        tags = sorted(entries, key=lambda tag: int(tag[2:]))

        for offset in range(0, len(tags), max_tags):
            batch = tags[offset:offset + max_tags]
            selected = [entries[tag] for tag in batch]

            urls = {item["source_url"] for item in selected if item["source_url"]}
            hashes = {
                item["source_sha256"] for item in selected
                if item["source_sha256"]
            }

            if len(urls) > 1 or len(hashes) > 1:
                raise ValueError(
                    f"Inconsistent source metadata: {package}=={version}"
                )

            build_selector = " ".join(f"{tag}-*" for tag in batch)

            # All entries in a group share the same target, hence the
            # same platform_floor.
            floor = selected[0].get("platform_floor")

            plan.append({
                "package": package,
                "version": version,
                "target": target,
                "cibw_platform": platform,
                "cibw_archs": arch,
                "runner": runner,
                "py_tags": batch,
                "cibw_build": build_selector,
                "platform_floor": floor,
                "source_url": next(iter(urls), None),
                "source_sha256": next(iter(hashes), None),
                "batch": offset // max_tags + 1,
            })

    return plan


def main():
    args = arguments()

    try:
        raw_gaps = load_gaps(args.input)

        valid = []
        rejected = []

        for index, gap in enumerate(raw_gaps, start=1):
            try:
                valid.append(normalize(gap, index))
            except ValueError as exc:
                rejected.append(str(exc))

        if rejected and args.strict:
            raise ValueError("\n".join(rejected))

        plan = make_plan(valid, args.max_python_tags_per_job)

        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps(plan, indent=2) + "\n",
            encoding="utf-8",
        )

        github_output = os.environ.get("GITHUB_OUTPUT")
        if github_output:
            with open(github_output, "a", encoding="utf-8") as file:
                file.write(
                    "matrix="
                    + json.dumps(plan, separators=(",", ":"))
                    + "\n"
                )
                file.write(f"has_builds={'true' if plan else 'false'}\n")
                file.write(f"build_count={len(plan)}\n")
                file.write(f"gap_count={len(valid)}\n")
                file.write(f"rejected_count={len(rejected)}\n")

        print(f"Discovered gaps: {len(raw_gaps)}")
        print(f"Buildable gaps: {len(valid)}")
        print(f"Generated jobs: {len(plan)}")
        print(f"Rejected/deferred: {len(rejected)}")

        for job in plan:
            print(
                f"{job['package']}=={job['version']} | "
                f"{job['target']} | {job['cibw_build']}"
            )

        for error in rejected:
            print(f"DEFERRED: {error}", file=sys.stderr)

        return 0

    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())