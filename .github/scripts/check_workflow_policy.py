#!/usr/bin/env python3
"""Fail-closed policy checks for the experimental v1.1 workflow set."""
from __future__ import annotations

import re
import sys
from pathlib import Path

WORKFLOWS = Path(".github/workflows")
TESTPYPI_WORKFLOW = "testpypi-publish.yml"
FORBIDDEN_DESTINATIONS = (
    "https://upload.pypi.org/legacy/",
    "https://pypi.org/legacy/",
    "repository-url: https://pypi.org/legacy/",
)

# Deliberately text-based, not YAML-parsed: actionlint (workflow-check.yml)
# handles syntax; these checks must survive a YAML reformat that could
# otherwise hide a forbidden construct.
_OIDC_RE = re.compile(r"\bid-token\s*:\s*write\b", re.I)
_PRT_RE = re.compile(r"\bpull_request_target\s*:", re.I)
_PUBLISH_ACTION_RE = re.compile(r"pypa/gh-action-pypi-publish", re.I)
_BLANKET_PERMS_RE = re.compile(r"permissions\s*:\s*(?:write-all|read-all)\b", re.I)


def _has_testpypi_environment(text: str) -> bool:
    """Match either `environment: testpypi` or the block form."""
    inline = re.compile(r"^\s*environment\s*:\s*['\"]?testpypi['\"]?\s*$", re.M)
    block = re.compile(
        r"^\s*environment\s*:\s*\n(?:\s+.*\n)*?\s*name\s*:\s*['\"]?testpypi['\"]?",
        re.M,
    )
    return inline.search(text) is not None or block.search(text) is not None


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
        text = path.read_text(encoding="utf-8-sig")
        lower = text.lower()

        for destination in FORBIDDEN_DESTINATIONS:
            if destination.lower() in lower:
                errors.append(
                    f"{path}: production PyPI destination is forbidden on the v1.1 "
                    f"experimental branch ({destination})."
                )

        if _PRT_RE.search(text):
            errors.append(
                f"{path}: pull_request_target is forbidden by experimental workflow policy."
            )

        if _BLANKET_PERMS_RE.search(text):
            errors.append(
                f"{path}: blanket 'permissions: write-all'/'read-all' is forbidden; "
                "declare explicit scopes."
            )

        if _OIDC_RE.search(text):
            oidc_files.append(path.name)
            if path.name != TESTPYPI_WORKFLOW:
                errors.append(
                    f"{path}: OIDC publishing permission is only permitted in "
                    f"{TESTPYPI_WORKFLOW}."
                )

        if _PUBLISH_ACTION_RE.search(text) and path.name != TESTPYPI_WORKFLOW:
            errors.append(
                f"{path}: package publishing action is only permitted in "
                f"{TESTPYPI_WORKFLOW}."
            )

    testpypi = WORKFLOWS / TESTPYPI_WORKFLOW
    if not testpypi.exists():
        errors.append(f"Required TestPyPI workflow is missing: {testpypi}.")
    else:
        text = testpypi.read_text(encoding="utf-8-sig")
        lower = text.lower()

        if "https://test.pypi.org/legacy/" not in lower:
            errors.append(f"{testpypi}: explicit TestPyPI repository URL is required.")

        if not _has_testpypi_environment(text):
            errors.append(
                f"{testpypi}: protected environment named exactly 'testpypi' is required."
            )

        for gate in (
            "needs.validate-release.result == 'success'",
            "needs.tests.result == 'success'",
            "needs.build.result == 'success'",
        ):
            if gate not in lower:
                errors.append(f"{testpypi}: publish job must gate on {gate!r}.")

        if "repository-url: https://test.pypi.org/legacy/" not in lower:
            errors.append(
                f"{testpypi}: publish step must set exactly "
                "'repository-url: https://test.pypi.org/legacy/'."
            )

    if oidc_files != [TESTPYPI_WORKFLOW]:
        errors.append(
            f"Expected OIDC publishing permission only in {TESTPYPI_WORKFLOW}; "
            f"found {oidc_files!r}."
        )

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