#!/usr/bin/env bash
# open-news installer for Termux / Android
#
# The Termux-specific counterpart to install.sh. Invoked automatically by
# install.sh when Termux is detected, or run directly:
#
#   curl -fsSL https://raw.githubusercontent.com/alphap365/open-news/main/install-on-android.sh | bash
#   ./install-on-android.sh --yes               # non-interactive
#   ./install-on-android.sh --uv                # use uv instead of pip
#   ./install-on-android.sh --version 1.0.3a1   # pin a version
#   ./install-on-android.sh --version=1.0.3a1   # same, equals form
#   ./install-on-android.sh --dry-run
#   ./install-on-android.sh --uninstall
#
# Environment:
#   GITHUB_TOKEN   Optional. Used for the GitHub release lookup to avoid
#                  the unauthenticated 60 requests/hour rate limit.
#
set -euo pipefail

# ---------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------
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

# Termux always sets PREFIX, but be defensive — a non-Termux shell that
# somehow reaches this script should fail cleanly, not reference /lib.
: "${PREFIX:=/data/data/com.termux/files/usr}"

# ---------------------------------------------------------------------
# State
# ---------------------------------------------------------------------
ASSUME_YES=0
JS_MODE="ask"          # ask | yes | no
PACKAGE_MANAGER="ask"  # ask | pip | uv
DRY_RUN=0
DO_UNINSTALL=0
PIN_VERSION=""

# ---------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------
# Robust: handles --version <value>, --version=<value>, missing value,
# and prevents a subsequent flag from being swallowed as the value.
while [ $# -gt 0 ]; do
  case "$1" in
    --yes|-y)  ASSUME_YES=1 ;;
    --js)      JS_MODE="yes" ;;
    --no-js)   JS_MODE="no" ;;
    --uv)      PACKAGE_MANAGER="uv" ;;
    --pip)     PACKAGE_MANAGER="pip" ;;
    --dry-run) DRY_RUN=1 ;;
    --uninstall) DO_UNINSTALL=1 ;;

    --dev)
      printf 'Error: --dev is not supported on Termux.\n' >&2
      printf '       Developer installs should clone the repo and use uv/pip manually:\n' >&2
      printf '         git clone https://github.com/%s.git ~/open-news\n' "$REPO" >&2
      printf '         cd ~/open-news && python -m venv .venv && .venv/bin/pip install -e ".[dev]"\n' >&2
      exit 2
      ;;

    --version)
      if [ $# -lt 2 ] || [ -z "${2:-}" ] || [ "${2#-}" != "$2" ]; then
        printf 'Error: --version requires a value, e.g. --version 1.0.3a1\n' >&2
        exit 2
      fi
      PIN_VERSION="$2"
      shift
      ;;
    --version=*)
      PIN_VERSION="${1#--version=}"
      if [ -z "$PIN_VERSION" ]; then
        printf 'Error: --version= requires a value, e.g. --version=1.0.3a1\n' >&2
        exit 2
      fi
      ;;

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
# Uninstall path (short-circuits everything else)
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
# 0. Sanity checks
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

# Confirm pip advertises an android_* platform tag. If it doesn't, the
# pre-built wheels will be rejected no matter how we fetch them.
if ! "$PYTHON_BIN" -m pip debug --verbose 2>/dev/null | grep -qi "android"; then
  warn "pip does not advertise any 'android_*' platform tag."
  warn "The pre-built wheels may be rejected. Continuing — if the install"
  warn "fails with 'not a supported wheel', this is why."
else
  ok "pip advertises an android_* platform tag."
fi

# ---------------------------------------------------------------------
# 1. Resolve the open-news-api version we're installing
# ---------------------------------------------------------------------
# Deliberately NOT using PyPI's info.version: that tracks only the latest
# STABLE release, so a prerelease like 1.0.3a1 on top of 1.0.2 leaves
# info.version pointing at 1.0.2 — sending us to a wheelhouse-v1.0.2 tag
# that may not exist. We ask GitHub directly for the newest release that
# actually contains an android_arm64_v8a wheel; that is the set of versions
# installable on this platform.
if [ -n "$PIN_VERSION" ]; then
  V="$PIN_VERSION"
  info "Using pinned version: $V"
  info "Looking for Android wheels in release: wheelhouse-v${V}"
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
token = os.environ.get("GITHUB_TOKEN")
if token:
    req.add_header("Authorization", f"Bearer {token}")

try:
    with urllib.request.urlopen(req, timeout=30) as r:
        releases = json.load(r)
except urllib.error.HTTPError as e:
    if e.code == 403:
        print("ERROR: GitHub API rate limit reached (HTTP 403).", file=sys.stderr)
        print("       Set GITHUB_TOKEN to raise the limit, or pass", file=sys.stderr)
        print("       --version X.Y.Z to skip the lookup.", file=sys.stderr)
    else:
        print(f"ERROR: could not list GitHub releases (HTTP {e.code}).", file=sys.stderr)
    sys.exit(1)
except Exception as e:
    print(f"ERROR: could not list GitHub releases: {e}", file=sys.stderr)
    sys.exit(1)


def semver_key(tag):
    """Sort key: a < b < rc < final for the same x.y.z."""
    v = tag.removeprefix("wheelhouse-v")
    m = re.match(r"^(\d+)\.(\d+)\.(\d+)(?:([abc]|rc)(\d+))?$", v)
    if not m:
        return (0, 0, 0, 0, 0)
    major, minor, patch, pre, pre_n = m.groups()
    pre_rank = {"a": 1, "b": 2, "rc": 3, "": 4}[pre or ""]
    return (int(major), int(minor), int(patch), pre_rank, int(pre_n or 0))


wh_all = [r for r in releases if r.get("tag_name", "").startswith("wheelhouse-v")]
candidates = [
    r["tag_name"] for r in wh_all
    if any(("android_" in a["name"] and "arm64_v8a" in a["name"])
           for a in r.get("assets", []))
]

if not candidates:
    print("ERROR: no GitHub release with android_arm64_v8a wheels found.", file=sys.stderr)
    if not wh_all:
        print("       No wheelhouse-v* releases exist at all.", file=sys.stderr)
        print("       -> build_dep_wheel.yml has never published successfully.", file=sys.stderr)
        print("       -> Check the workflow's last run under the Actions tab;", file=sys.stderr)
        print("          a 403 on 'publish' means it needs 'permissions: contents: write'.", file=sys.stderr)
    else:
        print(f"       {len(wh_all)} wheelhouse release(s) exist, but none carry android wheels:", file=sys.stderr)
        for r in wh_all[:10]:
            n_total = len(r.get("assets", []))
            n_android = sum(1 for a in r.get("assets", []) if "android" in a["name"])
            print(f"         {r['tag_name']}: {n_total} assets, {n_android} android", file=sys.stderr)
        print("       -> The android row in compute_wheel_gaps.py may have been", file=sys.stderr)
        print("          added after these releases were built. Re-run the workflow.", file=sys.stderr)
    print("       Pass --version X.Y.Z if you know a specific version exists.", file=sys.stderr)
    sys.exit(1)

best = max(candidates, key=semver_key)
print(best.removeprefix("wheelhouse-v"))
PY
)"
  [ -n "$V" ] || fail "Could not resolve a version with Android wheels. Pass --version X.Y.Z to specify one."
  ok "Latest Android-wheelhouse version: $V"
  info "Looking for Android wheels in release: wheelhouse-v${V}"
fi

TAG="wheelhouse-v${V}"

# ---------------------------------------------------------------------
# 2. Fetch the Android wheels from the GitHub release
# ---------------------------------------------------------------------
if [ "$DRY_RUN" -eq 0 ]; then
  mkdir -p "$WHEELHOUSE_DIR"
  # Clean previous run so a stale wheel can't shadow a new one.
  rm -f "$WHEELHOUSE_DIR"/*.whl 2>/dev/null || true

  info "Querying GitHub release $TAG for Android wheel assets..."

  ASSETS="$(REPO="$REPO" TAG="$TAG" "$PYTHON_BIN" - <<'PY'
import json, os, sys, urllib.request, urllib.error

repo = os.environ["REPO"]
tag = os.environ["TAG"]
url = f"https://api.github.com/repos/{repo}/releases/tags/{tag}"
req = urllib.request.Request(url, headers={
    "Accept": "application/vnd.github+json",
    "User-Agent": "open-news-installer",
})
token = os.environ.get("GITHUB_TOKEN")
if token:
    req.add_header("Authorization", f"Bearer {token}")

try:
    with urllib.request.urlopen(req, timeout=30) as r:
        release = json.load(r)
except urllib.error.HTTPError as e:
    if e.code == 404:
        print(f"ERROR: release '{tag}' not found.", file=sys.stderr)
        print("       The wheel-build workflow may not have published yet, or", file=sys.stderr)
        print("       this version predates the Android wheelhouse pipeline.", file=sys.stderr)
    elif e.code == 403:
        print("ERROR: GitHub API rate limit reached (HTTP 403).", file=sys.stderr)
        print("       Set GITHUB_TOKEN to raise the limit.", file=sys.stderr)
    else:
        print(f"ERROR: could not fetch release '{tag}' (HTTP {e.code}).", file=sys.stderr)
    sys.exit(1)
except Exception as e:
    print(f"ERROR: could not fetch release '{tag}': {e}", file=sys.stderr)
    sys.exit(1)

assets = [a for a in release.get("assets", [])
          if a["name"].endswith(".whl")
          and "android_" in a["name"]
          and "arm64_v8a" in a["name"]]

if not assets:
    print(f"ERROR: release '{tag}' has no android_arm64_v8a wheels.", file=sys.stderr)
    print(f"       It has {len(release.get('assets', []))} asset(s) total.", file=sys.stderr)
    for a in release.get("assets", [])[:10]:
        print(f"         - {a['name']}", file=sys.stderr)
    sys.exit(1)

for a in assets:
    print(a["browser_download_url"])
PY
)"
  [ -n "$ASSETS" ] || fail "No Android wheel assets found in release $TAG."

  while IFS= read -r url; do
    [ -n "$url" ] || continue
    fname="$(basename "$url")"
    info "Downloading $fname"
    run curl -fL --retry 3 --retry-delay 2 --retry-connrefused \
      -o "$WHEELHOUSE_DIR/$fname" "$url"
  done <<< "$ASSETS"

  count=$(find "$WHEELHOUSE_DIR" -maxdepth 1 -name '*.whl' | wc -l)
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
  # Non-standard for Termux; kept for symmetry with install.sh.
  BIN_DIR="$VENV_DIR/Scripts"
  VENV_PYTHON="$VENV_DIR/Scripts/python.exe"
else
  BIN_DIR="$VENV_DIR/bin"
  VENV_PYTHON="$VENV_DIR/bin/python"
fi

# ---------------------------------------------------------------------
# 4a. Select the installer (pip or uv)
# ---------------------------------------------------------------------
if [ "$PACKAGE_MANAGER" = "ask" ]; then
  if command -v uv >/dev/null 2>&1; then
    pm_choice=$(ask_choice \
      "Which installer should be used for the venv?" 2 \
      "pip (bundled with the venv)" \
      "uv (faster, uses the uv on PATH)")
    [ "$pm_choice" = "1" ] && PACKAGE_MANAGER="pip" || PACKAGE_MANAGER="uv"
  else
    PACKAGE_MANAGER="pip"
  fi
fi

if [ "$PACKAGE_MANAGER" = "uv" ]; then
  if ! command -v uv >/dev/null 2>&1; then
    fail "--uv was requested but 'uv' is not on PATH. Install it or drop --uv."
  fi
  UV_BIN="$(command -v uv)"
  PIP_PREFIX=("$UV_BIN" pip install --python "$VENV_PYTHON")
else
  PIP_PREFIX=("$BIN_DIR/pip" install)
fi

info "Upgrading packaging tools in the venv..."
run "${PIP_PREFIX[@]}" --upgrade pip wheel setuptools

# ---------------------------------------------------------------------
# 4b. Reconcile platform tags between the wheels and this interpreter
# ---------------------------------------------------------------------
# Termux's Python historically reports a "linux_aarch64" platform tag
# rather than the "android_24_arm64_v8a" tag used by cibuildwheel's
# android wheels. The binary inside is aarch64/bionic either way, so
# installing works — but pip's tag check rejects it first. If pip does
# not advertise an android_* tag for arm64, rewrite the downloaded wheel
# filenames to use linux_aarch64, which pip will accept.
if [ "$DRY_RUN" -eq 0 ]; then
  if "$VENV_PYTHON" -m pip debug --verbose 2>/dev/null \
       | grep -qE "android_[0-9]+_arm64_v8a"; then
    info "pip accepts android_* platform tags — leaving wheels unmodified."
  else
    warn "This Python does not advertise an android_* platform tag."
    warn "Rewriting android_24_arm64_v8a -> linux_aarch64 in the wheel"
    warn "filenames so pip will accept them. The binary contents are"
    warn "unchanged; only the platform tag string differs."
    renamed=0
    for whl in "$WHEELHOUSE_DIR"/*.whl; do
      [ -e "$whl" ] || continue
      newname="$(printf '%s' "$whl" \
        | sed -E 's/-android_[0-9]+_arm64_v8a\.whl$/-linux_aarch64.whl/')"
      if [ "$whl" != "$newname" ]; then
        mv "$whl" "$newname"
        info "  $(basename "$whl") -> $(basename "$newname")"
        renamed=$((renamed + 1))
      fi
    done
    [ "$renamed" -gt 0 ] || warn "No wheels needed renaming (unexpected)."
    ok "Renamed $renamed wheel(s) for this interpreter's platform tag."
  fi
fi

# ---------------------------------------------------------------------
# 5. Pre-install the compiled dependencies from the wheelhouse
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
  # --force-reinstall so a partial previous run cannot leave a stale copy.
  run "${PIP_PREFIX[@]}" --no-deps --force-reinstall "${wheels[@]}"
else
  info "[dry-run] would install wheels from $WHEELHOUSE_DIR"
fi

# ---------------------------------------------------------------------
# 6. Build lxml from source — strategy ladder
# ---------------------------------------------------------------------
# lxml is deliberately not in the wheelhouse (its Android cross-compile is
# broken upstream), so we build it here against Termux's libxml2/libxslt.
info "Installing lxml (this can take 5–20 minutes on a phone)..."

info "Installing lxml build dependencies..."
run pkg install -y clang libxml2 libxslt libiconv make python-dev pkg-config || \
  warn "Some build dependencies failed to install; lxml may fail."

BASE_CFLAGS="-I${PREFIX}/include/libxml2 -I${PREFIX}/include"
export CFLAGS="$BASE_CFLAGS"
export LDFLAGS="-L${PREFIX}/lib -Wl,-rpath,${PREFIX}/lib"
export XML2_CONFIG="${PREFIX}/bin/xml2-config"
export XSLT_CONFIG="${PREFIX}/bin/xslt-config"

LXML_OK=0

# Reset any partial state a previous attempt might have left behind, so
# that a reported success reflects a genuinely successful build.
reset_lxml() {
  if [ "$DRY_RUN" -eq 0 ]; then
    "${PIP_PREFIX[@]}" uninstall -y lxml >/dev/null 2>&1 || true
  fi
}

try_lxml() {
  local label="$1"; shift
  info "lxml attempt: $label"
  reset_lxml
  if run "${PIP_PREFIX[@]}" --no-cache-dir "$@"; then
    ok "lxml built successfully ($label)"
    LXML_OK=1
    return 0
  fi
  warn "lxml attempt failed ($label)"
  return 1
}

# Attempt 1: plain source build (works when Termux's libxml2/libxslt are
# current and picked up via pkg-config).
if [ "$LXML_OK" -eq 0 ]; then
  try_lxml "plain source build" lxml || true
fi

# Attempt 2: no build isolation (uses Termux's Cython/setuptools instead
# of pip's isolated build environment).
if [ "$LXML_OK" -eq 0 ]; then
  try_lxml "without build isolation" --no-build-isolation lxml || true
fi

# Attempt 3: -O0. Known workaround when Termux's clang at -O2 miscompiles
# or crashes on some Android toolchains. Uses an env-var prefix, not a
# re-parsed bash -c string, so paths with spaces or shell metacharacters
# are handled correctly.
if [ "$LXML_OK" -eq 0 ]; then
  info "lxml attempt: with -O0 (ARM optimisation workaround)"
  reset_lxml
  if CFLAGS="$BASE_CFLAGS -O0" run "${PIP_PREFIX[@]}" --no-cache-dir lxml; then
    ok "lxml built successfully (with -O0)"
    LXML_OK=1
  else
    warn "lxml attempt failed (with -O0)"
  fi
fi

# Attempt 4: pinned older lxml — last-resort known-good version if the
# current tip release has regressed against Termux's libxml2.
if [ "$LXML_OK" -eq 0 ]; then
  try_lxml "pinned lxml==5.2.2" "lxml==5.2.2" || true
fi

if [ "$LXML_OK" -eq 0 ] && [ "$DRY_RUN" -eq 0 ]; then
  fail "lxml could not be built. open-news-api cannot be installed without it.
Manual fallback:
  pkg install -y clang libxml2 libxslt libiconv make python-dev pkg-config
  export CFLAGS='-I\$PREFIX/include/libxml2 -I\$PREFIX/include'
  export LDFLAGS='-L\$PREFIX/lib -Wl,-rpath,\$PREFIX/lib'
  ${PIP_PREFIX[*]} --no-build-isolation lxml"
fi

# ---------------------------------------------------------------------
# 7. Install open-news-api (deps NOT skipped)
# ---------------------------------------------------------------------
# pip now sees all compiled deps satisfied and pulls only the pure-Python
# ones from PyPI.
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

# ---------------------------------------------------------------------
# 8. Playwright browser (only if the JS extra was requested)
# ---------------------------------------------------------------------
if [ "$JS_MODE" = "yes" ]; then
  info "Installing Playwright's Chromium browser (~300MB download)..."
  if [ -x "${BIN_DIR}/playwright" ]; then
    run "${BIN_DIR}/playwright" install chromium
  else
    run "$VENV_PYTHON" -m playwright install chromium
  fi
fi

# ---------------------------------------------------------------------
# 9. PATH handling
# ---------------------------------------------------------------------
OPEN_NEWS_BIN="$BIN_DIR/open-news"
if [ "$DRY_RUN" -eq 0 ] && [ -x "$OPEN_NEWS_BIN" ] && ! command -v open-news >/dev/null 2>&1; then
  case "$(basename "${SHELL:-bash}")" in
    zsh)  SHELL_RC="${HOME}/.zshrc" ;;
    fish) SHELL_RC="${HOME}/.config/fish/config.fish" ;;
    *)    SHELL_RC="${HOME}/.bashrc" ;;
  esac
  if [ "$(basename "${SHELL:-bash}")" = "fish" ]; then
    LINE="set -gx PATH \"$BIN_DIR\" \$PATH"
  else
    LINE="export PATH=\"$BIN_DIR:\$PATH\""
  fi
  if ! grep -qsF "$BIN_DIR" "$SHELL_RC" 2>/dev/null; then
    printf '\n# added by open-news installer\n%s\n' "$LINE" >> "$SHELL_RC"
    warn "Added $BIN_DIR to PATH in $SHELL_RC — restart your shell, or run:"
    warn "  $LINE"
  fi
fi

# ---------------------------------------------------------------------
# 10. First-run preferences -> config.json
# ---------------------------------------------------------------------
info "A few defaults — written once and used by the CLI/TUI unless overridden per-run."
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
# 11. Verify
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
  "$VENV_PYTHON" -m open_news.cli --version || \
    fail "Verification failed. Try: $VENV_PYTHON -m open_news.cli --version"
  echo "Run it with: $VENV_PYTHON -m open_news.cli --help"
fi

# ---------------------------------------------------------------------
# 12. Offer to launch the TUI
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