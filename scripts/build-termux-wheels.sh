#!/usr/bin/env bash
# Build and verify native dependency wheels inside Termux.

set -euo pipefail

WHEEL_DIR="${1:-wheelhouse}"
mkdir -p "$WHEEL_DIR"

packages=(lxml selectolax primp greenlet)
echo "Building ${packages[*]} from source into $WHEEL_DIR"
python -m pip wheel \
  --no-binary=lxml,selectolax,primp,greenlet \
  --no-cache-dir \
  --wheel-dir "$WHEEL_DIR" \
  "${packages[@]}"

shopt -s nullglob
for package in "${packages[@]}"; do
  wheels=("$WHEEL_DIR"/"$package"-*.whl)
  if [ "${#wheels[@]}" -eq 0 ]; then
    echo "ERROR: no $package wheel was created in $WHEEL_DIR" >&2
    exit 1
  fi
  printf 'Created wheel: %s\n' "${wheels[@]}"
done
