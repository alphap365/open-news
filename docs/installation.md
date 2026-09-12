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

`lxml` needs a compiler and headers to build on Termux. The installer handles this automatically; doing it by hand:

```bash
pkg install clang libxml2 libxslt python-pip
pip install open-news-api
```

If `uv` is already installed, the package install is:

```bash
uv pip install open-news-api
```

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

Removes the venv the installer created (`~/.open-news/`) and offers to remove your preferences (`~/.config/open-news/`). If you installed manually via `pip`, just `pip uninstall open-news-api`.

For a manual `uv` installation, use `uv pip uninstall open-news-api` or `uv tool uninstall open-news-api` when it was installed as a standalone tool.
