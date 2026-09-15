# Release flow

`open-news` uses three long-lived branches and [Commitizen](https://commitizen-tools.github.io/commitizen/) for version bumps. The branch you push to determines the PEP 440 suffix.

## Branches and suffixes

| Branch  | Commitizen invocation       | Result              |
|---------|-----------------------------|---------------------|
| `alpha` | `cz bump --prerelease a`    | `1.0.2a0 → 1.0.2a1` |
| `beta`  | `cz bump --prerelease b`    | `1.0.2a4 → 1.0.2b0` |
| `main`  | `cz bump`                   | `1.0.2b7 → 1.0.2`   |

Switching suffix discards the previous pre-release token: pushing a `1.0.2a4` tree to `beta` yields `1.0.2b0`, not `1.0.2a5`. This is what makes the promotion a single merge.

## What happens on push

`.github/workflows/publish.yml` runs on every push to `alpha`, `beta`, or `main`:

1. Checks out with full history (`fetch-depth: 0` — Commitizen reads tags).
2. Runs `cz bump <flag> --yes`, which rewrites `pyproject.toml:version`, commits, and creates an annotated tag.
3. Pushes the commit and tag back to the same branch.
4. Builds with `uv build` and validates with `twine check`.
5. Publishes to PyPI via the `pypi` environment (trusted publishing, no token in the repo).

The workflow can also be dispatched manually with a `branch_override` input (`prerelease-a`, `prerelease-b`, `final`) to force a specific bump type without merging branches first.

---

## Installing a pre-release

pip and uv both hide pre-releases by default:

```bash
pip install --pre open-news-api
pip install "open-news-api==1.0.2a3"
uv pip install --prerelease=allow open-news-api
```
`pip install open-news-api` (no flags) always resolves to the newest stable release, so an alpha on PyPI is invisible until you opt in. `open-news --version` reports what's actually installed.

## Version source of truth

`pyproject.toml:[project].version`. Two things must not claim this field:

- `dynamic = ["version"]` + `setuptools-scm` — removed in this cycle, because it derives the version from git tags independently of Commitizen's write, and the two can disagree.

- A `[tool.commitizen]` version that diverges from `[project].version` — `version_files` keeps them in sync, but the `[project]` value is what `uv` build reads.

`cz` bump writes the new version to `pyproject.toml`, commits with a `chore(release):` message, tags `vX.Y.Z`, and the rest of the pipeline follows.
