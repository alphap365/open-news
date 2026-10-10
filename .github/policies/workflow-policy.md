# GitHub Actions policy for the v1.1 experimental branch

## Required behavior

- Ordinary pushes and pull requests run verification only; they never publish a package.
- Test, build, dependency-audit, and workflow-policy results are separate. A release is eligible only if all required release checks succeed.
- The TestPyPI workflow is manual, requires the selected ref to be a version tag, confirms the exact `pyproject.toml` version, and rejects stable versions.
- TestPyPI publishing downloads the artifact produced by the successful build job in the same workflow run.
- OIDC `id-token: write` is restricted to `.github/workflows/testpypi-publish.yml` on this branch.
- Production PyPI publishing is intentionally absent from this experimental workflow set.
- Never use `continue-on-error` on a required release gate.
- Never convert failed, cancelled, skipped, or missing required checks into success.

## Recovery

1. Open the failed job and identify the first failing step.
2. Fix code/configuration on the feature branch and push a new commit.
3. Let CI rerun against the new commit; do not reuse artifacts from a previous run.
4. For a failed TestPyPI upload, fix the cause and use a new PEP 440 prerelease version. Published files generally cannot be overwritten for the same project/version/file name.
5. If a check fails because of runner or network infrastructure, rerun it. A retry is not an override of a real failure.

## GitHub repository settings to configure manually

- Protect `main` and require the intended CI checks before merge.
- Configure a GitHub environment named `testpypi`; add required reviewers if desired.
- Configure the PyPI Trusted Publisher on **TestPyPI**, using the exact repository, workflow filename, and environment name.
- Do not add production PyPI credentials or production Trusted Publisher configuration for this experimental workflow.
- Keep GitHub Actions permissions read-only by default and grant OIDC publishing permission only to the TestPyPI publish job.
