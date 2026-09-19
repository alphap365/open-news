# 📦 Installation Guide

> **Stable target: v1.0.3**

Open News is distributed as **`open-news-api`** and requires **Python 3.10 or newer**.

---

## ⚡ Recommended: interactive installer

```bash
curl -fsSL https://raw.githubusercontent.com/alphap365/open-news/main/install.sh | bash
```

The installer is designed as a guided setup rather than a silent one.

### What it handles

1. Detects Linux, macOS, Termux, WSL, or Git Bash environments.
2. Finds a usable Python `3.10+` interpreter.
3. Lets you choose `pip` or `uv` when both are available.
4. Offers a quick package installation or developer installation.
5. Can create an isolated virtual environment.
6. Optionally installs the JavaScript/Playwright extra.
7. Repairs PATH configuration when required.
8. Saves CLI preferences to `~/.config/open-news/config.json`.
9. Verifies the installation with `open-news --version`.
10. Offers to launch the TUI after installation.

> 💡 **Tip:** The isolated environment is the safest default for a normal user installation because it avoids modifying unrelated Python packages.

---

## 🧰 Installer flags

The installer supports non-interactive and maintenance modes:

```bash
./install.sh --yes
./install.sh --dev
./install.sh --uv
./install.sh --pip
./install.sh --js
./install.sh --no-js
./install.sh --dry-run
./install.sh --uninstall
```

| Flag | Meaning |
|---|---|
| `--yes` | Accept default answers without prompts |
| `--dev` | Install from a Git clone in editable mode |
| `--uv` | Prefer `uv` |
| `--pip` | Prefer `pip` |
| `--js` | Install JavaScript rendering automatically |
| `--no-js` | Do not offer JavaScript rendering |
| `--dry-run` | Show planned actions without changing the system |
| `--uninstall` | Remove the installer-managed installation |

---

## 🐍 Manual pip installation

```bash
pip install open-news-api
```

Pin the stable release explicitly:

```bash
pip install open-news-api==1.0.3
```

Verify:

```bash
open-news --version
```

Expected form:

```text
open-news 1.0.3
```

---

## ⚡ Manual uv installation

For a project:

```bash
uv add open-news-api
```

For the active environment:

```bash
uv pip install open-news-api
```

For an isolated CLI tool:

```bash
uv tool install open-news-api
```

---

## 🛠️ Developer installation

```bash
git clone https://github.com/alphap365/open-news.git
cd open-news

python -m venv .venv
source .venv/bin/activate

python -m pip install -e ".[dev]"
pytest -q
```

Windows:

```powershell
.venv\Scripts\activate
python -m pip install -e ".[dev]"
pytest -q
```

With `uv`:

```bash
uv sync --group dev
uv run pytest -q
```

---

## 🌐 Optional JavaScript rendering

Most news pages can be handled without a browser. Some sites require client-side rendering.

Install the optional extra:

```bash
pip install "open-news-api[js]"
playwright install chromium
```

Or with `uv`:

```bash
uv add "open-news-api[js]"
playwright install chromium
```

Then enable it through the API or CLI where supported:

```python
get_article(url, js=True)
```

```bash
open-news extract https://example.com/article --js
```

### What this costs

Chromium is a large download. The browser is therefore intentionally **optional** rather than a mandatory Open News dependency.

---

## 📱 Termux / Android

v1.0.3 includes a dedicated Android installation script:

```bash
./install-on-android.sh
```

The general installer also recognizes Termux.

For a manual setup, the native XML dependencies used by `lxml` may need to be installed first:

```bash
pkg install clang libxml2 libxslt python-pip
pip install open-news-api
```

With an existing `uv` environment:

```bash
uv pip install open-news-api
```

### Why Termux is special

The v1.0.3 acquisition layer does not assume that the native DDGS route is always suitable on Termux. `fetch()` can therefore start with the portable fallback chain instead of forcing the native route.

---

## ⚙️ CLI preferences

The interactive installer can create:

```text
~/.config/open-news/config.json
```

Example:

```json
{
  "language": null,
  "category": "general",
  "sort_by": "date",
  "format": "pretty"
}
```

These values become CLI defaults. Explicit command-line options override them.

You can safely edit or delete this file.

---

## 🧹 Uninstalling

### Installer-managed installation

```bash
./install.sh --uninstall
```

The installer records its installation state so that uninstall can distinguish package and developer installations.

### pip

```bash
pip uninstall open-news-api
```

### uv project dependency

Remove the package from the project with your normal `uv` workflow.

### uv tool

```bash
uv tool uninstall open-news-api
```

---

## 🧪 Verify before use

After installation:

```bash
open-news --version
open-news --help
open-news fetch --category tech --limit 3
```

For development:

```bash
pytest -q
```

A stable release should be verified in the environment where it will actually run, especially when using Termux, JavaScript rendering, or unusual Python installations.
