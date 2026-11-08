"""Recipe acquisition, normalization, and preflight.

Given (package, version, target), this module returns a ranked list of
candidates — prebuilt wheels, fetched recipes, static-analysis fallbacks —
and validates each candidate with cheap preflight probes before the planner
commits a build slot to it.
"""

from __future__ import annotations

import ast
import hashlib
import html as html_module
import json
import os
import re
import shlex
import subprocess
import sys
import tarfile
import tempfile
import time
import zipfile
from dataclasses import asdict, dataclass, field
from pathlib import Path
from urllib.parse import quote, urljoin

import httpx
from packaging.utils import canonicalize_name, parse_wheel_filename
from packaging.version import Version

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib

try:
    import yaml
except ImportError:
    yaml = None


# ─── Constants ───────────────────────────────────────────────────────────

CHAQUOPY_META_URLS = [
    "https://raw.githubusercontent.com/chaquo/chaquopy/master/packages/{name}/meta.yaml",
]
CHAQUOPY_PATCH_URL = (
    "https://raw.githubusercontent.com/chaquo/chaquopy/master/"
    "packages/{name}/patches/{patch}"
)
CHAQUOPY_MAVEN_BASE = "https://repo1.maven.org/maven2/com/chaquo/python"

FLET_META_URL = (
    "https://raw.githubusercontent.com/flet-dev/mobile-forge/main/"
    "recipes/{name}/meta.yaml"
)

TERMUX_BUILD_URL = (
    "https://raw.githubusercontent.com/termux/termux-packages/master/"
    "packages/{name}/build.sh"
)

EXTERNAL_INDEXES = [
    {
        "name": "flet",
        "type": "simple_html",
        "url_template": "https://pypi.flet.dev/{package}/",
        "supports": {"families": {"android", "ios"}},
    },
    {
        "name": "chaquopy",
        "type": "simple_html",
        "url_template": "https://chaquo.com/pypi-13.1/{package}/",
        "supports": {"families": {"android"}},
    },
    {
        "name": "termux",
        "type": "simple_html",
        "url_template": "https://termux-user-repository.github.io/pypi/{package}/",
        "supports": {"families": {"android"}},
    },
    {
        "name": "anaconda_pyswift",
        "type": "anaconda_api",
        "url_template": "https://api.anaconda.org/package/PySwift/{package}",
        "supports": {"families": {"android"}},
    },
    {
        "name": "exotic_wheels",
        "type": "simple_html",
        "url_template": "https://exotic-wheels.github.io/simple/{package}/",
        "supports": {
            "families": {"musllinux"},
            "archs": {"armv7l", "aarch64", "ppc64le", "s390x", "riscv64"},
        },
    },
    {
        "name": "piwheels",
        "type": "simple_html",
        "url_template": "https://www.piwheels.org/simple/{package}/",
        "supports": {"families": {"manylinux"}, "archs": {"armv7l", "armv6l"}},
    },
    {
        "name": "pytorch_cpu",
        "type": "simple_html",
        "url_template": "https://download.pytorch.org/whl/cpu/{package}/",
        "supports": {"families": {"manylinux", "musllinux", "windows", "macos"}},
    },
    {
        "name": "nvidia",
        "type": "simple_html",
        "url_template": "https://pypi.nvidia.com/{package}/",
        "supports": {"families": {"manylinux"}},
    },
]

_SYSTEM_LIB_HINTS = {
    "libxml2": "libxml2-dev",
    "libxslt": "libxslt1-dev",
    "openssl": "libssl-dev",
    "libffi": "libffi-dev",
    "libjpeg": "libjpeg-dev",
    "libpng": "libpng-dev",
    "zlib": "zlib1g-dev",
    "libyaml": "libyaml-dev",
    "freetype": "libfreetype6-dev",
    "libavformat": "libavformat-dev",
    "portaudio": "portaudio19-dev",
}

_NATIVE_BACKENDS = (
    "maturin",
    "scikit_build",
    "scikit-build",
    "mesonpy",
    "meson-python",
    "setuptools_rust",
    "setuptools-rust",
)

_DEB_TO_RPM = {
    "libxml2-dev": "libxml2-devel",
    "libxslt1-dev": "libxslt-devel",
    "libssl-dev": "openssl-devel",
    "libffi-dev": "libffi-devel",
    "zlib1g-dev": "zlib-devel",
    "libjpeg-dev": "libjpeg-turbo-devel",
    "libpng-dev": "libpng-devel",
    "libyaml-dev": "libyaml-devel",
    "libfreetype6-dev": "freetype-devel",
    "gfortran": "gcc-gfortran",
    "libopenblas-dev": "openblas-devel",
    "liblapack-dev": "lapack-devel",
}
_DEB_TO_ALPINE = {
    "libxml2-dev": "libxml2-dev",
    "libxslt1-dev": "libxslt-dev",
    "libssl-dev": "openssl-dev",
    "libffi-dev": "libffi-dev",
    "zlib1g-dev": "zlib-dev",
    "libjpeg-dev": "libjpeg-turbo-dev",
    "libpng-dev": "libpng-dev",
    "libyaml-dev": "yaml-dev",
    "libfreetype6-dev": "freetype-dev",
    "gfortran": "gfortran",
    "libopenblas-dev": "openblas-dev",
    "liblapack-dev": "lapack-dev",
}


# ─── Normalized recipe ───────────────────────────────────────────────────


@dataclass
class BuildRecipe:
    """Normalized build recipe, target-shaped, consumed by build.yml."""

    package: str
    version: str
    target: str
    source: str  # "chaquopy" | "flet" | "termux" | "local" | "static"
    source_ref: str
    confidence: str = "medium"  # "high" | "medium" | "low"
    build_type: str = "cibuildwheel"  # "pure_python" | "cibuildwheel"

    # Injected as CIBW_* env
    env: dict = field(default_factory=dict)
    before_all: str | None = None
    before_all_linux: str | None = None
    repair_command: str | None = None

    # Downloaded before build
    host_artifacts: list = field(default_factory=list)
    patches: list = field(default_factory=list)

    # manylinux / musllinux only; Debian names translated at plan time
    system_deps: list = field(default_factory=list)

    version_anchor: str | None = None  # version the recipe was written for
    reason: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


# ─── Utilities ───────────────────────────────────────────────────────────


def log(msg: str) -> None:
    print(f"[recipes] {msg}", flush=True)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def index_supports(index: dict, target: dict) -> bool:
    s = index.get("supports", {})
    if s.get("families") and target["family"] not in s["families"]:
        return False
    if s.get("archs") and target["architecture"] not in s["archs"]:
        return False
    return True


def version_delta(shipped: Version, requested: Version) -> str:
    if shipped == requested:
        return "exact"
    if shipped.major != requested.major:
        return "major"
    if shipped.minor != requested.minor:
        return "minor"
    return "patch"


def version_risk(delta: str) -> str:
    return {"exact": "none", "patch": "low", "minor": "medium", "major": "high"}.get(
        delta, "high"
    )


def version_anchor_ok(
    anchor: str | None, requested: str, max_delta: str = "minor"
) -> bool:
    """True if a recipe anchored at `anchor` is plausible for `requested`."""
    if not anchor:
        return True  # unanchored recipes are always considered
    try:
        delta = version_delta(Version(anchor), Version(requested))
    except Exception:
        return False
    order = {"exact": 0, "patch": 1, "minor": 2, "major": 3}
    return order[delta] <= order[max_delta]


def _parse_requirement(spec: str) -> tuple[str, str | None]:
    spec = (spec or "").strip()
    if not spec:
        return "", None
    for sep in ("==", "=", " "):
        if sep in spec:
            name, _, version = spec.partition(sep)
            return name.strip(), version.strip() or None
    return spec, None


# ─── Wheel index lookup ──────────────────────────────────────────────────

_SIMPLE_ANCHOR_RE = re.compile(
    r'<a\s+[^>]*href="([^"]+)"[^>]*>([^<]+)</a>', re.IGNORECASE
)


def query_simple_index(client: httpx.Client, url: str) -> list[dict]:
    try:
        r = client.get(url, follow_redirects=True)
        if r.status_code == 404:
            return []
        r.raise_for_status()
    except httpx.HTTPError:
        return []
    out = []
    for href, text in _SIMPLE_ANCHOR_RE.findall(r.text):
        fname = html_module.unescape(text.strip())
        if not fname.endswith(".whl"):
            continue
        abs_url = urljoin(url, href)
        sha = None
        if "#" in abs_url:
            abs_url, frag = abs_url.split("#", 1)
            if frag.startswith("sha256="):
                sha = frag[len("sha256=") :]
        out.append({"filename": fname, "url": abs_url, "sha256": sha})
    return out


def query_anaconda_api(client: httpx.Client, url: str) -> list[dict]:
    try:
        r = client.get(url, follow_redirects=True)
        if r.status_code == 404:
            return []
        r.raise_for_status()
        data = r.json()
    except (httpx.HTTPError, json.JSONDecodeError):
        return []
    out = []
    for fi in data.get("files", []):
        base = fi.get("basename", "")
        if not base.endswith(".whl"):
            continue
        attrs = fi.get("attrs") or {}
        if not str(attrs.get("subdir", "")).startswith("android_"):
            continue
        out.append(
            {
                "filename": base,
                "url": fi.get("download_url"),
                "sha256": attrs.get("sha256"),
            }
        )
    return out


def find_external_wheel(
    client: httpx.Client,
    package: str,
    version: str,
    target: dict,
    supported_tags: list,
    allow_deltas: tuple = ("patch", "minor"),
) -> dict | None:
    """Return the best external wheel for (package, version, target).

    Accepts the exact version first, then patch/minor drift if `allow_deltas`
    permits. Major drift is never returned.
    """
    requested = Version(version)
    supported = set(supported_tags)
    accepted_deltas = {"exact", *allow_deltas}
    best: dict | None = None
    best_rank: tuple | None = None

    for index in EXTERNAL_INDEXES:
        if not index_supports(index, target):
            continue
        url = index["url_template"].format(package=quote(package, safe=""))
        if index["type"] == "simple_html":
            cands = query_simple_index(client, url)
        elif index["type"] == "anaconda_api":
            cands = query_anaconda_api(client, url)
        else:
            continue
        for cand in cands:
            try:
                wname, wver, _, wtags = parse_wheel_filename(cand["filename"])
            except Exception:
                continue
            if canonicalize_name(str(wname)) != canonicalize_name(package):
                continue
            if not wtags.intersection(supported):
                continue
            delta = version_delta(wver, requested)
            if delta not in accepted_deltas:
                continue
            rank = ({"exact": 0, "patch": 1, "minor": 2}[delta], -wver.micro)
            if best_rank is None or rank < best_rank:
                best = {
                    "index": index["name"],
                    **cand,
                    "requested_version": version,
                    "shipped_version": str(wver),
                    "version_delta": delta,
                    "runtime_risk": version_risk(delta),
                }
                best_rank = rank
    return best


def download_wheel(
    client: httpx.Client,
    url: str,
    dest_dir: Path,
    expected_sha256: str | None,
) -> tuple[Path, str]:
    filename = url.rsplit("/", 1)[-1].split("?")[0].split("#")[0]
    if not filename.endswith(".whl") or "/" in filename or filename.startswith("."):
        raise ValueError(f"Unsafe wheel filename: {filename!r}")
    r = client.get(url, follow_redirects=True)
    r.raise_for_status()
    body = r.content
    digest = sha256_bytes(body)
    if expected_sha256 and digest.lower() != expected_sha256.lower():
        raise ValueError(f"SHA-256 mismatch for {filename}")
    dest = dest_dir / filename
    dest.write_bytes(body)
    return dest, digest


# ─── Source fetchers ─────────────────────────────────────────────────────


def _fetch_yaml(client: httpx.Client, url: str, retries: int = 2) -> dict | None:
    if yaml is None:
        return None
    for attempt in range(retries + 1):
        try:
            r = client.get(url, follow_redirects=True, timeout=20)
            if r.status_code == 404:
                return None
            r.raise_for_status()
            return yaml.safe_load(r.text) or {}
        except (httpx.HTTPError, yaml.YAMLError):
            if attempt >= retries:
                return None
            time.sleep(2**attempt)
    return None


def fetch_chaquopy_meta(
    client: httpx.Client,
    package: str,
    version: str,
    retries: int = 2,
) -> dict | None:
    pkg = package.lower()
    # Chaquopy uses versioned folder names: cryptography-3.4, lxml-4.9.3, etc.
    candidates = [
        f"{pkg}-{version}",
        pkg,
        f"{pkg.replace('-', '_')}-{version}",
        pkg.replace("-", "_"),
    ]
    for name in candidates:
        for template in CHAQUOPY_META_URLS:
            url = template.format(name=name)
            meta = _fetch_yaml(client, url, retries=retries)
            if meta is not None:
                return {"recipe_name": name, "meta": meta, "url": url}
    return None


def fetch_flet_meta(
    client: httpx.Client,
    package: str,
    version: str,
    retries: int = 2,
) -> dict | None:
    pkg = package.lower()
    for name in [pkg, pkg.replace("-", "_")]:
        url = FLET_META_URL.format(name=name)
        meta = _fetch_yaml(client, url, retries=retries)
        if meta is not None:
            return {"recipe_name": name, "meta": meta, "url": url}
    return None


def fetch_termux_build_sh(
    client: httpx.Client,
    package: str,
    retries: int = 2,
) -> dict | None:
    # Termux package names are prefixed: python-cryptography, python-lxml, ...
    for name in [f"python-{package.lower()}", package.lower()]:
        url = TERMUX_BUILD_URL.format(name=name)
        for attempt in range(retries + 1):
            try:
                r = client.get(url, follow_redirects=True, timeout=20)
                if r.status_code == 404:
                    break
                r.raise_for_status()
                return {"recipe_name": name, "script": r.text, "url": url}
            except httpx.HTTPError:
                if attempt >= retries:
                    break
                time.sleep(2**attempt)
    return None


def load_local_recipe(package: str, version: str, target: dict) -> dict | None:
    """Load .github/recipes/<pkg>/meta.yaml if it exists."""
    if yaml is None:
        return None
    path = Path(".github/recipes") / canonicalize_name(package) / "meta.yaml"
    if not path.is_file():
        return None
    try:
        meta = yaml.safe_load(path.read_text())
    except yaml.YAMLError:
        return None
    return {"recipe_name": package, "meta": meta or {}, "path": str(path)}


# ─── Adapters ────────────────────────────────────────────────────────────


def _chaquopy_artifact_url(name: str, version: str | None) -> str | None:
    if not name.startswith("chaquopy-") or not version:
        return None
    tail = name[len("chaquopy-") :]
    return f"{CHAQUOPY_MAVEN_BASE}/chaquopy-{tail}/{version}/chaquopy-{tail}-{version}.tar.gz"


def from_conda_yaml(
    payload: dict,
    source: str,
    package: str,
    version: str,
    target: dict,
) -> BuildRecipe:
    """Chaquopy / Flet / local recipes all use the Conda-subset schema."""
    meta = payload.get("meta") or {}
    reqs = meta.get("requirements") or {}
    build_block = meta.get("build") or {}

    host_artifacts = []
    for spec in reqs.get("host") or []:
        name, ver = _parse_requirement(spec)
        if not name:
            continue
        url = (
            _chaquopy_artifact_url(name, ver)
            if source in ("chaquopy", "local")
            else None
        )
        host_artifacts.append(
            {
                "name": name,
                "version": ver,
                "url": url,
                "required": source == "chaquopy" and url is not None,
            }
        )

    env: dict[str, str] = {}
    for entry in build_block.get("script_env") or []:
        if "=" in entry:
            k, _, v = entry.partition("=")
            env[k.strip()] = v.strip()
    # Local recipes can override env explicitly
    for k, v in (meta.get("cibw_environment") or {}).items():
        env[k] = str(v)

    patches = []
    recipe_name = payload.get("recipe_name")
    if source == "chaquopy" and recipe_name:
        for p in ("chaquopy.patch", "android.patch", "fix.patch", "build.patch"):
            patches.append(
                {
                    "url": CHAQUOPY_PATCH_URL.format(name=recipe_name, patch=p),
                    "filename": p,
                }
            )
    elif source == "local":
        local_patches = meta.get("patches") or []
        for p in local_patches:
            if isinstance(p, dict):
                patches.append(p)

    anchor = ((meta.get("package") or {}).get("version") or "").strip() or None
    confidence = "high" if source == "local" else "medium"
    if anchor and version_delta(Version(anchor), Version(version)) == "major":
        confidence = "low"

    return BuildRecipe(
        package=package,
        version=version,
        target=target["target"],
        source=source,
        source_ref=payload.get("url") or payload.get("path") or "",
        confidence=confidence,
        build_type="cibuildwheel",
        env=env,
        host_artifacts=host_artifacts,
        patches=patches,
        before_all=build_block.get("script"),
        before_all_linux=meta.get("cibw_before_all_linux"),
        repair_command=meta.get("repair_command"),
        version_anchor=anchor,
        reason=f"{source} recipe ({anchor or 'unanchored'})",
    )


def _cibw_python_glob(pattern: str) -> str:
    return f"$(python -c 'import glob,sys; print(glob.glob(sys.argv[1])[0])' {pattern})"


def _android_cffi_env() -> dict[str, str]:
    discover_include = _cibw_python_glob(
        "/tmp/cibw-run-*/cp*-android_*/python/prefix/include/python*"
    )
    return {
        "CFLAGS_aarch64_linux_android": (
            f"-D__BIONIC_NO_PAGE_SIZE_MACRO -I{discover_include}"
        ),
    }


_TERMUX_EXPORT_RE = re.compile(r"^\s*export\s+([A-Z_][A-Z0-9_]*)=(.*)$", re.MULTILINE)


def from_termux_shell(
    payload: dict,
    package: str,
    version: str,
    target: dict,
) -> BuildRecipe:
    """Translate Termux build.sh into an Android recipe.

    Termux sets CFLAGS_<triple> to the *versioned* Python include path
    (.../include/python3.13), because cc-rs only receives the parent
    (.../include) from cibuildwheel. That versioned subdirectory is the
    one that actually contains Python.h. Its exact location is only
    known at build time, so discover it through CIBW_ENVIRONMENT.
    """
    script = payload.get("script") or ""

    # Discover the versioned include/lib dirs at build time. Both are
    # unique per cibuildwheel run (random hash in the path).
    # cibuildwheel rebuilds generic CFLAGS when it creates its Android
    # environment, so changes to CFLAGS do not reach the cross-compiler.
    # cc-rs checks the target-specific variable, which survives that setup.
    env: dict[str, str] = {
        "CARGO_BUILD_TARGET": "aarch64-linux-android",
        "ANDROID_API_LEVEL": "24",
        **_android_cffi_env(),
    }
    # PyO3 needs the directory containing libpython for the target.
    env["PYO3_CROSS_LIB_DIR"] = _cibw_python_glob(
        "/tmp/cibw-run-*/cp*-android_*/python/prefix/lib"
    )

    # Extract Python version from Termux's script when available, so
    # the patchelf step below matches whatever Termux currently targets.
    py_ver = "3.13"
    m = re.search(r'TERMUX_PYTHON_VERSION=["\']?([0-9.]+)', script)
    if m:
        py_ver = m.group(1)

    anchor = None
    m = re.search(r'TERMUX_PKG_VERSION=["\']?([0-9][^\s"\']*)', script)
    if m:
        anchor = m.group(1)

    # patchelf the built .so — maturin only links libpython for binary
    # targets, not cdylib, and the Android linker requires it.
    repair = f'patchelf --add-needed libpython{py_ver}.so "$SO"'

    confidence = (
        "high"
        if anchor
        and version_delta(Version(anchor), Version(version)) in ("exact", "patch")
        else "medium"
    )

    return BuildRecipe(
        package=package,
        version=version,
        target=target["target"],
        source="termux",
        source_ref=payload.get("url", ""),
        confidence=confidence,
        build_type="cibuildwheel",
        env=env,
        repair_command=repair,
        version_anchor=anchor,
        reason=f"termux recipe ({anchor or 'unanchored'})",
    )


# ─── Static analysis (fallback recipe source) ────────────────────────────


def _extract_archive(archive: Path, dest: Path) -> Path:
    dest.mkdir(parents=True, exist_ok=True)
    if tarfile.is_tarfile(archive):
        with tarfile.open(archive) as tf:
            for m in tf.getmembers():
                if m.name.startswith("/") or ".." in m.name.split("/"):
                    raise ValueError(f"Unsafe tar member: {m.name}")
            tf.extractall(dest, filter="data")
    elif zipfile.is_zipfile(archive):
        with zipfile.ZipFile(archive) as zf:
            for item in zf.infolist():
                if item.filename.startswith("/") or ".." in item.filename.split("/"):
                    raise ValueError(f"Unsafe zip member: {item.filename}")
            zf.extractall(dest)
    else:
        raise ValueError("Unsupported source archive format")
    entries = list(dest.iterdir())
    return entries[0] if len(entries) == 1 and entries[0].is_dir() else dest


def _detect_extension_via_ast(setup_py: Path) -> bool:
    try:
        tree = ast.parse(setup_py.read_text(errors="replace"))
    except (SyntaxError, OSError):
        return False
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            fn = node.func
            name = (
                fn.id
                if isinstance(fn, ast.Name)
                else (fn.attr if isinstance(fn, ast.Attribute) else "")
            )
            if name in ("Extension", "RustExtension"):
                return True
    return False


def _has_shell_execution(source: Path) -> bool:
    for name in ("setup.py", "setupinfo.py"):
        p = source / name
        if not p.is_file():
            continue
        try:
            text = p.read_text(errors="replace")
        except OSError:
            continue
        if re.search(r"Popen\(.*shell\s*=\s*True|os\.system|subprocess\.run", text):
            return True
    return False


def _is_maturin_with_cffi(source: Path) -> bool:
    pyproject = source / "pyproject.toml"
    if not pyproject.is_file():
        return False
    try:
        with pyproject.open("rb") as f:
            pp = tomllib.load(f)
    except Exception:
        return False
    backend = (pp.get("build-system", {}).get("build-backend") or "").lower()
    if "maturin" not in backend:
        return False
    for cargo in source.rglob("Cargo.toml"):
        try:
            with cargo.open("rb") as f:
                ct = tomllib.load(f)
            deps = ct.get("dependencies") or {}
            if "cffi" in deps or any("cffi" in str(k).lower() for k in deps):
                return True
        except Exception:
            continue
    return False


def _analyze_source_tree(source: Path, target: dict) -> dict:
    info = {
        "backend": None,
        "requires": [],
        "native": False,
        "system_deps": [],
        "reason": "",
        "build_type": "pure_python",
        "confidence": "high",
        "env": {},
    }

    pyproject = source / "pyproject.toml"
    if pyproject.is_file():
        try:
            with pyproject.open("rb") as f:
                pp = tomllib.load(f)
            bs = pp.get("build-system", {})
            info["requires"] = list(bs.get("requires", []))
            info["backend"] = bs.get("build-backend")
        except Exception:
            pass

    backend_lc = (info["backend"] or "").lower()
    if any(b in backend_lc for b in _NATIVE_BACKENDS):
        info["native"] = True
        info["reason"] = f"native backend: {info['backend']}"

    if not info["native"] and info["requires"]:
        reqs = " ".join(info["requires"]).lower()
        if "cython" in reqs:
            info["native"] = True
            info["reason"] = "cython in build-system.requires"

    if not info["native"]:
        setup_py = source / "setup.py"
        if setup_py.is_file():
            if _detect_extension_via_ast(setup_py):
                info["native"] = True
                info["reason"] = "Extension() in setup.py"
            else:
                try:
                    if re.search(
                        r"ext_modules\s*=\s*\[", setup_py.read_text(errors="replace")
                    ):
                        info["native"] = True
                        info["reason"] = "ext_modules in setup.py"
                except OSError:
                    pass

    info["build_type"] = "cibuildwheel" if info["native"] else "pure_python"
    info["confidence"] = "medium" if info["native"] else "high"

    if info["native"] and target["family"] == "android":
        # Android-specific failure classes
        if _has_shell_execution(source):
            info["confidence"] = "low"
            info["reason"] = (
                "build-time shell exec (Android cross-compile needs SHELL=/bin/bash)"
            )
        elif _is_maturin_with_cffi(source):
            info["confidence"] = "low"
            info["reason"] = (
                "maturin + cffi C-ext (Python.h propagation gap on Android)"
            )
            info["env"].update(_android_cffi_env())

    if target["family"] in ("manylinux", "musllinux") and info["native"]:
        text_blob = ""
        for f in list(source.rglob("*.py"))[:80]:
            try:
                text_blob += f.read_text(errors="replace").lower()
            except OSError:
                continue
        for lib, pkg in _SYSTEM_LIB_HINTS.items():
            if lib in text_blob:
                info["system_deps"].append(pkg)
        info["system_deps"] = sorted(set(info["system_deps"]))

    return info


def probe_pure_build(source: Path, timeout: int = 180) -> tuple[bool, str]:
    with tempfile.TemporaryDirectory() as wh:
        env = dict(os.environ)
        env["PIP_DISABLE_PIP_VERSION_CHECK"] = "1"
        try:
            r = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "pip",
                    "wheel",
                    "--no-deps",
                    "--quiet",
                    "--wheel-dir",
                    wh,
                    str(source),
                ],
                capture_output=True,
                text=True,
                timeout=timeout,
                env=env,
            )
        except subprocess.TimeoutExpired:
            return False, "probe timed out"
        if r.returncode != 0:
            return False, (r.stderr or "")[-500:]
        return True, ""


def analyze_sdist_url(
    client: httpx.Client,
    url: str,
    expected_sha256: str | None,
    target: dict,
    do_probe: bool,
) -> tuple[BuildRecipe, Path | None]:
    """Download the sdist, classify it, and (optionally) probe pure builds.

    Returns (recipe, extracted_source_or_None). The extracted path is used
    by the caller for preflight; it lives in a tempdir whose lifetime the
    caller controls via TemporaryDirectory.
    """
    tmp = Path(tempfile.mkdtemp(prefix="recipe-sdist-"))
    try:
        archive = tmp / "sdist"
        r = client.get(url, follow_redirects=True, timeout=180)
        r.raise_for_status()
        archive.write_bytes(r.content)
        if expected_sha256:
            actual = sha256_bytes(archive.read_bytes())
            if actual.lower() != expected_sha256.lower():
                raise ValueError("sdist SHA-256 mismatch")
        source = _extract_archive(archive, tmp / "src")
        info = _analyze_source_tree(source, target)

        if do_probe and info["build_type"] == "pure_python":
            ok, msg = probe_pure_build(source)
            if not ok:
                info["confidence"] = "low"
                info["reason"] = f"pure probe failed: {msg[:200]}"

        recipe = BuildRecipe(
            package=info.get("package", ""),
            version=info.get("version", ""),
            target=target["target"],
            source="static",
            source_ref=url,
            confidence=info["confidence"],
            build_type=info["build_type"],
            env=info["env"] or {},
            system_deps=info["system_deps"],
            reason=info["reason"]
            or (
                "pure-python sdist"
                if info["build_type"] == "pure_python"
                else "native sdist"
            ),
        )
        return recipe, source
    except Exception as exc:
        return BuildRecipe(
            package="",
            version="",
            target=target["target"],
            source="static",
            source_ref=url,
            confidence="low",
            build_type="cibuildwheel",
            reason=f"analysis failed: {exc}",
        ), None


# ─── Preflight probes ────────────────────────────────────────────────────


def probe_metadata_resolution(
    source: Path, env: dict, timeout: int = 120
) -> tuple[bool, str]:
    """Run the build backend's get_requires_for_build_wheel without compiling."""
    merged_env = {**os.environ, **env}
    try:
        r = subprocess.run(
            [
                sys.executable,
                "-m",
                "build",
                "--sdist",
                "--no-isolation",
                "--skip-dependency-check",
            ],
            cwd=source,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=merged_env,
        )
    except subprocess.TimeoutExpired:
        return False, "metadata resolution timed out"
    if r.returncode != 0:
        tail = (r.stderr or "")[-300:]
        if "/system/bin/sh" in tail or "system/bin/sh" in tail:
            return (
                False,
                "metadata requires shell exec (/system/bin/sh missing on host)",
            )
        return False, f"metadata resolution failed: {tail}"
    return True, ""


def probe_include_paths(env: dict) -> tuple[bool, str]:
    """Verify every -I path referenced by CFLAGS_* exists on this runner."""
    for key, val in env.items():
        if not key.startswith(("CFLAGS_", "CPPFLAGS_")):
            continue
        for token in shlex.split(val):
            if token.startswith("-I"):
                path = token[2:]
                if not os.path.isdir(path):
                    return False, f"{key} references missing include dir: {path}"
    return True, ""


def probe_rust_target(env: dict) -> tuple[bool, str]:
    target = env.get("CARGO_BUILD_TARGET")
    if not target:
        return True, ""
    try:
        r = subprocess.run(
            ["rustup", "target", "list", "--installed"],
            capture_output=True,
            text=True,
            timeout=15,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return True, ""  # rustup not available; skip this probe
    if target not in (r.stdout or ""):
        return False, f"Rust target {target} not installed"
    return True, ""


def preflight(recipe: BuildRecipe, source: Path | None) -> tuple[bool, str]:
    if recipe.build_type == "pure_python":
        return True, ""
    ok, reason = probe_include_paths(recipe.env)
    if not ok:
        return False, reason
    ok, reason = probe_rust_target(recipe.env)
    if not ok:
        return False, reason
    if source is not None and recipe.env:
        ok, reason = probe_metadata_resolution(source, recipe.env)
        if not ok:
            return False, reason
    return True, ""


# ─── Resolver ladder ─────────────────────────────────────────────────────


def resolve_recipe(
    client: httpx.Client,
    package: str,
    version: str,
    target: dict,
    sdist_url: str,
    sdist_sha256: str | None,
    do_probe: bool = True,
) -> tuple[BuildRecipe, str, list[dict]]:
    """Walk the recipe ladder and return (winning_recipe, kind, rejects)."""
    candidates: list[tuple[str, dict]] = []

    # 1. Local recipe (highest trust)
    local = load_local_recipe(package, version, target)
    if local:
        recipe = from_conda_yaml(local, "local", package, version, target)
        if version_anchor_ok(recipe.version_anchor, version, max_delta="minor"):
            candidates.append(("recipe_local", local))

    # 2. Termux (Android only — first choice for cross-compiled C-extensions)
    if target["family"] == "android":
        termux = fetch_termux_build_sh(client, package)
        if termux:
            recipe = from_termux_shell(termux, package, version, target)
            if version_anchor_ok(recipe.version_anchor, version, max_delta="minor"):
                candidates.append(("recipe_termux", termux))

    # 3. Chaquopy (Android only)
    if target["family"] == "android":
        chaq = fetch_chaquopy_meta(client, package, version)
        if chaq:
            anchor = (
                (chaq["meta"].get("package") or {}).get("version") or ""
            ).strip() or None
            if version_anchor_ok(anchor, version, max_delta="minor"):
                candidates.append(("recipe_chaquopy", chaq))

    # 4. Flet mobile-forge (Android + iOS)
    if target["family"] in ("android", "ios"):
        flet = fetch_flet_meta(client, package, version)
        if flet:
            anchor = (
                (flet["meta"].get("package") or {}).get("version") or ""
            ).strip() or None
            if version_anchor_ok(anchor, version, max_delta="minor"):
                candidates.append(("recipe_flet", flet))

    # 5. Static analysis (always last)
    candidates.append(("static_analysis", None))

    rejects: list[dict] = []
    for kind, payload in candidates:
        if kind == "recipe_local":
            recipe = from_conda_yaml(payload, "local", package, version, target)
            source_path = None
        elif kind == "recipe_chaquopy":
            recipe = from_conda_yaml(payload, "chaquopy", package, version, target)
            source_path = None
        elif kind == "recipe_flet":
            recipe = from_conda_yaml(payload, "flet", package, version, target)
            source_path = None
        elif kind == "recipe_termux":
            recipe = from_termux_shell(payload, package, version, target)
            source_path = None
        else:
            recipe, source_path = analyze_sdist_url(
                client,
                sdist_url,
                sdist_sha256,
                target,
                do_probe,
            )
            recipe.package = package
            recipe.version = version

        ok, reason = preflight(recipe, source_path)
        if ok:
            return recipe, kind, rejects

        rejects.append({"kind": kind, "reason": reason})
        log(f"preflight reject: {package} {kind}: {reason}")

        # Clean up static-analysis tempdir if not selected
        if source_path is not None:
            import shutil as _shutil

            _shutil.rmtree(source_path.parent, ignore_errors=True)

    # Nothing passed preflight — return the static recipe as expected_risk
    static_recipe, _ = analyze_sdist_url(
        client,
        sdist_url,
        sdist_sha256,
        target,
        do_probe=False,
    )
    static_recipe.package = package
    static_recipe.version = version
    static_recipe.confidence = "low"
    static_recipe.reason = "all candidates failed preflight: " + "; ".join(
        r["reason"] for r in rejects
    )
    return static_recipe, "expected_risk", rejects
