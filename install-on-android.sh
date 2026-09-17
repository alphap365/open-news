#!/usr/bin/env bash
# open-news installer for Termux/Android
#
# This is the Termux-specific counterpart to install.sh. It is invoked
# automatically by install.sh when Termux is detected, and can also be run
# directly:
#
#   curl -fsSL https://raw.githubusercontent.com/alphap365/open-news/main/install-on-android.sh | bash
#   ./install-on-android.sh --yes          # non-interactive
#   ./install-on-android.sh --uv           # use uv instead of pip
#   ./install-on-android.sh --version 0.3.2
#   ./install-on-android.sh --dry-run
#   ./install-on-android.sh --uninstall
#
set -euo pipefail

REPO="alphap365/open-news"
PKG="open-news-api"
VENV_DIR="${HOME}/.open-news/venv"
CONFIG_DIR="${HOME}/.config/open-news"
CONFIG_FILE="${CONFIG_DIR}/config.json"
STATE_FILE="${HOME}/.open-news/install-state.json"
WHEELHOUSE_DIR="${HOME}/.open-news/wheelhouse"
ANDROID_API="24"
ARCH_TAG="arm64_v8a"
PLATFORM_TAG="android_${ANDROID_API}_${ARCH_TAG}"

ASSUME_YES=0
JS_MODE="ask"       # ask | yes | no
PACKAGE_MANAGER="ask" # ask | pip | uv
DRY_RUN=0
DO_UNINSTALL=0
PIN_VERSION=""

# ---- arg parsing (while-loop, since --version takes a value) --------
while [ $# -gt 0 ]; do
  case "$1" in
    --yes|-y) ASSUME_YES=1 ;;
    --js) JS_MODE="yes" ;;
    --no-js) JS_MODE="no" ;;
    --uv) PACKAGE_MANAGER="uv" ;;
    --pip) PACKAGE_MANAGER="pip" ;;
    --version) PIN_VERSION="$2"; shift ;;
    --dry-run) DRY_RUN=1 ;;
    --uninstall) DO_UNINSTALL=1 ;;
    -h|--help)
      sed -n '2,20p' "$0" | sed 's/^# \{0,1\}//'
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
# Helpers
# ---------------------------------------------------------------------
info()  { printf '\033[36m==>\033[0m %s\n' "$1"; }
warn()  { printf '\033[33m!!\033[0m %s\n' "$1" >&2; }
fail()  { printf '\033[31mError:\033[0m %s\n' "$1" >&2; exit 1; }
ok()    { printf '\033[32m✓\033[0m %s\n' "$1"; }

run() {
  if [ "$DRY_RUN" -eq 1 ]; then
    printf '\033[2m$ %s\033[0m\n' "$*"
  else
    "$@"
  fi
}

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
  done
  local reply
  read -r -p "Choose [default ${default_idx}]: " reply
  if [ -z "$reply" ]; then
    echo "$default_idx"
  else
    echo "$reply"
  fi
}

ask_text() {
  local prompt="$1" default="$2" reply
  if [ "$ASSUME_YES" -eq 1 ]; then
    echo "$default"
    return
  fi
  read -r -p "$prompt [$default]: " reply >&2 || true
  echo "${reply:-$default}"
}

# ---------------------------------------------------------------------
# Uninstall path (mirrors install.sh; short-circuits everything else)
# ---------------------------------------------------------------------
if [ "$DO_UNINSTALL" -eq 1 ]; then
  info "Removing ${HOME}/.open-news"
  rm -rf "${HOME}/.open-news"

  read -r -p "Also remove preferences at $CONFIG_FILE? [y/N]: " reply || true
  if [ "${reply:-N}" = "y" ] || [ "${reply:-N}" = "Y" ]; then
    rm -rf "$CONFIG_DIR"
    ok "Removed $CONFIG_DIR"
  fi
  ok "Uninstalled. Remove the PATH line from your shell rc file manually if you added one."
  exit 0
fi

printf '\n'
printf '\033[1m open-news installer (Android / Termux)\033[0m\n'
printf ' Fetch, search, discover, understand.\n\n'

# ---------------------------------------------------------------------
# 0. Sanity: we really are on Termux, and Python is new enough
# ---------------------------------------------------------------------
if ! command -v pkg >/dev/null 2>&1; then
  fail "This installer is for Termux (the 'pkg' command was not found). Use install.sh instead."
fi

info "Ensuring Python is installed..."
run pkg install -y python || fail "Could not install Python. Run 'pkg update && pkg install python' manually and retry."

PYTHON_BIN="$(command -v python3 || command -v python || true)"
[ -n "$PYTHON_BIN" ] || fail "No python3 on PATH after 'pkg install python'."

PY_VERSION="$("$PYTHON_BIN" -c 'import sys; print("%d.%d" % sys.version_info[:2])')"
PY_MINOR="${PY_VERSION#3.}"
case "$PY_MINOR" in
  ''|*[!0-9]*) fail "Could not parse Python version: $PY_VERSION" ;;
esac

if [ "$PY_MINOR" -lt 13 ]; then
  warn "Detected Python $PY_VERSION, but the Android wheels are built for Python 3.13+."
  warn "The 'primp' wheel is abi3 and would install on older versions, but"
  warn "'selectolax' and others are strictly cp313-cp313."
  fail "Please upgrade Termux's Python (pkg upgrade python) or run 'pkg install tur-repo && pkg install python3.13'."
fi
ok "Python $PY_VERSION ($PYTHON_BIN)"

# Verify pip actually recognises the Android platform tag. If it doesn't,
# the pre-built wheels will be rejected no matter how we fetch them.
if ! "$PYTHON_BIN" -m pip debug --verbose 2>/dev/null | grep -qi "android"; then
  warn "pip does not appear to advertise any 'android_*' platform tag."
  warn "The pre-built wheels may be rejected. Continuing anyway — if the"
  warn "install fails with 'not a supported wheel', that is why."
fi

# ---------------------------------------------------------------------
# 1. Resolve the open-news-api version we're installing
# ---------------------------------------------------------------------
# We deliberately do NOT use PyPI's info.version here. That field tracks
# only the latest STABLE release, so a prerelease like 1.0.3a1 uploaded on
# top of 1.0.2 leaves info.version pointing at 1.0.2 — which would send us
# looking for a wheelhouse-v1.0.2 release that may not exist. Instead we
# ask GitHub directly: "newest release tagged wheelhouse-v* that actually
# contains an android_arm64_v8a wheel?" That is the set of versions the
# user can actually install on this platform.
if [ -n "$PIN_VERSION" ]; then
  V="$PIN_VERSION"
  info "Using pinned version $V"
else
  V="$("$PYTHON_BIN" - <<EOF
import json, sys, urllib.request, urllib.error

url = "https://api.github.com/repos/$REPO/releases?per_page=100"
try:
    with urllib.request.urlopen(url, timeout=30) as r:
        releases = json.load(r)
except Exception as e:
    print(f"ERROR: could not list GitHub releases: {e}", file=sys.stderr)
    sys.exit(1)

def semver_key(tag):
    # Strip prefix, split on '.', coerce to comparable tuples. Prerelease
    # suffixes (a1, b2, rc3) sort BELOW the final release of the same x.y.z,
    # which matches PEP 440 / packaging semantics closely enough here.
    import re
    v = tag.removeprefix("wheelhouse-v")
    m = re.match(r"^(\d+)\.(\d+)\.(\d+)(?:([abc]|rc)(\d+))?$", v)
    if not m:
        return (0, 0, 0, 0, 0)
    major, minor, patch, pre, pre_n = m.groups()
    # pre="" sorts after any pre-release marker for the same x.y.z
    pre_rank = {"a": 1, "b": 2, "rc": 3, "": 4}[pre or ""]
    return (int(major), int(minor), int(patch), pre_rank, int(pre_n or 0))

candidates = []
for r in releases:
    tag = r.get("tag_name", "")
    if not tag.startswith("wheelhouse-v"):
        continue
    if not any("android_arm64_v8a" in a["name"] for a in r.get("assets", [])):
        continue
    candidates.append(tag)

if not candidates:
    print("ERROR: no GitHub release with android_arm64_v8a wheels found.",
          file=sys.stderr)
    print("       The wheel-build workflow has not published an Android",
          file=sys.stderr)
    print("       wheelhouse release yet. Pass --version X.Y.Z if you know",
          file=sys.stderr)
    print("       a specific version should exist.", file=sys.stderr)
    sys.exit(1)

best = max(candidates, key=semver_key)
print(best.removeprefix("wheelhouse-v"))
EOF
)"
  [ -n "$V" ] || fail "Could not resolve a version with Android wheels from GitHub releases. Pass --version X.Y.Z to specify one."
  info "Latest Android-wheelhouse version: $V"
fi

# ---------------------------------------------------------------------
# 2. Fetch the Android wheels from the GitHub release
# ---------------------------------------------------------------------
if [ "$DRY_RUN" -eq 0 ]; then
  mkdir -p "$WHEELHOUSE_DIR"
  # Clean previous run so a stale wheel can't shadow a new one.
  rm -f "$WHEELHOUSE_DIR"/*.whl

  info "Querying GitHub release $TAG for Android wheel assets..."

  ASSETS="$("$PYTHON_BIN" - <<EOF
import json, sys, urllib.request, urllib.error

tag = "$TAG"
url = f"https://api.github.com/repos/$REPO/releases/tags/{tag}"

try:
    with urllib.request.urlopen(url, timeout=30) as r:
        release = json.load(r)
except urllib.error.HTTPError as e:
    print(f"ERROR: release '{tag}' not found (HTTP {e.code}).", file=sys.stderr)
    print("       The monthly wheel-build workflow may not have run yet,", file=sys.stderr)
    print("       or this version was published before wheels were built.", file=sys.stderr)
    sys.exit(1)
except Exception as e:
    print(f"ERROR: {e}", file=sys.stderr)
    sys.exit(1)

assets = [a for a in release.get("assets", [])
          if a["name"].endswith(".whl") and "android_arm64_v8a" in a["name"]]

if not assets:
    print(f"ERROR: release '{tag}' has no android_arm64_v8a wheels.", file=sys.stderr)
    sys.exit(1)

for a in assets:
    print(a["browser_download_url"])
EOF
)"
  [ -n "$ASSETS" ] || fail "No Android wheel assets found in release $TAG."

  while IFS= read -r url; do
    [ -n "$url" ] || continue
    fname="$(basename "$url")"
    info "Downloading $fname"
    run curl -fL --retry 3 --retry-delay 2 -o "$WHEELHOUSE_DIR/$fname" "$url"
  done <<< "$ASSETS"

  count=$(find "$WHEELHOUSE_DIR" -name '*.whl' | wc -l)
  [ "$count" -gt 0 ] || fail "No wheels landed in $WHEELHOUSE_DIR."
  ok "Downloaded $count Android wheel(s) into $WHEELHOUSE_DIR"
else
  info "[dry-run] would download android wheels for $TAG into $WHEELHOUSE_DIR"
fi

# ---------------------------------------------------------------------
# 3. Create the venv
# ---------------------------------------------------------------------
info "Creating virtual environment at $VENV_DIR"
run "$PYTHON_BIN" -m venv "$VENV_DIR"

if [ -d "$VENV_DIR/Scripts" ]; then
  # Non-standard, but keep the branch for symmetry with install.sh.
  BIN_DIR="$VENV_DIR/Scripts"
  VENV_PYTHON="$VENV_DIR/Scripts/python.exe"
else
  BIN_DIR="$VENV_DIR/bin"
  VENV_PYTHON="$VENV_DIR/bin/python"
fi

# Pick the installer binary for the venv.
if [ "$PACKAGE_MANAGER" = "uv" ]; then
  if ! command -v uv >/dev/null 2>&1; then
    fail "--uv was requested but 'uv' is not on PATH. Install it or drop --uv."
  fi
  PIP_BIN="$(command -v uv)"
  PIP_PREFIX=("$PIP_BIN" pip install --python "$VENV_PYTHON")
else
  PIP_BIN="$BIN_DIR/pip"
  PIP_PREFIX=("$PIP_BIN" install)
fi

run "${PIP_PREFIX[@]}" --upgrade pip wheel setuptools

# ---------------------------------------------------------------------
# 4. Pre-install the compiled dependencies from the wheelhouse
# ---------------------------------------------------------------------
# --no-deps so lxml (which is not in the wheelhouse) is not pulled in yet.
# Passing all wheels in one invocation lets pip resolve inter-wheel deps.
if [ "$DRY_RUN" -eq 0 ]; then
  shopt -s nullglob
  wheels=("$WHEELHOUSE_DIR"/*.whl)
  shopt -u nullglob
  if [ "${#wheels[@]}" -eq 0 ]; then
    fail "No wheels found in $WHEELHOUSE_DIR."
  fi
  info "Installing ${#wheels[@]} pre-built Android wheel(s)..."
  run "${PIP_PREFIX[@]}" --no-deps "${wheels[@]}"
else
  info "[dry-run] would install wheels from $WHEELHOUSE_DIR"
fi

# ---------------------------------------------------------------------
# 5. Build lxml from source — strategy ladder
# ---------------------------------------------------------------------
# lxml is deliberately not in the wheelhouse (its Android cross-compile is
# broken upstream), so we build it here against Termux's libxml2/libxslt.
info "Installing lxml (this can take 5–20 minutes on a phone)..."

info "Installing lxml build dependencies..."
run pkg install -y clang libxml2 libxslt libiconv make python-dev pkg-config || \
  warn "Some build dependencies failed to install; lxml may fail."

export CFLAGS="-I${PREFIX}/include/libxml2 -I${PREFIX}/include"
export LDFLAGS="-L${PREFIX}/lib -Wl,-rpath,${PREFIX}/lib"
export XML2_CONFIG="${PREFIX}/bin/xml2-config"
export XSLT_CONFIG="${PREFIX}/bin/xslt-config"

LXML_OK=0

try_lxml() {
  local label="$1"; shift
  info "lxml attempt: $label"
  if run "${PIP_PREFIX[@]}" "$@"; then
    ok "lxml built successfully ($label)"
    LXML_OK=1
    return 0
  fi
  warn "lxml attempt failed ($label)"
  return 1
}

# Attempt 1: plain build.
try_lxml "plain source build" lxml || \
# Attempt 2: no build isolation (uses Termux's Cython/setuptools).
try_lxml "without build isolation" --no-build-isolation lxml || \
# Attempt 3: -O0 (known workaround for ARM optimisation crashes).
{
  info "lxml attempt: -O0 (ARM optimisation workaround)"
  if run bash -c "CFLAGS='-O0' ${PIP_PREFIX[*]} lxml"; then
    ok "lxml built successfully (-O0)"
    LXML_OK=1
  fi
} || \
# Attempt 4: known-good older version.
try_lxml "pinned lxml==5.2.2" "lxml==5.2.2" || true

if [ "$LXML_OK" -eq 0 ] && [ "$DRY_RUN" -eq 0 ]; then
  fail "lxml could not be built. open-news-api cannot be installed without it.
Manual fallback:
  pkg install -y clang libxml2 libxslt libiconv make python-dev pkg-config
  export CFLAGS='-I\$PREFIX/include/libxml2 -I\$PREFIX/include'
  export LDFLAGS='-L\$PREFIX/lib -Wl,-rpath,\$PREFIX/lib'
  ${PIP_PREFIX[*]} --no-build-isolation lxml"
fi

# ---------------------------------------------------------------------
# 6. Install open-news-api normally (deps NOT skipped)
# ---------------------------------------------------------------------
# pip now sees all compiled deps satisfied and will only pull the
# pure-Python ones from PyPI.
if [ "$JS_MODE" = "ask" ]; then
  js_choice=$(ask_choice \
    "Install the optional JavaScript-rendering extra (Playwright + Chromium, ~300MB)?" 2 \
    "Yes, now" \
    "No, I can add it later with: pip install \"open-news-api[js]\" && playwright install chromium")
  [ "$js_choice" = "1" ] && JS_MODE="yes" || JS_MODE="no"
fi

SPEC="${PKG}==${V}"
[ "$JS_MODE" = "yes" ] && SPEC="${PKG}[js]==${V}"

info "Installing $SPEC"
run "${PIP_PREFIX[@]}" "$SPEC"

if [ "$JS_MODE" = "yes" ]; then
  info "Installing Playwright's Chromium browser (~300MB download)..."
  run "$BIN_DIR/playwright" install chromium
fi

# ---------------------------------------------------------------------
# 7. PATH handling (same logic as install.sh)
# ---------------------------------------------------------------------
OPEN_NEWS_BIN="$BIN_DIR/open-news"
if [ "$DRY_RUN" -eq 0 ] && [ -x "$OPEN_NEWS_BIN" ] && ! command -v open-news >/dev/null 2>&1; then
  case "$(basename "${SHELL:-bash}")" in
    zsh) SHELL_RC="${HOME}/.zshrc" ;;
    fish) SHELL_RC="${HOME}/.config/fish/config.fish" ;;
    *) SHELL_RC="${HOME}/.bashrc" ;;
  esac
  LINE="export PATH=\"$BIN_DIR:\$PATH\""
  if [ "$(basename "${SHELL:-bash}")" = "fish" ]; then
    LINE="set -gx PATH \"$BIN_DIR\" \$PATH"
  fi
  if ! grep -qsF "$BIN_DIR" "$SHELL_RC" 2>/dev/null; then
    printf '\n# added by open-news installer\n%s\n' "$LINE" >> "$SHELL_RC"
    warn "Added $BIN_DIR to PATH in $SHELL_RC — restart your shell, or run:"
    warn "  $LINE"
  fi
fi

# ---------------------------------------------------------------------
# 8. First-run preferences -> config.json
# ---------------------------------------------------------------------
info "A few defaults — these are written once and used by the CLI/TUI unless overridden per-run."
PREF_LANGUAGE=$(ask_text "Default language filter (ISO 639-1, blank = none)" "")
PREF_CATEGORY=$(ask_text "Default fetch category" "general")
PREF_SORT=$(ask_text "Default sort (date/relevance/popularity)" "date")
PREF_FORMAT=$(ask_text "Default CLI output format (pretty/json)" "pretty")

info "Writing preferences to $CONFIG_FILE"
run mkdir -p "$CONFIG_DIR"
if [ "$DRY_RUN" -eq 0 ]; then
  cat > "$CONFIG_FILE" <<EOF
{
  "language": $( [ -n "$PREF_LANGUAGE" ] && printf '"%s"' "$PREF_LANGUAGE" || printf 'null' ),
  "category": "$PREF_CATEGORY",
  "sort_by": "$PREF_SORT",
  "format": "$PREF_FORMAT"
}
EOF
  mkdir -p "$(dirname "$STATE_FILE")"
  cat > "$STATE_FILE" <<EOF
{
  "mode": "quick",
  "platform": "termux",
  "package_manager": "$PACKAGE_MANAGER",
  "version": "$V",
  "venv_dir": "$VENV_DIR",
  "bin_dir": "$BIN_DIR",
  "js_extra": $( [ "$JS_MODE" = "yes" ] && printf 'true' || printf 'false' ),
  "installed_at": "$(date -u +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || echo unknown)"
}
EOF
fi

# ---------------------------------------------------------------------
# 9. Verify
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
  "$VENV_PYTHON" -m open_news.cli --version || fail "Verification failed. Try: $VENV_PYTHON -m open_news.cli --version"
  echo "Run it with: $VENV_PYTHON -m open_news.cli --help"
fi

# ---------------------------------------------------------------------
# 10. Offer to launch the TUI
# ---------------------------------------------------------------------
if [ "$ASSUME_YES" -eq 0 ]; then
  read -r -p $'\nLaunch the terminal interface now? [y/N]: ' launch || true
  if [ "${launch:-N}" = "y" ] || [ "${launch:-N}" = "Y" ]; then
    if [ -x "${BIN_DIR}/open-news-tui" ]; then
      exec "${BIN_DIR}/open-news-tui"
    else
      exec "$VENV_PYTHON" -m open_news.tui
    fi
  fi
fi