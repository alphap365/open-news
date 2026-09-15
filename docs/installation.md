# 📦 Installation

## The interactive installer (recommended)

```bash
curl -fsSL https://raw.githubusercontent.com/alphap365/open-news/main/install.sh | bash
```

This is a wizard, not a silent script. It will:

1. Detect your OS/shell (Linux, macOS, Termux, WSL/Git Bash) and check Python ≥3.10.
2. Ask whether to use `pip` or `uv` when `uv` is installed (`pip` remains the default otherwise).
3. Ask whether you want a **Quick install** (package install) or a **Developer install** (git clone + editable).
4. Ask whether to use an isolated virtual environment (recommended, default) or your current Python environment.
5. Ask whether to install the optional JS-rendering extra (Playwright + Chromium, ~300MB).
6. Fix `PATH` automatically if the `open-news` command isn't reachable yet.
7. Ask a few first-run preferences (default language / category / sort / output format) and save them to `~/.config/open-news/config.json` — the CLI reads these as defaults, so you don't have to repeat `--language en --sort date` every time.
8. Install, then verify with `open-news --version` before declaring success.
9. Offer to launch the TUI immediately.

### Non-interactive / flags

```bash
./install.sh --yes            # all defaults, no prompts (CI-friendly)
./install.sh --dev            # developer install: git clone + editable
./install.sh --uv             # use uv instead of pip
./install.sh --pip            # use pip (default)
./install.sh --js             # always install the JS/Playwright extra
./install.sh --no-js          # never offer it
./install.sh --dry-run        # print what would happen, run nothing
./install.sh --uninstall      # remove the venv + optionally the config
```

> **Native Windows note:** `install.sh` needs a POSIX-style shell — it works under **WSL** or **Git Bash**, but not raw `cmd.exe`/PowerShell. On native Windows, use the manual install below inside PowerShell.

> **Shell requirements:** `install.sh` uses bash arrays in a way that needs bash ≥ 4.4. macOS's bundled `/bin/bash` is 3.2; if you hit `PIP_FLAGS[@]: unbound variable`, run the installer with Homebrew bash — `brew install bash && /opt/homebrew/bin/bash install.sh` — or use the manual install below.

> **Piping the script:** the interactive prompts read from `/dev/tty`, so `curl … | bash` works as advertised even though stdin is the pipe. If you're piping the script **and** have no controlling terminal (some CI containers), pass `--yes` — the wizard will then take every default without prompting.

## Manual install

```bash
pip install open-news-api
```

With `uv`, install into the active virtual environment:

```bash
uv pip install open-news-api
```

For a standalone CLI installation, `uv` can also manage an isolated tool environment:

```bash
uv tool install open-news-api
```

For local development:

```bash
git clone https://github.com/alphap365/open-news.git
cd open-news
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux/Termux: source .venv/bin/activate
python -m pip install -e ".[dev]"
```

Or let `uv` create and manage the project environment:

```bash
uv sync --group dev
uv run pytest -q
```

## Optional: JavaScript rendering

Needed for sites whose article content or links only appear after client-side rendering (crawler `js=True`, `get_article(..., js=True)`).

```bash
pip install "open-news-api[js]"
playwright install chromium
```

With `uv`:

```bash
uv pip install "open-news-api[js]"
playwright install chromium
```

This is a genuinely large download (~300MB for Chromium) — it's optional for a reason. Most feeds and article pages don't need it.

## Termux

Termux uses native builds for the compiled dependencies. The installer handles the toolchain automatically; doing it by hand:

```bash
pkg install clang rust make cmake pkg-config libxml2 libxslt libffi openssl python-pip
pip install open-news-api
```

If `uv` is already installed, the package install is:

```bash
uv pip install open-news-api
```

The installer forces native source builds for `lxml`, `selectolax`, `primp`, and `greenlet`. This avoids trying to install desktop Linux wheels on Android. If a build fails, confirm the packages above are installed and retry with verbose output:

```bash
python -m pip install -v --no-binary=lxml,selectolax,primp,greenlet open-news-api
```

To verify that native dependency wheels can be produced locally from a checkout:

```bash
bash scripts/build-termux-wheels.sh
```

The repository also builds Android wheels for `arm64_v8a` and `x86_64` with `ANDROID_API_LEVEL=24` in GitHub Actions. Those artifacts are published to the `wheelhouse` release; the Termux installer still prefers native builds for compatibility with the device's local environment.

The wheel workflow is [`.github/workflows/build-dep-wheels.yml`](https://github.com/alphap365/open-news/blob/main/.github/workflows/build-dep-wheels.yml). It builds one wheel per package × platform × Python version (3.10–3.13), driven by the versions pinned in `uv.lock` — to refresh a wheel, bump the pin and push, or trigger it manually from the Actions tab.

## Pre-release (alpha / beta) installs

The distribution follows `X.Y.ZaN` (alpha) → `X.Y.ZbN` (beta) → `X.Y.Z` (final) on the `alpha`, `beta`, and `main` branches respectively. **`pip install open-news-api` will not pick up a pre-release** — pip hides them by default. To install one, opt in explicitly:

```bash
# newest alpha or beta
pip install --pre open-news-api

# a specific pre-release
pip install "open-news-api==1.0.2a3"

# "1.0.2a0 or newer, including pre-releases on that line"
pip install "open-news-api>=1.0.2a0"
```

With `uv`:

```bash
uv pip install --prerelease=allow open-news-api
uv tool install --prerelease=allow open-news-api
```

The interactive installer always installs the newest stable release; there is no flag to make it install a pre-release. If you're testing an alpha, use one of the commands above instead. `open-news --version` prints the exact version installed.

## Preferences file

Written by the installer wizard at `~/.config/open-news/config.json`:

```json
{
  "language": null,
  "category": "general",
  "sort_by": "date",
  "format": "pretty"
}
```

These become the CLI's argparse **defaults** — any flag you pass explicitly on the command line still overrides them. Safe to hand-edit or delete.

## Uninstalling

```bash
./install.sh --uninstall
```
Removes the venv the installer created (`~/.open-news/`) and offers to remove your preferences (`~/.config/open-news/`). If you did a **Developer install**, it also reads `~/.open-news/install-state.json` (written at install time) to locate the git clone and offers to remove it and its .venv too.

If you've deleted install-state.json by hand, the dev-clone prompt won't appear — remove ~/open-news yourself in that case.

If you installed manually via `pip`, just `pip uninstall open-news-api`.

For a manual `uv` installation, use `uv pip uninstall open-news-api` or `uv tool uninstall open-news-api` when it was installed as a standalone tool.