#!/bin/bash
# Host-side cache restore for the fbthrift install tree.
#
# Fetches a single tarball from the URI configured in
# scripts/_cache-config.sh (TAAC_CACHE_URI) into $REPO_ROOT/.fbthrift-cache/.
# Dockerfile.taac's builder stage then COPYs that dir in and extracts the
# tarball into /scratch/installed/, letting the subsequent getdeps build
# skip the 20+ min fbthrift compile.
#
# TAAC_CACHE_URI points at the full tarball, not a prefix — the caller
# names the right object for the current manifest pin. Local filename is
# the URI's basename, so a URI change (e.g. pin bump → new rev in the
# URL) produces a new local file and the prune below sweeps the stale
# one.
#
# Cache miss, network error, missing CLI for the URI scheme, or
# unconfigured storage all silent-fall-through (exit 0). The Dockerfile
# is the only consumer and it tolerates a missing tarball.
#
# Storage is configured via scripts/_cache-config.sh (gitignored) — see
# scripts/_cache-config.sh.example for the template. Without that file
# the cache feature no-ops.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
CACHE_DIR="$REPO_ROOT/.fbthrift-cache"

# Source org-specific cache config if present. Defines TAAC_CACHE_URI.
# Without it (or with it unset) the cache feature silently no-ops below.
if [ -f "$SCRIPT_DIR/_cache-config.sh" ]; then
    # shellcheck source=scripts/_cache-config.sh.example
    source "$SCRIPT_DIR/_cache-config.sh"
fi

if [ -z "${TAAC_CACHE_URI:-}" ]; then
    echo "cache-pull: TAAC_CACHE_URI not set; skipping"
    echo "cache-pull: see scripts/_cache-config.sh.example to enable"
    exit 0
fi

# shellcheck source=scripts/_lib_cache_uri.sh
source "$SCRIPT_DIR/_lib_cache_uri.sh"

GET_BIN="$(cache_uri_get_bin "$TAAC_CACHE_URI" 2>/dev/null || true)"
if [ -z "$GET_BIN" ]; then
    echo "cache-pull: unrecognized URI scheme in TAAC_CACHE_URI=$TAAC_CACHE_URI; skipping"
    exit 0
fi
if ! command -v "$GET_BIN" >/dev/null 2>&1; then
    echo "cache-pull: '$GET_BIN' (needed for $TAAC_CACHE_URI) not on PATH; skipping"
    exit 0
fi

# Local filename = URI's basename. A URI change cleanly produces a
# different local filename; any other .tar.gz in CACHE_DIR is stale and
# gets pruned below.
#
# Manual staging (demo workflows that drop a tarball into .fbthrift-cache/
# without using this script) relies on Dockerfile.taac globbing *.tar.gz
# — that path is independent of the prune below because the prune only
# runs when TAAC_CACHE_URI is set.
TARBALL="$CACHE_DIR/$(basename "$TAAC_CACHE_URI")"

mkdir -p "$CACHE_DIR"
for f in "$CACHE_DIR"/*.tar.gz; do
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

echo "cache-pull: fetching $TAAC_CACHE_URI -> $TARBALL ..."

# Keep stderr — we want to see the difference between a clean 404 (real
# miss → fall through silently is fine) and an auth/DNS/network failure
# (operator likely needs to fix it). Suppressing stderr made a
# misconfigured CLI look identical to a cache miss, which was hard to
# diagnose.
if ! cache_uri_get "$TAAC_CACHE_URI" "$TARBALL"; then
    echo "cache-pull: miss or error ($TAAC_CACHE_URI) — fbthrift will be built from source"
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
