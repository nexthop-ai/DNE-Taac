#!/bin/bash
# Bootstrap the getdeps build infrastructure.
#
# Replaces the manual "clone fbthrift + cp build/fbcode_builder/" step
# with an idempotent script. Shallow-clones fbthrift, copies its
# build/fbcode_builder/ into this repo, then overlays our custom
# manifests from getdeps/manifests/.
#
# Usage:
#   ./scripts/setup_getdeps.sh          # no-op if build/fbcode_builder exists
#   ./scripts/setup_getdeps.sh --force  # wipe and re-fetch

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

TARGET="$REPO_ROOT/build/fbcode_builder"
MANIFESTS_SRC="$REPO_ROOT/getdeps/manifests"
FBTHRIFT_URL="https://github.com/facebook/fbthrift.git"

FORCE=0
if [ "${1:-}" = "--force" ]; then
    FORCE=1
fi

if [ -d "$TARGET" ]; then
    if [ "$FORCE" -ne 1 ]; then
        echo "$TARGET already exists — nothing to do."
        echo "Re-run with --force to wipe and re-fetch."
        exit 0
    fi
    echo "Removing existing $TARGET ..."
    rm -rf "$TARGET"
fi

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

echo "Shallow-cloning fbthrift into $TMP ..."
git clone --depth 1 "$FBTHRIFT_URL" "$TMP/fbthrift"

echo "Copying build/fbcode_builder/ into repo ..."
mkdir -p "$(dirname "$TARGET")"
cp -r "$TMP/fbthrift/build/fbcode_builder" "$TARGET"

echo "Overlaying custom manifests from $MANIFESTS_SRC ..."
cp "$MANIFESTS_SRC"/* "$TARGET/manifests/"

echo ""
echo "Setup complete."
echo "Next:"
echo "  python3 build/fbcode_builder/getdeps.py \\"
echo "      --allow-system-packages build --no-tests taac"
