#!/bin/bash
# Host-side cache restore for the fbthrift install tree.
#
# Reads the pinned fbthrift SHA from getdeps/manifests/fbthrift-python and
# tries to pull `vol-shared/fboss/taac/fbthrift-python-<sha>.tar.gz` from
# the Nexthop bucket into $REPO_ROOT/.fbthrift-cache/. The Dockerfile.taac
# builder stage then COPYs that dir in and extracts the tarball into
# /scratch/installed/, letting the subsequent getdeps build skip the
# 20+ min fbthrift compile.
#
# We pin `fbthrift-python` (the actual getdeps build target) not `fbthrift`
# — the two are separate upstream manifests, and the build only references
# fbthrift-python's dep graph.
#
# Cache miss, network error, or `ng` not installed all silent-fall-through
# (exit 0). The Dockerfile is the only consumer and it tolerates a missing
# tarball.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
MANIFEST="$REPO_ROOT/getdeps/manifests/fbthrift-python"
CACHE_DIR="$REPO_ROOT/.fbthrift-cache"
BUCKET_PREFIX="vol-shared/fboss/taac"

if [ ! -f "$MANIFEST" ]; then
    echo "cache-pull: $MANIFEST not found, skipping"
    exit 0
fi

REV=$(grep -E '^rev[[:space:]]*=' "$MANIFEST" | head -1 | awk -F'=' '{print $2}' | tr -d ' ')
if [ -z "$REV" ]; then
    echo "cache-pull: no rev pinned in $MANIFEST, skipping"
    exit 0
fi

if ! command -v ng >/dev/null 2>&1; then
    echo "cache-pull: 'ng' CLI not on PATH, skipping (will build fbthrift from source)"
    exit 0
fi

mkdir -p "$CACHE_DIR"
TARBALL="$CACHE_DIR/fbthrift-python-$REV.tar.gz"

# Auto-cleanup: prune any cached tarballs for revs other than the one we
# care about right now. Branch-switching across pins would otherwise
# leave 1+ GB stale tarballs sitting on disk.
for f in "$CACHE_DIR"/fbthrift-python-*.tar.gz; do
    [ -e "$f" ] || continue
    if [ "$f" != "$TARBALL" ]; then
        echo "cache-pull: pruning stale $f"
        rm -f "$f"
    fi
done

if [ -s "$TARBALL" ]; then
    echo "cache-pull: $TARBALL already present, skipping fetch"
    exit 0
fi

KEY="$BUCKET_PREFIX/fbthrift-python-$REV.tar.gz"
echo "cache-pull: fetching $KEY -> $TARBALL ..."

# Keep stderr — we want to see the difference between a clean 404 (real
# miss → fall through silently is fine) and an auth/DNS/network failure
# (operator likely needs to fix it). Suppressing stderr made misconfigured
# `ng` look identical to a cache miss, which is hard to diagnose.
if ! ng bucket get "$KEY" "$TARBALL"; then
    echo "cache-pull: miss or error ($KEY) — fbthrift will be built from source"
    rm -f "$TARBALL"
    exit 0
fi

if [ ! -s "$TARBALL" ]; then
    echo "cache-pull: downloaded file is empty, treating as miss"
    rm -f "$TARBALL"
    exit 0
fi

SIZE_MB=$(du -m "$TARBALL" | awk '{print $1}')
echo "cache-pull: hit — restored $TARBALL (${SIZE_MB} MB)"
