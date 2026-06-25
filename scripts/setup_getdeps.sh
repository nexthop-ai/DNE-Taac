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

# Read the pinned fbthrift rev from our overlay manifest. Same rev that
# getdeps will check out for the build proper — clone the build/fbcode_builder
# tooling at the matching SHA so the two stay in lockstep. We pin
# `fbthrift-python` (the actual getdeps build target Dockerfile.taac uses),
# not `fbthrift` — fbthrift-python is a separate manifest in upstream and
# does not transitively depend on fbthrift.
FBTHRIFT_REV=$(grep -E '^rev[[:space:]]*=' "$MANIFESTS_SRC/fbthrift-python" \
    | head -1 | awk -F'=' '{print $2}' | tr -d ' ')
if [ -z "$FBTHRIFT_REV" ]; then
    echo "ERROR: could not parse rev from $MANIFESTS_SRC/fbthrift-python" >&2
    exit 1
fi

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

echo "Fetching fbthrift at $FBTHRIFT_REV into $TMP (shallow) ..."
git init "$TMP/fbthrift"
git -C "$TMP/fbthrift" fetch --depth 1 "$FBTHRIFT_URL" "$FBTHRIFT_REV"
git -C "$TMP/fbthrift" checkout FETCH_HEAD

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
