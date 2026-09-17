#!/usr/bin/env bash
# open-news installer for Termux / Android
#
#   curl -fsSL https://raw.githubusercontent.com/alphap365/open-news/main/install-on-android.sh | bash
#   ./install-on-android.sh --yes               # non-interactive
#   ./install-on-android.sh --uv                # use uv instead of pip
#   ./install-on-android.sh --version 1.0.3a2   # pin a version
#   ./install-on-android.sh --dry-run
#   ./install-on-android.sh --uninstall
#
# Environment:
#   GITHUB_TOKEN   Optional. Used for the GitHub release lookup.
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
  read -r -p "Also remove preferences at $CONFIG_FILE? [y/N]: " reply || true
  if [ "${reply:-N}" = "y" ] || [ "${reply:-N}" = "Y" ]; then
    rm -rf "$CONFIG_DIR"
    ok "Removed $CONFIG_DIR"
  fi
  ok "Uninstalled."
  exit 0
fi

printf '\n\033[1m open-news installer (Android / Termux)\033[0m\n\n'

if ! command -v pkg >/dev/null 2>&1; then
  fail "This installer is for Termux (no 'pkg' command found). Use install.sh instead."
fi

info "Ensuring Python is installed..."
run pkg install -y python || fail "Could not install Python."
PYTHON_BIN="$(command -v python3 || command -v python || true)"
[ -n "$PYTHON_BIN" ] || fail "No python3 on PATH."

PY_VERSION="$("$PYTHON_BIN" -c 'import sys; print("%d.%d" % sys.version_info[:2])')"
PY_MINOR="${PY_VERSION#3.}"
case "$PY_MINOR" in ''|*[!0-9]*) fail "Could not parse Python version: $PY_VERSION" ;; esac

if [ "$PY_MINOR" -lt 13 ]; then
  warn "Python $PY_VERSION detected. Android wheels require 3.13+."
  fail "Upgrade Termux Python: pkg upgrade python"
fi
ok "Python $PY_VERSION ($PYTHON_BIN)"

# ---- 1. Resolve version (latest android-wheelhouse release on GitHub) --
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
    print(f"ERROR: GitHub API HTTP {e.code}", file=sys.stderr)
    sys.exit(1)
except Exception as e:
    print(f"ERROR: {e}", file=sys.stderr)
    sys.exit(1)

def semver_key(tag):
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
    if any("android_" in a["name"] and "arm64_v8a" in a["name"]
           for a in r.get("assets", []))
]

if not candidates:
    print("ERROR: no release with android_arm64_v8a wheels found.", file=sys.stderr)
    if not wh_all:
        print("       No wheelhouse-v* releases exist.", file=sys.stderr)
    else:
        print(f"       {len(wh_all)} wheelhouse release(s), none with android wheels:", file=sys.stderr)
        for r in wh_all[:10]:
            n = sum(1 for a in r.get("assets", []) if "android" in a["name"])
            print(f"         {r['tag_name']}: {n} android", file=sys.stderr)
    print("       Pass --version X.Y.Z to pin a specific version.", file=sys.stderr)
    sys.exit(1)

best = max(candidates, key=semver_key)
print(best.removeprefix("wheelhouse-v"))
PY
)"
  [ -n "$V" ] || fail "Could not resolve version. Pass --version X.Y.Z."
  ok "Latest Android-wheelhouse version: $V"
fi

TAG="wheelhouse-v${V}"
info "Fetching release: $TAG"

# ---- 2. Download the Android wheels from the release ------------------
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
    if e.code == 404:
        print(f"ERROR: release '{tag}' not found.", file=sys.stderr)
    else:
        print(f"ERROR: HTTP {e.code} for '{tag}'", file=sys.stderr)
    sys.exit(1)
except Exception as e:
    print(f"ERROR: {e}", file=sys.stderr)
    sys.exit(1)

assets = [a for a in release.get("assets", [])
          if a["name"].endswith(".whl")
          and "android_" in a["name"]
          and "arm64_v8a" in a["name"]]

if not assets:
    print(f"ERROR: release '{tag}' has no android wheels.", file=sys.stderr)
    sys.exit(1)

for a in assets:
    print(a["browser_download_url"])
PY
)"
  [ -n "$ASSETS" ] || fail "No Android wheels in release $TAG."

  while IFS= read -r url; do
    [ -n "$url" ] || continue
    info "Downloading $(basename "$url")"
    run curl -fL --retry 3 --retry-delay 2 -o "$WHEELHOUSE_DIR/$(basename "$url")" "$url"
  done <<< "$ASSETS"

  count=$(find "$WHEELHOUSE_DIR" -maxdepth 1 -name '*.whl' | wc -l)
  [ "$count" -gt 0 ] || fail "No wheels downloaded."
  ok "Downloaded $count wheel(s)."
fi

# ---- 3. Create venv --------------------------------------------------
info "Creating venv at $VENV_DIR"
run "$PYTHON_BIN" -m venv "$VENV_DIR"

if [ -d "$VENV_DIR/Scripts" ]; then
  BIN_DIR="$VENV_DIR/Scripts"; VENV_PYTHON="$VENV_DIR/Scripts/python.exe"
else
  BIN_DIR="$VENV_DIR/bin"; VENV_PYTHON="$VENV_DIR/bin/python"
fi

if [ "$PACKAGE_MANAGER" = "ask" ]; then
  if command -v uv >/dev/null 2>&1; then
    pm=$(ask_choice "Which installer for the venv?" 2 "pip (venv's own)" "uv (system)")
    [ "$pm" = "2" ] && PACKAGE_MANAGER="uv" || PACKAGE_MANAGER="pip"
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
# 4a/4b/4c. Reconcile wheel platform tags with this interpreter
# ---------------------------------------------------------------------
#   4a. Compatibility check — read pip's own tag list and classify every
#       wheel in the wheelhouse as already-ok / needs-rename / incompatible.
#       Renames are never inferred from a hardcoded platform string; the
#       target platform comes from what pip actually advertises.
#   4b. Rename — apply the plan from 4a. Wheels marked already-ok are
#       never touched.
#   4c. Verify — re-run the compatibility check. Catches the case where a
#       rename produced a tag pip doesn't accept for that wheel's own
#       (python, abi) pair.
if [ "$DRY_RUN" -eq 0 ] && [ -d "$WHEELHOUSE_DIR" ]; then
  info "Reconciling wheel platform tags with this interpreter (4a/4b/4c)..."

  if WHEELHOUSE_DIR="$WHEELHOUSE_DIR" VENV_PYTHON="$VENV_PYTHON" \
       "$VENV_PYTHON" - <<'PY'
import os, re, subprocess, sys

wheelhouse = os.environ["WHEELHOUSE_DIR"]
venv_python = os.environ["VENV_PYTHON"]


# ---- shared helpers -------------------------------------------------
def pip_compatible_tags():
    out = subprocess.run(
        [venv_python, "-m", "pip", "debug", "--verbose"],
        capture_output=True, text=True, check=True,
    ).stdout
    tags = []
    in_tags = False
    for line in out.splitlines():
        if line.startswith("Compatible tags:"):
            in_tags = True
            continue
        if in_tags:
            s = line.strip()
            if not s:
                if tags:
                    break
                continue
            if re.match(r"^(cp|py|pp)\d", s):
                tags.append(s)
    return tags


def parse_wheel(name):
    """Return (name_version, pytag, abitag, platformtag) or None."""
    if not name.endswith(".whl"):
        return None
    parts = name[:-4].rsplit("-", 3)
    if len(parts) != 4:
        return None
    return tuple(parts)


def find_new_platform(tags, interp_py, pytag, abitag):
    """Pick a platform segment pip accepts for (pytag, abitag), or None.

    Preference:
      1. Exact (pytag, abitag) with any platform pip advertises.
      2. For abi3 wheels only: (interp_py, abi3) — stable-ABI promise.
      3. For abi3 wheels only: (interp_py, interp_py) — a cpXX-abi3
         binary loads under the interpreter's own version-specific ABI.
    """
    for t in tags:
        if t.startswith(f"{pytag}-{abitag}-"):
            return t.split("-", 2)[2]
    if abitag == "abi3":
        for alt in ("abi3", interp_py):
            for t in tags:
                if t.startswith(f"{interp_py}-{alt}-"):
                    return t.split("-", 2)[2]
    return None


# =====================================================================
# 4a. Compatibility check
# =====================================================================
tags = pip_compatible_tags()
tagset = set(tags)
if not tags:
    print("4a: FAIL — pip advertised no compatible tags", file=sys.stderr)
    sys.exit(1)

interp_py = f"cp{sys.version_info.major}{sys.version_info.minor}"
print(f"4a: pip advertises {len(tags)} tags (first: {tags[0]})",
      file=sys.stderr)
print(f"4a: interpreter tag {interp_py}, platform {sys.platform}",
      file=sys.stderr)

already_ok = []    # [name, ...]
plan = []          # [(old_name, new_name), ...]
incompatible = []  # [(name, reason), ...]

for whl in sorted(os.listdir(wheelhouse)):
    parsed = parse_wheel(whl)
    if parsed is None:
        if whl.endswith(".whl"):
            incompatible.append((whl, "unparseable filename"))
        continue
    nv, pytag, abitag, plat = parsed
    if f"{pytag}-{abitag}-{plat}" in tagset:
        already_ok.append(whl)
        continue
    new_plat = find_new_platform(tags, interp_py, pytag, abitag)
    if new_plat is None:
        incompatible.append(
            (whl, f"no pip tag matches {pytag}-{abitag}-*"))
        continue
    if new_plat == plat:
        already_ok.append(whl)
        continue
    plan.append((whl, f"{nv}-{pytag}-{abitag}-{new_plat}.whl"))

print(f"4a: {len(already_ok)} already-compatible, "
      f"{len(plan)} need-rename, {len(incompatible)} incompatible",
      file=sys.stderr)
for w in already_ok:
    print(f"4a:   OK   {w}", file=sys.stderr)
for old, new in plan:
    print(f"4a:   TAG  {old}", file=sys.stderr)
    print(f"4a:     -> {new}", file=sys.stderr)
for w, why in incompatible:
    print(f"4a:   FAIL {w}  ({why})", file=sys.stderr)


# =====================================================================
# 4b. Apply renames
# =====================================================================
renamed = 0
rename_errors = 0
for old, new in plan:
    src = os.path.join(wheelhouse, old)
    dst = os.path.join(wheelhouse, new)
    if not os.path.exists(src):
        print(f"4b: WARN {old} disappeared before rename", file=sys.stderr)
        rename_errors += 1
        continue
    if os.path.exists(dst):
        print(f"4b: WARN {new} already exists, skipping", file=sys.stderr)
        rename_errors += 1
        continue
    os.rename(src, dst)
    renamed += 1

print(f"4b: renamed {renamed}, errors {rename_errors}", file=sys.stderr)


# =====================================================================
# 4c. Verify
# =====================================================================
ok = bad = 0
for whl in sorted(os.listdir(wheelhouse)):
    parsed = parse_wheel(whl)
    if parsed is None:
        continue
    _, pytag, abitag, plat = parsed
    if f"{pytag}-{abitag}-{plat}" in tagset:
        ok += 1
    else:
        print(f"4c: BAD  {whl}  (not in pip's compatible tags)",
              file=sys.stderr)
        bad += 1

print(f"4c: {ok} compatible, {bad} incompatible", file=sys.stderr)


# =====================================================================
# Exit code: 0 = clean, 2 = some wheels still incompatible
# =====================================================================
if bad or rename_errors or incompatible:
    sys.exit(2)
sys.exit(0)
PY
  then
    ok "Wheel platform tags reconciled (4a/4b/4c clean)."
  else
    rc=$?
    if [ "$rc" -eq 2 ]; then
      warn "Some wheels are not compatible with this interpreter."
      warn "pip will report a detailed error at install time."
      warn ""
      warn "If a wheel shows 'no pip tag matches <py>-<abi>-*', the fix is"
      warn "in the wheelhouse, not here: add the interpreter's python tag"
      warn "to the android row in compute_wheel_gaps.py and rebuild the"
      warn "wheelhouse release."
    else
      warn "Wheel reconciliation failed unexpectedly (rc=$rc)."
    fi
  fi
fi

# ---- 5. Pre-install compiled wheels ---------------------------------
if [ "$DRY_RUN" -eq 0 ]; then
  shopt -s nullglob
  wheels=("$WHEELHOUSE_DIR"/*.whl)
  shopt -u nullglob
  [ "${#wheels[@]}" -gt 0 ] || fail "No wheels in $WHEELHOUSE_DIR."
  info "Installing ${#wheels[@]} pre-built wheel(s)..."
  if ! run "${PIP_PREFIX[@]}" --no-deps --force-reinstall "${wheels[@]}"; then
    warn "pip rejected wheels. Diagnostics:"
    warn "  interpreter: $VENV_PYTHON"
    warn "  platform:    $("$VENV_PYTHON" -c 'import sysconfig; print(sysconfig.get_platform())')"
    warn "  py tag:      $("$VENV_PYTHON" -c 'import sys; print(f"cp{sys.version_info.major}{sys.version_info.minor}")')"
    fail "Wheel install failed."
  fi
fi

# ---- 6. lxml build ladder --------------------------------------------
info "Installing lxml (5–20 min on a phone)..."
run pkg install -y clang libxml2 libxslt libiconv make python-dev pkg-config || \
  warn "Some build deps failed."

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

# ---- 7. Install open-news-api ----------------------------------------
if [ "$JS_MODE" = "ask" ]; then
  js=$(ask_choice "Install JS extra (Playwright + Chromium, ~300MB)?" 2 "Yes" "No")
  [ "$js" = "1" ] && JS_MODE="yes" || JS_MODE="no"
fi
SPEC="${PKG}==${V}"
[ "$JS_MODE" = "yes" ] && SPEC="${PKG}[js]==${V}"
info "Installing $SPEC"
run "${PIP_PREFIX[@]}" "$SPEC"

if [ "$JS_MODE" = "yes" ]; then
  info "Installing Chromium..."
  if [ -x "${BIN_DIR}/playwright" ]; then
    run "${BIN_DIR}/playwright" install chromium
  else
    run "$VENV_PYTHON" -m playwright install chromium
  fi
fi

# ---- 8. PATH ---------------------------------------------------------
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
    warn "Added $BIN_DIR to PATH in $SHELL_RC"
  fi
fi

# ---- 9. Preferences --------------------------------------------------
info "First-run preferences..."
PREF_LANGUAGE=$(ask_text "Default language (ISO 639-1, blank = none)" "")
PREF_CATEGORY=$(ask_text "Default fetch category" "general")
PREF_SORT=$(ask_text "Default sort (date/relevance/popularity)" "date")
PREF_FORMAT=$(ask_text "Default CLI output format (pretty/json)" "pretty")

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

# ---- 10. Verify ------------------------------------------------------
[ "$DRY_RUN" -eq 1 ] && { ok "Dry run complete."; exit 0; }

info "Verifying install..."
if [ -x "$OPEN_NEWS_BIN" ]; then
  "$OPEN_NEWS_BIN" --version
  ok "Install verified."
  if command -v open-news >/dev/null 2>&1; then
    echo "Run: open-news --help"
  else
    echo "Run: $OPEN_NEWS_BIN --help   (or restart your shell)"
  fi
else
  warn "No binary at $OPEN_NEWS_BIN — trying module invocation."
  "$VENV_PYTHON" -m open_news.cli --version || \
    fail "Verification failed. Try: $VENV_PYTHON -m open_news.cli --version"
fi

if [ "$ASSUME_YES" -eq 0 ]; then
  read -r -p $'\nLaunch the TUI now? [y/N]: ' launch || true
  if [ "${launch:-N}" = "y" ] || [ "${launch:-N}" = "Y" ]; then
    if [ -x "${BIN_DIR}/open-news-tui" ]; then
      exec "${BIN_DIR}/open-news-tui"
    else
      exec "$VENV_PYTHON" -m open_news.tui
    fi
  fi
fi