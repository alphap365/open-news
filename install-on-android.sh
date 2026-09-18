#!/usr/bin/env bash
# open-news installer for Termux / Android
#
#   curl -fsSL https://raw.githubusercontent.com/alphap365/open-news/main/install-on-android.sh | bash
#   ./install-on-android.sh --yes
#   ./install-on-android.sh --uv
#   ./install-on-android.sh --version 1.0.3a2
#   ./install-on-android.sh --dry-run
#   ./install-on-android.sh --uninstall
#
# News-fetch backend note: on Termux, `ddgs` is skipped automatically at
# runtime (its `primp` dependency panics with SIGABRT on Android — see
# open_news/feeds/duckduckgo_engine.py). `duckpy` (pure Python/httpx) is
# the primary DDG backend here instead, with a manual HTML scraper as
# the last-resort fallback. Both install normally via pip; no special
# handling needed in this script.
set -euo pipefail

REPO="alphap365/open-news"
PKG="open-news-api"
VENV_DIR="${HOME}/.open-news/venv"
CONFIG_DIR="${HOME}/.config/open-news"
CONFIG_FILE="${CONFIG_DIR}/config.json"
STATE_FILE="${HOME}/.open-news/install-state.json"
WHEELHOUSE_DIR="${HOME}/.open-news/wheelhouse"

: "${PREFIX:=/data/data/com.termux/files/usr}"

ASSUME_YES=0
JS_MODE="ask"
PACKAGE_MANAGER="ask"
DRY_RUN=0
DO_UNINSTALL=0
PIN_VERSION=""

while [ $# -gt 0 ]; do
  case "$1" in
    --yes|-y)    ASSUME_YES=1 ;;
    --js)        JS_MODE="yes" ;;
    --no-js)     JS_MODE="no" ;;
    --uv)        PACKAGE_MANAGER="uv" ;;
    --pip)       PACKAGE_MANAGER="pip" ;;
    --dry-run)   DRY_RUN=1 ;;
    --uninstall) DO_UNINSTALL=1 ;;
    --dev)
      printf 'Error: --dev is not supported on Termux.\n' >&2
      printf '       git clone https://github.com/%s.git ~/open-news\n' "$REPO" >&2
      printf '       cd ~/open-news && python -m venv .venv && .venv/bin/pip install -e ".[dev]"\n' >&2
      exit 2
      ;;
    --version)
      if [ $# -lt 2 ] || [ -z "${2:-}" ] || [ "${2#-}" != "$2" ]; then
        printf 'Error: --version requires a value, e.g. --version 1.0.3a2\n' >&2
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
      sed -n '2,15p' "$0" | sed 's/^# \{0,1\}//'
      exit 0
      ;;
    *)
      printf 'Unknown option: %s\n' "$1" >&2
      exit 2
      ;;
  esac
  shift
done

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
  if [ "$ASSUME_YES" -eq 1 ]; then echo "$default_idx"; return; fi
  printf '\n%s\n' "$prompt" >&2
  local i=1
  for opt in "${options[@]}"; do
    local marker=" "
    [ "$i" -eq "$default_idx" ] && marker="*"
    printf '  [%s%d] %s\n' "$marker" "$i" "$opt" >&2
  done
  local reply
  read -r -p "Choose [default ${default_idx}]: " reply
  if [ -z "$reply" ]; then echo "$default_idx"; else echo "$reply"; fi
}

ask_text() {
  local prompt="$1" default="$2" reply
  if [ "$ASSUME_YES" -eq 1 ]; then echo "$default"; return; fi
  read -r -p "$prompt [$default]: " reply >&2 || true
  echo "${reply:-$default}"
}

if [ "$DO_UNINSTALL" -eq 1 ]; then
  info "Removing ${HOME}/.open-news"
  rm -rf "${HOME}/.open-news"

  for cmd in open-news open-news-tui; do
    if [ -f "$PREFIX/bin/$cmd" ]; then
      if grep -q 'added by open-news installer' "$PREFIX/bin/$cmd" 2>/dev/null; then
        rm -f "$PREFIX/bin/$cmd"
        ok "Removed $PREFIX/bin/$cmd"
      fi
    fi
  done

  read -r -p "Also remove preferences at $CONFIG_FILE? [y/N]: " reply || true
  if [ "${reply:-N}" = "y" ] || [ "${reply:-N}" = "Y" ]; then
    rm -rf "$CONFIG_DIR"
    ok "Removed $CONFIG_DIR"
  fi
  ok "Uninstalled."
  exit 0
fi

printf '\n\033[1m open-news installer (Android / Termux)\033[0m\n\n'

# ---------------------------------------------------------------------
# 0. Sanity checks
# ---------------------------------------------------------------------
if ! command -v pkg >/dev/null 2>&1; then
  fail "This installer is for Termux (no 'pkg' command found). Use install.sh instead."
fi

info "Ensuring Python is installed..."
run pkg install -y python || fail "Could not install Python."

PYTHON_BIN="$(command -v python3 || command -v python || true)"
[ -n "$PYTHON_BIN" ] || fail "No python3 on PATH."

PY_VERSION="$("$PYTHON_BIN" -c 'import sys; print("%d.%d" % sys.version_info[:2])')"
PY_MINOR="${PY_VERSION#3.}"
case "$PY_MINOR" in
  ''|*[!0-9]*) fail "Could not parse Python version: $PY_VERSION" ;;
esac

if [ "$PY_MINOR" -lt 13 ]; then
  warn "Detected Python $PY_VERSION, but Android wheels require 3.13+."
  fail "Upgrade Termux's Python: pkg upgrade python"
fi
ok "Python $PY_VERSION ($PYTHON_BIN)"

# ---------------------------------------------------------------------
# 0b. TLS trust store for Python
# ---------------------------------------------------------------------
info "Ensuring CA certificates are installed..."
run pkg install -y ca-certificates || warn "Could not install ca-certificates."

CERT_FILE="${PREFIX}/etc/tls/cert.pem"
if [ -f "$CERT_FILE" ]; then
  export SSL_CERT_FILE="$CERT_FILE"
  export REQUESTS_CA_BUNDLE="$CERT_FILE"
  export CURL_CA_BUNDLE="$CERT_FILE"
  export PIP_CERT="$CERT_FILE"
  export SSL_CERT_DIR="${PREFIX}/etc/tls"
  ok "Using Termux CA bundle: $CERT_FILE"
else
  warn "CA bundle not found at $CERT_FILE — HTTPS may fail."
  warn "If it does, run: pkg install ca-certificates"
fi

# ---------------------------------------------------------------------
# 1. Resolve the open-news-api version
# ---------------------------------------------------------------------
if [ -n "$PIN_VERSION" ]; then
  V="$PIN_VERSION"
  info "Using pinned version: $V"
else
  info "Resolving latest version with Android wheels from GitHub releases..."
  V="$(REPO="$REPO" "$PYTHON_BIN" - <<'PY'
import json, os, re, sys, urllib.request, urllib.error

REPO = os.environ["REPO"]
url = f"https://api.github.com/repos/{REPO}/releases?per_page=100"
req = urllib.request.Request(url, headers={
    "Accept": "application/vnd.github+json",
    "User-Agent": "open-news-installer",
})
if os.environ.get("GITHUB_TOKEN"):
    req.add_header("Authorization", f"Bearer {os.environ['GITHUB_TOKEN']}")

try:
    with urllib.request.urlopen(req, timeout=30) as r:
        releases = json.load(r)
except urllib.error.HTTPError as e:
    print(f"ERROR: GitHub API HTTP {e.code}", file=sys.stderr); sys.exit(1)
except Exception as e:
    print(f"ERROR: {e}", file=sys.stderr); sys.exit(1)

def semver_key(tag):
    v = tag.removeprefix("v")
    m = re.match(r"^(\d+)\.(\d+)\.(\d+)(?:([abc]|rc)(\d+))?$", v)
    if not m: return (0, 0, 0, 0, 0)
    major, minor, patch, pre, pre_n = m.groups()
    rank = {"a": 1, "b": 2, "rc": 3, "": 4}[pre or ""]
    return (int(major), int(minor), int(patch), rank, int(pre_n or 0))

# Single tag scheme now: every release (vX.Y.Z) may carry both the
# package's own dist and depwheel-*.whl dependency wheels side by side.
all_releases = [r for r in releases if re.match(r"^v\d+\.\d+\.\d+", r.get("tag_name", ""))]
candidates = [
    r["tag_name"] for r in all_releases
    if any(a["name"].startswith("depwheel-") and "android_" in a["name"] and "arm64_v8a" in a["name"]
           for a in r.get("assets", []))
]
if not candidates:
    print("ERROR: no release with depwheel-*android_arm64_v8a* wheels found.", file=sys.stderr)
    if not all_releases:
        print("       No v* releases exist at all.", file=sys.stderr)
    else:
        print(f"       {len(all_releases)} release(s), none with android depwheels:",
              file=sys.stderr)
        for r in all_releases[:10]:
            n = sum(1 for a in r.get("assets", [])
                    if a["name"].startswith("depwheel-") and "android" in a["name"])
            print(f"         {r['tag_name']}: {n} android depwheel(s)", file=sys.stderr)
    print("       Pass --version X.Y.Z to pin a version.", file=sys.stderr)
    sys.exit(1)

best = max(candidates, key=semver_key)
print(best.removeprefix("v"))
PY
)"
  [ -n "$V" ] || fail "Could not resolve version. Pass --version X.Y.Z."
  ok "Latest Android-depwheel version: $V"
fi

TAG="v${V}"
info "Fetching release: $TAG"

# ---------------------------------------------------------------------
# 2. Download the Android wheels
# ---------------------------------------------------------------------
if [ "$DRY_RUN" -eq 0 ]; then
  mkdir -p "$WHEELHOUSE_DIR"
  rm -f "$WHEELHOUSE_DIR"/*.whl 2>/dev/null || true

  ASSETS="$(REPO="$REPO" TAG="$TAG" "$PYTHON_BIN" - <<'PY'
import json, os, sys, urllib.request, urllib.error

repo = os.environ["REPO"]
tag = os.environ["TAG"]
url = f"https://api.github.com/repos/{repo}/releases/tags/{tag}"
req = urllib.request.Request(url, headers={
    "Accept": "application/vnd.github+json",
    "User-Agent": "open-news-installer",
})
if os.environ.get("GITHUB_TOKEN"):
    req.add_header("Authorization", f"Bearer {os.environ['GITHUB_TOKEN']}")

try:
    with urllib.request.urlopen(req, timeout=30) as r:
        release = json.load(r)
except urllib.error.HTTPError as e:
    print(f"ERROR: HTTP {e.code} for release '{tag}'", file=sys.stderr); sys.exit(1)
except Exception as e:
    print(f"ERROR: {e}", file=sys.stderr); sys.exit(1)

# Only depwheel-*.whl assets, further scoped to android_*arm64_v8a — this
# is also what stops us ever grabbing the release's own open_news_api-*
# package wheel by accident, since both now live in the same release.
assets = [a for a in release.get("assets", [])
          if a["name"].endswith(".whl")
          and a["name"].startswith("depwheel-")
          and "android_" in a["name"] and "arm64_v8a" in a["name"]]
if not assets:
    print(f"ERROR: release '{tag}' has no depwheel-*android* wheels.", file=sys.stderr)
    sys.exit(1)
for a in assets:
    print(a["browser_download_url"])
PY
)"
  [ -n "$ASSETS" ] || fail "No Android wheels in release $TAG."

  while IFS= read -r url; do
    [ -n "$url" ] || continue
    fname="$(basename "$url")"
    # Strip the depwheel- prefix locally so downstream tag-parsing
    # (cut -d- -f1-2, etc. in step 5) sees the real wheel filename.
    real_name="${fname#depwheel-}"
    info "Downloading $real_name"
    run curl -fL --retry 3 --retry-delay 2 --retry-connrefused \
      -o "$WHEELHOUSE_DIR/$real_name" "$url"
  done <<< "$ASSETS"

  count=$(find "$WHEELHOUSE_DIR" -maxdepth 1 -name '*.whl' | wc -l)
  [ "$count" -gt 0 ] || fail "No wheels downloaded."
  ok "Downloaded $count wheel(s)."
fi

# ---------------------------------------------------------------------
# 3. Create venv
# ---------------------------------------------------------------------
info "Creating venv at $VENV_DIR"
run "$PYTHON_BIN" -m venv "$VENV_DIR"

if [ -d "$VENV_DIR/Scripts" ]; then
  BIN_DIR="$VENV_DIR/Scripts"
  VENV_PYTHON="$VENV_DIR/Scripts/python.exe"
else
  BIN_DIR="$VENV_DIR/bin"
  VENV_PYTHON="$VENV_DIR/bin/python"
fi

# Persist cert env vars into the venv's activate script.
if [ "$DRY_RUN" -eq 0 ] && [ -n "${SSL_CERT_FILE:-}" ] && [ -f "$VENV_DIR/bin/activate" ]; then
  if ! grep -qs 'SSL_CERT_FILE' "$VENV_DIR/bin/activate"; then
    cat >> "$VENV_DIR/bin/activate" <<EOF

# added by open-news installer — Termux CA bundle for httpx/requests
export SSL_CERT_FILE="$SSL_CERT_FILE"
export REQUESTS_CA_BUNDLE="$SSL_CERT_FILE"
export CURL_CA_BUNDLE="$SSL_CERT_FILE"
export SSL_CERT_DIR="$SSL_CERT_DIR"
EOF
    ok "Persisted CA bundle path into venv activate script."
  fi
fi

# ---------------------------------------------------------------------
# 4. Choose installer (pip or uv)
# ---------------------------------------------------------------------
if [ "$PACKAGE_MANAGER" = "ask" ]; then
  if command -v uv >/dev/null 2>&1; then
    pm_choice=$(ask_choice "Which installer for the venv?" 2 \
      "pip (venv's own)" "uv (system)")
    [ "$pm_choice" = "1" ] && PACKAGE_MANAGER="pip" || PACKAGE_MANAGER="uv"
  else
    PACKAGE_MANAGER="pip"
  fi
fi

if [ "$PACKAGE_MANAGER" = "uv" ]; then
  command -v uv >/dev/null 2>&1 || fail "--uv requested but uv not on PATH."
  PIP_PREFIX=("$(command -v uv)" pip install --python "$VENV_PYTHON")
else
  PIP_PREFIX=("$BIN_DIR/pip" install)
fi

run "${PIP_PREFIX[@]}" --upgrade pip wheel setuptools

# ---------------------------------------------------------------------
# 5. Reconcile wheel tags with this interpreter (ask pip directly)
# ---------------------------------------------------------------------
if [ "$DRY_RUN" -eq 0 ]; then
  info "Checking each wheel against this interpreter..."
  interp_py="$("$VENV_PYTHON" -c 'import sys; print(f"cp{sys.version_info.major}{sys.version_info.minor}")')"
  info "  interpreter: $interp_py"

  accepts_pip() {
    "$VENV_PYTHON" -m pip install --dry-run --no-deps --quiet \
      --disable-pip-version-check "$1" >/dev/null 2>&1
  }

  accept=()
  reject=()
  for whl in "$WHEELHOUSE_DIR"/*.whl; do
    [ -e "$whl" ] || continue
    if accepts_pip "$whl"; then
      info "  OK   $(basename "$whl")"
      accept+=("$whl")
    else
      warn "  FAIL $(basename "$whl")"
      reject+=("$whl")
    fi
  done

  for whl in "${reject[@]}"; do
    [ -e "$whl" ] || continue
    base="$(basename "$whl")"
    nv="$(printf '%s' "$base" | cut -d- -f1-2)"
    pytag="$(printf '%s' "$base" | cut -d- -f3)"
    abitag="$(printf '%s' "$base" | cut -d- -f4)"
    rest="$(printf '%s' "$base" | cut -d- -f5-)"

    if [ "$pytag" = "$abitag" ] && [ "${pytag#cp}" != "$pytag" ]; then
      bare="${abitag#cp}"
      newname="${nv}-${pytag}-${bare}-${rest}"
      info "  Trying rename: $base -> $newname"
      mv "$whl" "$WHEELHOUSE_DIR/$newname"
      whl="$WHEELHOUSE_DIR/$newname"
      if accepts_pip "$whl"; then
        info "  OK   $newname (after rename)"
        accept+=("$whl")
      else
        warn "  FAIL $newname (still rejected)"
      fi
    fi
  done

  for whl in "$WHEELHOUSE_DIR"/*.whl; do
    [ -e "$whl" ] || continue
    b="$(basename "$whl")"
    keep=0
    for k in "${accept[@]:-}"; do
      [ -n "$k" ] || continue
      [ "$b" = "$(basename "$k")" ] && keep=1 && break
    done
    if [ "$keep" -eq 0 ]; then
      warn "  Dropping $b (not accepted by this interpreter)"
      rm -f "$whl"
    fi
  done

  remaining=$(find "$WHEELHOUSE_DIR" -maxdepth 1 -name '*.whl' | wc -l)
  [ "$remaining" -gt 0 ] || fail "No wheels survived compatibility check for $interp_py."
  ok "$remaining wheel(s) usable on $interp_py."
fi

# ---------------------------------------------------------------------
# 6. Pre-install the compiled wheels
# ---------------------------------------------------------------------
if [ "$DRY_RUN" -eq 0 ]; then
  shopt -s nullglob
  wheels=("$WHEELHOUSE_DIR"/*.whl)
  shopt -u nullglob
  [ "${#wheels[@]}" -gt 0 ] || fail "No wheels in $WHEELHOUSE_DIR."

  info "Installing ${#wheels[@]} pre-built wheel(s)..."
  if ! run "${PIP_PREFIX[@]}" --no-deps --force-reinstall "${wheels[@]}"; then
    warn "pip rejected the wheels."
    warn "  interpreter: $VENV_PYTHON"
    warn "  platform:    $("$VENV_PYTHON" -c 'import sysconfig; print(sysconfig.get_platform())')"
    warn "  pip version: $("$VENV_PYTHON" -m pip --version)"
    fail "Wheel install failed."
  fi
fi

# ---------------------------------------------------------------------
# 7. Build lxml from source
# ---------------------------------------------------------------------
info "Installing lxml (5–20 minutes on a phone)..."
run pkg install -y clang libxml2 libxslt libiconv make python-dev pkg-config || \
  warn "Some build dependencies failed."

BASE_CFLAGS="-I${PREFIX}/include/libxml2 -I${PREFIX}/include"
export CFLAGS="$BASE_CFLAGS"
export LDFLAGS="-L${PREFIX}/lib -Wl,-rpath,${PREFIX}/lib"
export XML2_CONFIG="${PREFIX}/bin/xml2-config"
export XSLT_CONFIG="${PREFIX}/bin/xslt-config"

LXML_OK=0
reset_lxml() { [ "$DRY_RUN" -eq 0 ] && "${PIP_PREFIX[@]}" uninstall -y lxml >/dev/null 2>&1 || true; }
try_lxml() {
  local label="$1"; shift
  info "lxml attempt: $label"
  reset_lxml
  if run "${PIP_PREFIX[@]}" --no-cache-dir "$@"; then
    ok "lxml OK ($label)"; LXML_OK=1; return 0
  fi
  warn "lxml failed ($label)"; return 1
}

[ "$LXML_OK" -eq 0 ] && { try_lxml "plain" lxml || true; }
[ "$LXML_OK" -eq 0 ] && { try_lxml "no build isolation" --no-build-isolation lxml || true; }
if [ "$LXML_OK" -eq 0 ]; then
  info "lxml attempt: with -O0"
  reset_lxml
  if CFLAGS="$BASE_CFLAGS -O0" run "${PIP_PREFIX[@]}" --no-cache-dir lxml; then
    ok "lxml OK (with -O0)"; LXML_OK=1
  else
    warn "lxml failed (with -O0)"
  fi
fi
[ "$LXML_OK" -eq 0 ] && { try_lxml "pinned 5.2.2" "lxml==5.2.2" || true; }

if [ "$LXML_OK" -eq 0 ] && [ "$DRY_RUN" -eq 0 ]; then
  fail "lxml could not be built. Manual fallback:
  pkg install -y clang libxml2 libxslt libiconv make python-dev pkg-config
  export CFLAGS='-I\$PREFIX/include/libxml2 -I\$PREFIX/include'
  export LDFLAGS='-L\$PREFIX/lib -Wl,-rpath,\$PREFIX/lib'
  ${PIP_PREFIX[*]} --no-build-isolation lxml"
fi

# ---------------------------------------------------------------------
# 8. Install open-news-api
# ---------------------------------------------------------------------
if [ "$JS_MODE" = "ask" ]; then
  js_choice=$(ask_choice \
    "Install the JS extra (Playwright + Chromium, ~300MB)?" 2 \
    "Yes" "No")
  [ "$js_choice" = "1" ] && JS_MODE="yes" || JS_MODE="no"
fi

SPEC="${PKG}==${V}"
[ "$JS_MODE" = "yes" ] && SPEC="${PKG}[js]==${V}"

info "Installing $SPEC"
run "${PIP_PREFIX[@]}" "$SPEC"

if [ "$JS_MODE" = "yes" ]; then
  info "Installing Playwright's Chromium..."
  if [ -x "${BIN_DIR}/playwright" ]; then
    run "${BIN_DIR}/playwright" install chromium
  else
    run "$VENV_PYTHON" -m playwright install chromium
  fi
fi

# ---------------------------------------------------------------------
# 9. Verify network connectivity and DDG backend availability
# ---------------------------------------------------------------------
if [ "$DRY_RUN" -eq 0 ]; then
  info "Verifying Python HTTPS works..."

  # Test 1: with environment variables set (how the wrapper runs it)
  if "$VENV_PYTHON" - <<'PY' 2>/tmp/net-check.err
import httpx, sys
try:
    r = httpx.get("https://news.google.com/rss", timeout=15)
    print(f"  RSS fetch: HTTP {r.status_code}, {len(r.content)} bytes")
    sys.exit(0)
except Exception as e:
    print(f"  RSS fetch failed: {type(e).__name__}: {e}", file=sys.stderr)
    sys.exit(1)
PY
  then
    ok "HTTPS reachable from the venv Python."
  else
    warn "HTTPS from Python failed. First 5 lines of the error:"
    sed -n '1,5p' /tmp/net-check.err >&2 || true
  fi

  # Test 2: without environment variables, relying on certifi alone.
  if env -u SSL_CERT_FILE -u REQUESTS_CA_BUNDLE -u CURL_CA_BUNDLE \
       "$VENV_PYTHON" - <<'PY' 2>/tmp/net-check2.err
import httpx, sys
try:
    r = httpx.get("https://news.google.com/rss", timeout=15)
    print(f"  certifi-only fetch: HTTP {r.status_code}, {len(r.content)} bytes")
    sys.exit(0)
except Exception as e:
    print(f"  certifi-only fetch failed: {type(e).__name__}: {e}", file=sys.stderr)
    sys.exit(1)
PY
  then
    ok "HTTPS works via certifi alone."
  else
    warn "HTTPS via certifi alone failed. First 5 lines:"
    sed -n '1,5p' /tmp/net-check2.err >&2 || true
  fi

  # Test 3: report which DuckDuckGo news backends are importable here.
  # ddgs is expected to be present but is skipped at runtime on Termux
  # (its `primp` dependency SIGABRTs) — duckpy is the real primary path.
  info "Checking DuckDuckGo backend availability..."
  "$VENV_PYTHON" - <<'PY' || true
checks = []
try:
    import ddgs  # noqa: F401
    checks.append(("ddgs", True, "installed (skipped at runtime on Termux)"))
except ImportError:
    checks.append(("ddgs", False, "not installed"))

try:
    import duckpy  # noqa: F401
    checks.append(("duckpy", True, "installed — primary backend on Termux"))
except ImportError:
    checks.append(("duckpy", False, "not installed — falls back to HTML scraper"))

for name, ok_, note in checks:
    mark = "OK  " if ok_ else "MISS"
    print(f"  [{mark}] {name}: {note}")
PY
fi

# ---------------------------------------------------------------------
# 10. Install launcher wrappers in $PREFIX/bin
# ---------------------------------------------------------------------
if [ "$DRY_RUN" -eq 0 ] && [ -d "$PREFIX/bin" ] && [ -w "$PREFIX/bin" ]; then
  for cmd in open-news open-news-tui; do
    if [ -x "$BIN_DIR/$cmd" ]; then
      wrapper="$PREFIX/bin/$cmd"
      if [ -e "$wrapper" ] && ! grep -q 'added by open-news installer' "$wrapper" 2>/dev/null; then
        warn "$wrapper exists and is not ours — skipping."
        continue
      fi
      cat > "$wrapper" <<EOF
#!${PREFIX}/bin/bash
# added by open-news installer
export SSL_CERT_FILE="${PREFIX}/etc/tls/cert.pem"
export REQUESTS_CA_BUNDLE="\$SSL_CERT_FILE"
export CURL_CA_BUNDLE="\$SSL_CERT_FILE"
export SSL_CERT_DIR="${PREFIX}/etc/tls"
exec "$BIN_DIR/$cmd" "\$@"
EOF
      chmod +x "$wrapper"
      ok "Installed launcher: $wrapper"
    fi
  done
else
  warn "$PREFIX/bin not writable — open-news not added to PATH."
  warn "Run directly: $BIN_DIR/open-news"
fi

# ---------------------------------------------------------------------
# 11. First-run preferences
# ---------------------------------------------------------------------
info "A few defaults — used by CLI/TUI unless overridden per-run."
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
  "cert_file": "${SSL_CERT_FILE:-}",
  "js_extra": $( [ "$JS_MODE" = "yes" ] && printf 'true' || printf 'false' ),
  "installed_at": "$(date -u +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || echo unknown)"
}
EOF
fi

# ---------------------------------------------------------------------
# 12. Verify
# ---------------------------------------------------------------------
if [ "$DRY_RUN" -eq 1 ]; then
  ok "Dry run complete."
  exit 0
fi

info "Verifying install..."
if command -v open-news >/dev/null 2>&1; then
  open-news --version && ok "Install verified."
  echo "Run it with: open-news --help"
elif [ -x "$BIN_DIR/open-news" ]; then
  "$BIN_DIR/open-news" --version && ok "Install verified."
  echo "Run it with: $BIN_DIR/open-news --help (or restart your shell)"
else
  fail "No open-news binary found."
fi

# ---------------------------------------------------------------------
# 13. Offer to launch the TUI
# ---------------------------------------------------------------------
if [ "$ASSUME_YES" -eq 0 ]; then
  read -r -p $'\nLaunch the terminal interface now? [y/N]: ' launch || true
  if [ "${launch:-N}" = "y" ] || [ "${launch:-N}" = "Y" ]; then
    if command -v open-news-tui >/dev/null 2>&1; then
      exec open-news-tui
    elif [ -x "${BIN_DIR}/open-news-tui" ]; then
      exec "${BIN_DIR}/open-news-tui"
    else
      exec "$VENV_PYTHON" -m open_news.tui
    fi
  fi
fi