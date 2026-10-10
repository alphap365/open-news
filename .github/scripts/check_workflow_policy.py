#!/usr/bin/env python3
"""Fail-closed policy checks for the experimental v1.1 workflow set."""

from __future__ import annotations

import sys
from pathlib import Path

WORKFLOWS = Path(".github/workflows")
TESTPYPI_WORKFLOW = "testpypi-publish.yml"
FORBIDDEN_DESTINATIONS = (
    "https://upload.pypi.org/legacy/",
    "https://pypi.org/legacy/",
    "repository-url: https://pypi.org/legacy/",
)


def main() -> int:
    if not WORKFLOWS.is_dir():
        print(f"Missing workflows directory: {WORKFLOWS}", file=sys.stderr)
        return 1

    workflow_files = sorted(WORKFLOWS.glob("*.yml")) + sorted(WORKFLOWS.glob("*.yaml"))
    if not workflow_files:
        print("No workflow files found.", file=sys.stderr)
        return 1

    errors: list[str] = []
    oidc_files: list[str] = []
    for path in workflow_files:
        text = path.read_text(encoding="utf-8")
        lower = text.lower()
        for destination in FORBIDDEN_DESTINATIONS:
            if destination.lower() in lower:
                errors.append(f"{path}: production PyPI destination is forbidden on the v1.1 experimental branch ({destination}).")
        if "pull_request_target:" in lower:
            errors.append(f"{path}: pull_request_target is forbidden by experimental workflow policy.")
        if "id-token: write" in lower:
            oidc_files.append(path.name)
            if path.name != TESTPYPI_WORKFLOW:
                errors.append(f"{path}: OIDC publishing permission is only permitted in {TESTPYPI_WORKFLOW}.")
        if "pypa/gh-action-pypi-publish" in lower and path.name != TESTPYPI_WORKFLOW:
            errors.append(f"{path}: package publishing action is only permitted in {TESTPYPI_WORKFLOW}.")

    testpypi = WORKFLOWS / TESTPYPI_WORKFLOW
    if not testpypi.exists():
        errors.append(f"Required TestPyPI workflow is missing: {testpypi}.")
    else:
        text = testpypi.read_text(encoding="utf-8").lower()
        if "https://test.pypi.org/legacy/" not in text:
            errors.append(f"{testpypi}: explicit TestPyPI repository URL is required.")
        if "environment:" not in text or "name: testpypi" not in text:
            errors.append(f"{testpypi}: protected 'testpypi' environment is required.")
        if "needs.tests.result == 'success'" not in text or "needs.build.result == 'success'" not in text:
            errors.append(f"{testpypi}: publishing must depend on successful tests and build jobs.")

    if oidc_files != [TESTPYPI_WORKFLOW]:
        errors.append(f"Expected OIDC publishing permission only in {TESTPYPI_WORKFLOW}; found {oidc_files!r}.")

    if errors:
        print("Workflow policy FAILED:", file=sys.stderr)
        for error in errors:
            print(f" - {error}", file=sys.stderr)
        return 1

    print(f"Workflow policy passed for {len(workflow_files)} workflow files.")
    print("Production PyPI publishing is absent from this experimental workflow set.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
