# Release policy for Open News v1.1 development

1. Development commits and pull requests are not releases.
2. A version change alone must not create a tag, draft release, or package upload.
3. A TestPyPI upload is initiated manually from an exact prerelease Git tag. The operator must enter the same version declared in `pyproject.toml`.
4. The selected tag must match the package version and the version must be a PEP 440 prerelease or development release.
5. Tests and package build/verification must both succeed before the publish job can start.
6. The publish job uploads only the artifacts built and verified in that same workflow run, to `https://test.pypi.org/legacy/`.
7. Production PyPI publication is out of scope for this experimental branch. It must be added later as a separately reviewed and protected workflow.
8. GitHub draft releases are optional and can be created manually. They are not a prerequisite for TestPyPI installation testing.
