#!/usr/bin/env bash
# open-news interactive installer & project initializer
#
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/alphap365/open-news/main/install.sh | bash
#   ./install.sh --yes              # non-interactive, all defaults (CI-friendly)
#   ./install.sh --dev              # developer install: git clone + editable
#   ./install.sh --uv               # use uv instead of pip
#   ./install.sh --pip              # use pip (default)
#   ./install.sh --no-js            # never offer the Playwright/JS extra
#   ./install.sh --version 1.0.3    # install a specific version (quick install)
#   ./install.sh --dry-run          # print what would happen, run nothing
#   ./install.sh --uninstall        # remove the venv + config this script created
#
# What this does, roughly in order:
#   1. Detect OS / shell / Termux, and Python version.
#   2. Ask: Quick install or Developer install (git clone -e).
#   3. Ask: isolated venv (recommended) or current environment.
#   4. Ask: install the JS/Playwright extra now, later, or never.
#   5. Fix PATH so `open-news` works in a new shell.
#   6. Ask a few first-run preferences -> ~/.config/open-news/config.json
#   7. Install, verify with `open-news --version`, offer to launch the TUI.
#
set -euo pipefail

REPO_URL="https://github.com/alphap365/open-news.git"
PKG="open-news-api"
VENV_DIR="${HOME}/.open-news/venv"
DEV_DIR="${HOME}/open-news"
CONFIG_DIR="${HOME}/.config/open-news"
CONFIG_FILE="${CONFIG_DIR}/config.json"
STATE_FILE="${HOME}/.open-news/install-state.json"

ASSUME_YES=0
DEV_MODE=0
JS_MODE="ask"           # ask | yes | no
PACKAGE_MANAGER="ask"   # ask | pip | uv
DRY_RUN=0
DO_UNINSTALL=0
PIN_VERSION=""

info()  { printf '\033[36m==>\033[0m %s\n' "$1"; }
warn()  { printf '\033[33m!!\033[0m %s\n' "$1" >&2; }
fail()  { printf '\033[31mError:\033[0m %s\n' "$1" >&2; exit 1; }
ok()    { printf '\033[32m✓\033[0m %s\n' "$1"; }

run() {
  # Executes unless --dry-run, in which case it just echoes the command.
  if [ "$DRY_RUN" -eq 1 ]; then
    printf '\033[2m$ %s\033[0m\n' "$*"
  else
    "$@"
  fi
}

# Read from the terminal even when the script itself is piped (curl | bash).
_tty_read() {   # usage: _tty_read "prompt" varname
  if [ -r /dev/tty ]; then
    read -r -p "$1" "$2" </dev/tty || true
  else
    read -r -p "$1" "$2" || true
  fi
}

# Prompt with a numbered default; returns the chosen index (1-based) on stdout.
# In --yes mode, always returns the default without asking.
ask_choice() {
  local prompt="$1"; shift
  local default_idx="$1"; shift
  local options=("$@")

  if [ "$ASSUME_YES" -eq 1 ]; then
    echo "$default_idx"
    return
  fi

  printf '\n%s\n' "$prompt" >&2
  local i=1
  for opt in "${options[@]}"; do
    local marker=" "
    [ "$i" -eq "$default_idx" ] && marker="*"
    printf '  [%s%d] %s\n' "$marker" "$i" "$opt" >&2
    i=$((i + 1))
  done
  local reply=""
  _tty_read "Choose [default ${default_idx}]: " reply
  if [ -z "$reply" ]; then
    echo "$default_idx"
  else
    echo "$reply"
  fi
}

ask_text() {
  local prompt="$1" default="$2" reply=""
  if [ "$ASSUME_YES" -eq 1 ]; then
    echo "$default"
    return
  fi
  _tty_read "$prompt [$default]: " reply
  echo "${reply:-$default}"
}

# NOTE: main() opens here and closes at the end of block 4.
# The body is intentionally not indented so heredoc terminators stay valid.
main() {

# Keep the original args so the Termux handoff can forward them untouched.
ORIG_ARGS=("$@")

while [ $# -gt 0 ]; do
  case "$1" in
    --yes|-y)    ASSUME_YES=1 ;;
    --dev)       DEV_MODE=1 ;;
    --uv)        PACKAGE_MANAGER="uv" ;;
    --pip)       PACKAGE_MANAGER="pip" ;;
    --js)        JS_MODE="yes" ;;
    --no-js)     JS_MODE="no" ;;
    --dry-run)   DRY_RUN=1 ;;
    --uninstall) DO_UNINSTALL=1 ;;
    --version)
      if [ $# -lt 2 ] || [ -z "${2:-}" ] || [ "${2#-}" != "$2" ]; then
        printf 'Error: --version requires a value, e.g. --version 1.0.3\n' >&2
        exit 2
      fi
      PIN_VERSION="$2"
      shift
      ;;
    --version=*)
      PIN_VERSION="${1#--version=}"
      [ -n "$PIN_VERSION" ] || { printf 'Error: --version= requires a value\n' >&2; exit 2; }
      ;;
    -h|--help)
      sed -n '2,23p' "$0" | sed 's/^# \{0,1\}//'
      exit 0
      ;;
    *)
      printf 'Unknown option: %s\n' "$1" >&2
      exit 2
      ;;
  esac
  shift
done

# ---------------------------------------------------------------------
# Termux has a fundamentally different install path — no PyPI Android
# wheels for compiled deps, and lxml needs a from-source build. Hand off.
# (This runs before the uninstall path so --uninstall on Termux also
# removes the launcher wrappers in $PREFIX/bin.)
# ---------------------------------------------------------------------
if [ -n "${TERMUX_VERSION:-}" ] || [ -d "/data/data/com.termux" ]; then
  info "Termux detected — handing off to install-on-android.sh"

  SELF_DIR=""
  if [ -n "${BASH_SOURCE[0]:-}" ]; then
    SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" 2>/dev/null && pwd || true)"
  fi

  if [ -n "$SELF_DIR" ] && [ -f "$SELF_DIR/install-on-android.sh" ]; then
    exec bash "$SELF_DIR/install-on-android.sh" ${ORIG_ARGS[@]+"${ORIG_ARGS[@]}"}
  fi

  tmp="$(mktemp)"
  curl -fsSL \
    "https://raw.githubusercontent.com/alphap365/open-news/main/install-on-android.sh" \
    -o "$tmp"
  exec bash "$tmp" ${ORIG_ARGS[@]+"${ORIG_ARGS[@]}"}
fi

# ---------------------------------------------------------------------
# Uninstall path (short-circuits everything else)
# ---------------------------------------------------------------------
if [ "$DO_UNINSTALL" -eq 1 ]; then
  # Read the state file BEFORE deleting ~/.open-news (it lives inside it).
  STATE_DEV_DIR=""; STATE_MODE=""
  if [ -f "$STATE_FILE" ]; then
    STATE_DEV_DIR="$(sed -n 's/.*"dev_dir" *: *"\([^"]*\)".*/\1/p' "$STATE_FILE" 2>/dev/null || true)"
    STATE_MODE="$(sed -n 's/.*"mode" *: *"\([^"]*\)".*/\1/p' "$STATE_FILE" 2>/dev/null || true)"
  fi

  info "Removing ${HOME}/.open-news"
  rm -rf "${HOME}/.open-news"

  if [ "$STATE_MODE" = "dev" ] && [ -n "$STATE_DEV_DIR" ] && [ -d "$STATE_DEV_DIR" ]; then
    reply_dev=""
    _tty_read "Also remove the developer clone at $STATE_DEV_DIR (includes its .venv)? [y/N]: " reply_dev
    if [ "${reply_dev:-N}" = "y" ] || [ "${reply_dev:-N}" = "Y" ]; then
      rm -rf "$STATE_DEV_DIR"
      ok "Removed $STATE_DEV_DIR"
    fi
  fi

  reply=""
  _tty_read "Also remove preferences at $CONFIG_FILE? [y/N]: " reply
  if [ "${reply:-N}" = "y" ] || [ "${reply:-N}" = "Y" ]; then
    rm -rf "$CONFIG_DIR"
    ok "Removed $CONFIG_DIR"
  fi
  ok "Uninstalled. Remove the PATH line from your shell rc file manually if you added one."
  exit 0
fi

printf '\n'
printf '\033[1m open-news installer\033[0m\n'
printf ' Fetch, search, discover, understand.\n\n'

# ---------------------------------------------------------------------
# 1. Environment detection
# ---------------------------------------------------------------------
OS="unknown"
case "$(uname -s)" in
  Linux*)  OS="linux" ;;
  Darwin*) OS="macos" ;;
  CYGWIN*|MINGW*|MSYS*) OS="windows-shell" ;;
esac
info "Detected environment: $OS"

if [ "$OS" = "windows-shell" ]; then
  warn "Native cmd.exe/PowerShell can't run this script — you're in Git Bash/MSYS,"
  warn "which is fine, but consider WSL for the smoothest experience."
fi

PYTHON_BIN=""
PY_VERSION=""
PY_MINOR_BEST=-1

candidates=()
for v in {20..4}; do candidates+=("python3.$v"); done
candidates+=(python3 python)   # bare names: Linux/macOS use python3,
                               # Windows Git Bash usually only has python

for candidate in "${candidates[@]}"; do
  command -v "$candidate" >/dev/null 2>&1 || continue

  ver=$("$candidate" -c 'import sys; print("%d.%d" % sys.version_info[:2])' 2>/dev/null) || continue

  case "$ver" in
    3.*) ;;
    *) continue ;;
  esac

  minor=${ver#3.}
  case "$minor" in
    ''|*[!0-9]*) continue ;;
  esac
  [ "$minor" -ge 10 ] || continue

  if [ "$minor" -gt "$PY_MINOR_BEST" ]; then
    PYTHON_BIN="$candidate"
    PY_VERSION="$ver"
    PY_MINOR_BEST="$minor"
  fi
done

[ -n "$PYTHON_BIN" ] || fail "No Python 3.10+ interpreter found on PATH (tried ${candidates[*]})."
ok "Python $PY_VERSION ($PYTHON_BIN)"

UV_BIN=""
if command -v uv >/dev/null 2>&1; then
  UV_BIN="$(command -v uv)"
fi
if [ "$PACKAGE_MANAGER" = "ask" ]; then
  if [ -n "$UV_BIN" ]; then
    package_manager_choice=$(ask_choice \
      "Which package manager should install open-news?" 2 \
      "pip" \
      "uv (recommended when available)")
    [ "$package_manager_choice" = "2" ] && PACKAGE_MANAGER="uv" || PACKAGE_MANAGER="pip"
  else
    PACKAGE_MANAGER="pip"
    info "uv not found — using pip. Pass --uv after installing uv to use it."
  fi
elif [ "$PACKAGE_MANAGER" = "uv" ] && [ -z "$UV_BIN" ]; then
  fail "--uv was requested, but uv was not found. Install it from https://docs.astral.sh/uv/getting-started/installation/"
fi

# ---------------------------------------------------------------------
# 2. Quick vs Developer install
# ---------------------------------------------------------------------
if [ "$DEV_MODE" -eq 1 ]; then
  mode_choice=2
else
  mode_choice=$(ask_choice \
    "How would you like to install open-news?" 1 \
    "Quick install — package, for regular use" \
    "Developer install — git clone + editable (-e), for contributing")
fi

# ---------------------------------------------------------------------
# 3. venv or current environment
# ---------------------------------------------------------------------
if [ "$mode_choice" = "2" ]; then
  # Developer installs always use their own venv inside the repo,
  # matching the README's `python -m venv .venv` convention.
  venv_choice=1
  VENV_DIR="${DEV_DIR}/.venv"
  if [ -n "$PIN_VERSION" ]; then
    warn "--version is ignored for developer installs (editable install of the clone)."
  fi
else
  venv_choice=$(ask_choice \
    "Where should it be installed?" 1 \
    "Isolated virtual environment (recommended): $VENV_DIR" \
    "Current Python environment ($PYTHON_BIN)")
fi

# ---------------------------------------------------------------------
# 4. JS/Playwright extra
# ---------------------------------------------------------------------
if [ "$JS_MODE" = "ask" ]; then
  js_choice=$(ask_choice \
    "Install the optional JavaScript-rendering extra (Playwright + Chromium, ~300MB)?" 2 \
    "Yes, now" \
    "No, I can add it later with: ${PACKAGE_MANAGER} install \"open-news-api[js]\" && playwright install chromium")
  [ "$js_choice" = "1" ] && JS_MODE="yes" || JS_MODE="no"
fi

# ---------------------------------------------------------------------
# 5. First-run preferences -> config.json (the "project initializer" part)
# ---------------------------------------------------------------------
info "A few defaults — these are written once and used by the CLI/TUI unless overridden per-run."
PREF_LANGUAGE=$(ask_text "Default language filter (ISO 639-1, blank = none)" "")
PREF_CATEGORY=$(ask_text "Default fetch category" "general")
PREF_SORT=$(ask_text "Default sort (date/relevance/popularity)" "date")
PREF_FORMAT=$(ask_text "Default CLI output format (pretty/json)" "pretty")

case "$PREF_CATEGORY" in
  general|business|tech|sports|health|science|entertainment) ;;
  *) warn "Unknown category '$PREF_CATEGORY'; using 'general'."; PREF_CATEGORY="general" ;;
esac
case "$PREF_SORT" in
  date|relevance|popularity) ;;
  *) warn "Unknown sort '$PREF_SORT'; using 'date'."; PREF_SORT="date" ;;
esac
case "$PREF_FORMAT" in
  pretty|json) ;;
  *) warn "Unknown format '$PREF_FORMAT'; using 'pretty'."; PREF_FORMAT="pretty" ;;
esac

# ---------------------------------------------------------------------
# Install
# ---------------------------------------------------------------------
if [ "$mode_choice" = "2" ]; then
  # --- Developer install ---
  if [ -d "$DEV_DIR/.git" ]; then
    info "Repo already present at $DEV_DIR — pulling latest"
    run git -C "$DEV_DIR" pull --ff-only
  else
    info "Cloning $REPO_URL to $DEV_DIR"
    run git clone "$REPO_URL" "$DEV_DIR"
  fi
  info "Creating venv at $VENV_DIR"
  run "$PYTHON_BIN" -m venv "$VENV_DIR"
  if [ -d "$VENV_DIR/Scripts" ]; then
    BIN_DIR="$VENV_DIR/Scripts"
    VENV_PYTHON="$VENV_DIR/Scripts/python.exe"
  else
    BIN_DIR="$VENV_DIR/bin"
    VENV_PYTHON="$VENV_DIR/bin/python"
  fi
  SPEC=".[dev]"
  [ "$JS_MODE" = "yes" ] && SPEC=".[dev,js]"
  info "Installing editable ($SPEC) from $DEV_DIR"
  if [ "$PACKAGE_MANAGER" = "uv" ]; then
    ( cd "$DEV_DIR" && run "$UV_BIN" pip install --python "$VENV_PYTHON" --upgrade "$SPEC" )
  else
    PIP_BIN="$BIN_DIR/pip"
    run "$PIP_BIN" install --upgrade pip
    ( cd "$DEV_DIR" && run "$PIP_BIN" install -e "$SPEC" )
  fi
else
  # --- Quick install ---
  if [ "$venv_choice" = "1" ]; then
    info "Creating venv at $VENV_DIR"
    run "$PYTHON_BIN" -m venv "$VENV_DIR"
    if [ -d "$VENV_DIR/Scripts" ]; then
      BIN_DIR="$VENV_DIR/Scripts"
      VENV_PYTHON="$VENV_DIR/Scripts/python.exe"
    else
      BIN_DIR="$VENV_DIR/bin"
      VENV_PYTHON="$VENV_DIR/bin/python"
    fi
  else
    BIN_DIR="$("$PYTHON_BIN" -c 'import site; print(site.USER_BASE + "/bin")')"
  fi

  SPEC="$PKG"
  [ "$JS_MODE" = "yes" ] && SPEC="${PKG}[js]"
  [ -n "$PIN_VERSION" ] && SPEC="${SPEC}==${PIN_VERSION}"

  info "Installing $SPEC"
  if [ "$PACKAGE_MANAGER" = "uv" ] && [ "$venv_choice" = "1" ]; then
    run "$UV_BIN" pip install --python "$VENV_PYTHON" "$SPEC"
  elif [ "$venv_choice" = "1" ]; then
    PIP_BIN="$BIN_DIR/pip"
    run "$PIP_BIN" install --upgrade pip
    run "$PIP_BIN" install "$SPEC"
  else
    # Current-environment install: always use pip (uv pip has no --user).
    run "$PYTHON_BIN" -m pip install --user --upgrade "$SPEC"
  fi
fi

if [ "$JS_MODE" = "yes" ]; then
  info "Installing Playwright's Chromium browser (~300MB download)..."
  if [ "$venv_choice" = "1" ] || [ "$mode_choice" = "2" ]; then
    run "$BIN_DIR/playwright" install chromium
  else
    run "$PYTHON_BIN" -m playwright install chromium
  fi
fi

# ---------------------------------------------------------------------
# PATH handling
# ---------------------------------------------------------------------
OPEN_NEWS_BIN="$BIN_DIR/open-news"
if [ "$DRY_RUN" -eq 0 ] && [ -x "$OPEN_NEWS_BIN" ] && ! command -v open-news >/dev/null 2>&1; then
  # Pick the rc file for the user's actual login shell.
  case "$(basename "${SHELL:-bash}")" in
    zsh)  SHELL_RC="${HOME}/.zshrc" ;;
    fish) SHELL_RC="${HOME}/.config/fish/config.fish" ;;
    *)    SHELL_RC="${HOME}/.bashrc" ;;
  esac
  LINE="export PATH=\"$BIN_DIR:\$PATH\""
  if [ "$(basename "${SHELL:-bash}")" = "fish" ]; then
    LINE="set -gx PATH \"$BIN_DIR\" \$PATH"
  fi
  if ! grep -qsF "$BIN_DIR" "$SHELL_RC" 2>/dev/null; then
    mkdir -p "$(dirname "$SHELL_RC")"
    printf '\n# added by open-news installer\n%s\n' "$LINE" >> "$SHELL_RC"
    warn "Added $BIN_DIR to PATH in $SHELL_RC — restart your shell, or run:"
    warn "  $LINE"
  fi
fi

# ---------------------------------------------------------------------
# Write preferences config
# ---------------------------------------------------------------------
info "Writing preferences to $CONFIG_FILE"
run mkdir -p "$CONFIG_DIR"
if [ "$DRY_RUN" -eq 0 ]; then
  CFG_PY="${VENV_PYTHON:-$PYTHON_BIN}"
  "$CFG_PY" - "$PREF_LANGUAGE" "$PREF_CATEGORY" "$PREF_SORT" "$PREF_FORMAT" "$CONFIG_FILE" <<'PY'
import json, sys
lang, cat, sort_by, fmt, path = sys.argv[1:6]
with open(path, "w", encoding="utf-8") as f:
    json.dump({"language": lang or None, "category": cat,
               "sort_by": sort_by, "format": fmt}, f, indent=2)
    f.write("\n")
PY
  mkdir -p "$(dirname "$STATE_FILE")"
  STATE_MODE_VAL="quick"
  [ "$mode_choice" = "2" ] && STATE_MODE_VAL="dev"
  cat > "$STATE_FILE" <<EOF
{
  "mode": "$STATE_MODE_VAL",
  "package_manager": "$PACKAGE_MANAGER",
  "venv_dir": "$VENV_DIR",
  "dev_dir": "$( [ "$mode_choice" = "2" ] && printf '%s' "$DEV_DIR" )",
  "js_extra": $( [ "$JS_MODE" = "yes" ] && printf 'true' || printf 'false' ),
  "bin_dir": "$BIN_DIR",
  "installed_at": "$(date -u +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || echo unknown)"
}
EOF
fi

# ---------------------------------------------------------------------
# Verify
# ---------------------------------------------------------------------
if [ "$DRY_RUN" -eq 1 ]; then
  ok "Dry run complete — nothing was installed."
  exit 0
fi

info "Verifying install..."
if [ -x "$OPEN_NEWS_BIN" ]; then
  "$OPEN_NEWS_BIN" --version
  ok "Install verified."
  echo
  echo "Run it with:"
  if command -v open-news >/dev/null 2>&1; then
    echo "  open-news --help"
  else
    echo "  $OPEN_NEWS_BIN --help   (or restart your shell / re-source your rc file)"
  fi
else
  warn "No open-news binary found at $OPEN_NEWS_BIN — falling back to module invocation."
  "$PYTHON_BIN" -m open_news.cli --version || fail "Verification failed. Try: $PYTHON_BIN -m open_news.cli --version"
  echo "Run it with: $PYTHON_BIN -m open_news.cli --help"
fi

# ---------------------------------------------------------------------
# Offer to launch the TUI
# ---------------------------------------------------------------------
if [ "$ASSUME_YES" -eq 0 ]; then
  launch=""
  _tty_read $'\nLaunch the terminal interface now? [y/N]: ' launch
  if [ "${launch:-N}" = "y" ] || [ "${launch:-N}" = "Y" ]; then
    if [ -x "${BIN_DIR}/open-news-tui" ]; then
      exec "${BIN_DIR}/open-news-tui"
    else
      exec "$PYTHON_BIN" -m open_news.tui
    fi
  fi
fi

}   # end main()

main "$@"