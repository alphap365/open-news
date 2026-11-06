"""Assemble successful dependency wheels into a ZIP and create manifests."""

from __future__ import annotations

import argparse
import json
import sys
import zipfile
try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib

from datetime import datetime, timezone
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--wheel-dir", required=True)
    parser.add_argument("--plan", required=True)
    parser.add_argument("--output-dir", default="bundle")
    parser.add_argument("--version", default=None)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--commit", required=True)
    args = parser.parse_args()

    project = tomllib.loads(
        Path("pyproject.toml").read_text(encoding="utf-8")
    )

    project_version = args.version or project["project"]["version"]
    project_name = project["project"]["name"]

    wheel_root = Path(args.wheel_dir)
    output_root = Path(args.output_dir)
    output_root.mkdir(parents=True, exist_ok=True)

    plan = json.loads(
        Path(args.plan).read_text(encoding="utf-8")
    )

    planned = plan.get("builds", [])
    deferred = plan.get("deferred", [])

    wheels = sorted(wheel_root.rglob("*.whl"))

    built_records = []
    used_wheels = set()

    for wheel in wheels:
        built_records.append({
            "filename": wheel.name,
            "size": wheel.stat().st_size,
            "source": str(wheel),
        })
        used_wheels.add(wheel.name)

    missing = []

    for request in planned:
        prefix = (
            request["package"].lower().replace("-", "_")
            + "-"
            + request["version"]
            + "-"
        )

        matches = [
            wheel for wheel in wheels
            if wheel.name.lower().startswith(prefix)
        ]

        if not matches:
            missing.append({
                "package": request["package"],
                "version": request["version"],
                "target": request["target"],
                "py_tag": request["py_tag"],
                "status": "build_failed_or_no_artifact",
            })

    manifest = {
        "schema_version": 1,
        "project": project_name,
        "project_version": project_version,
        "tag": args.tag,
        "source_commit": args.commit,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "summary": {
            "requested": plan.get("requested_count", 0),
            "planned": plan.get("planned_count", 0),
            "deferred": len(deferred),
            "wheel_files_found": len(wheels),
            "missing_planned_combinations": len(missing),
        },
        "built_wheels": built_records,
        "missing": missing,
        "deferred": deferred,
        "limitations": [
            "This bundle contains third-party dependency wheels only.",
            "It does not contain an Open News wheel or source distribution.",
            "A wheel being present does not guarantee all external shared "
            "libraries are available on the destination system.",
            "Use the bundle only with the dependency versions and target "
            "environment for which it was built.",
        ],
    }

    json_path = output_root / "manifest.json"
    json_path.write_text(
        json.dumps(manifest, indent=2) + "\n",
        encoding="utf-8",
    )

    text_lines = [
        f"{project_name} {project_version} — dependency wheel bundle",
        f"Tag: {args.tag}",
        f"Source commit: {args.commit}",
        f"Created: {manifest['created_at']}",
        "",
        "Third-party dependency wheels only.",
        "No Open News wheel is included.",
        "",
        f"Wheel files found: {len(wheels)}",
        f"Planned combinations: {plan.get('planned_count', 0)}",
        f"Deferred combinations: {len(deferred)}",
        f"Missing planned combinations: {len(missing)}",
        "",
        "Built wheel files:",
    ]

    if wheels:
        text_lines.extend(f"  {wheel.name}" for wheel in wheels)
    else:
        text_lines.append("  None")

    if missing:
        text_lines += ["", "Missing or failed combinations:"]

        for item in missing:
            text_lines.append(
                f"  {item['package']}=={item['version']} / "
                f"{item['target']} / {item['py_tag']}"
            )

    if deferred:
        text_lines += ["", "Deferred combinations:"]

        for item in deferred:
            text_lines.append(
                f"  {item['package']}=={item['version']} / "
                f"{item['target']} / {item['py_tag']} — "
                f"{item.get('reason', 'No build recipe')}"
            )

    text_lines += [
        "",
        "The bundle is supplementary. It is not a guarantee of a fully",
        "offline installation because system libraries may still be needed.",
        "",
        "For normal installation:",
        "  pip install open-news-api",
    ]

    text_path = output_root / "MANIFEST.txt"
    text_path.write_text(
        "\n".join(text_lines) + "\n",
        encoding="utf-8",
    )

    zip_path = output_root / "dependency-wheels.zip"

    with zipfile.ZipFile(
        zip_path,
        "w",
        compression=zipfile.ZIP_DEFLATED,
        compresslevel=9,
    ) as archive:

        for wheel in wheels:
            archive.write(wheel, arcname=wheel.name)

        archive.write(json_path, arcname="manifest.json")
        archive.write(text_path, arcname="MANIFEST.txt")

    print(f"Created {zip_path}")
    print(f"Wheel files: {len(wheels)}")
    print(f"Missing planned combinations: {len(missing)}")
    print(f"Deferred combinations: {len(deferred)}")

    # An empty ZIP is not useful and must not be published.
    if not wheels:
        print(
            "No wheels were built; refusing to publish an empty bundle.",
            file=sys.stderr,
        )
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())