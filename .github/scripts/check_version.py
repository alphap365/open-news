"""Fail if the packaged version and pyproject.toml disagree.

CI runs this so a release bump cannot update one place and silently miss the
other: ``open_news.__version__`` is what users see, ``pyproject.toml`` is what
gets published to PyPI.
"""

import pathlib
import sys

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10
    import tomli as tomllib

import open_news


def main() -> int:
    pyproject = pathlib.Path(__file__).resolve().parents[2] / "pyproject.toml"
    with open(pyproject, "rb") as handle:
        declared = tomllib.load(handle)["project"]["version"]

    if declared != open_news.__version__:
        print(
            f"version mismatch: pyproject.toml={declared!r}, "
            f"open_news.__version__={open_news.__version__!r}",
            file=sys.stderr,
        )
        return 1

    print(f"version agreement OK: {declared}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
