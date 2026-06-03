#!/bin/bash
# Host-side cache publish for the fbthrift install tree.
#
# Tars /scratch/installed/ (sans taac-* runtime build) from the named
# docker volume `fboss-scratch-<distro>` and uploads it to the URI
# configured in scripts/_cache-config.sh (TAAC_CACHE_URI). Consumed by
# taac-cache-pull.sh on subsequent builds.
#
# TAAC_CACHE_URI is the full destination URL — caller is responsible
# for naming the object (e.g. encoding the manifest rev in the path).
# This script just packages whatever is in the volume and uploads it.
#
# Prerequisites:
#   - Successful prior build via run-fboss-docker.sh getdeps-build,
#     which populates the named volume.
#   - scripts/_cache-config.sh present (or env vars set in CI) with
#     TAAC_CACHE_URI set to the full destination URL for this build.
#
# Usage:
#   ./scripts/taac-cache-push.sh --distro {centos|debian}

set -euo pipefail

DISTRO=""
while [[ $# -gt 0 ]]; do
    case "$1" in
        --distro) DISTRO="$2"; shift 2 ;;
        *) echo "ERROR: unknown arg $1" >&2; exit 1 ;;
    esac
done

if [ -z "$DISTRO" ]; then
    echo "ERROR: --distro {centos|debian} required" >&2
    exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
SCRATCH_VOLUME="fboss-scratch-$DISTRO"

# Source org-specific cache config if present. Defines TAAC_CACHE_URI.
# Required for publish — unlike cache-pull (which silently no-ops
# without config), push is a deliberate action and fails loud if not
# configured.
if [ -f "$SCRIPT_DIR/_cache-config.sh" ]; then
    # shellcheck source=scripts/_cache-config.sh.example
    source "$SCRIPT_DIR/_cache-config.sh"
fi

if [ -z "${TAAC_CACHE_URI:-}" ]; then
    echo "ERROR: TAAC_CACHE_URI not set" >&2
    echo "  Set TAAC_CACHE_URI via scripts/_cache-config.sh" >&2
    echo "  (see scripts/_cache-config.sh.example)." >&2
    exit 1
fi

# shellcheck source=scripts/_lib_cache_uri.sh
source "$SCRIPT_DIR/_lib_cache_uri.sh"

PUT_BIN="$(cache_uri_put_bin "$TAAC_CACHE_URI" 2>/dev/null || true)"
if [ -z "$PUT_BIN" ]; then
    echo "ERROR: TAAC_CACHE_URI=$TAAC_CACHE_URI uses a scheme that doesn't support push" >&2
    exit 1
fi
if ! command -v "$PUT_BIN" >/dev/null 2>&1; then
    echo "ERROR: '$PUT_BIN' (needed for $TAAC_CACHE_URI) not on PATH" >&2
    exit 1
fi

if ! docker volume inspect "$SCRATCH_VOLUME" >/dev/null 2>&1; then
    echo "ERROR: docker volume '$SCRATCH_VOLUME' not found" >&2
    echo "Run a getdeps build first: ./docker/run-fboss-docker.sh --distro $DISTRO getdeps-build" >&2
    exit 1
fi

# Sanity-check the volume actually contains an fbthrift-python install tree.
if ! docker run --rm -v "$SCRATCH_VOLUME":/scratch:ro alpine:3 \
        sh -c 'test -d /scratch/installed/fbthrift-python && echo found' \
        | grep -q '^found$'; then
    echo "ERROR: /scratch/installed/fbthrift-python not found in volume '$SCRATCH_VOLUME'" >&2
    echo "Was the getdeps build successful?" >&2
    exit 1
fi

TMP_HOST="$(mktemp -d)"
trap 'rm -rf "$TMP_HOST"' EXIT

# Local filename is opaque — only the destination URI matters. Use a
# stable name so the docker-run command line is readable; the upload
# lands at $TAAC_CACHE_URI regardless of what we call it here.
TARBALL="$TMP_HOST/fbthrift-python.tar.gz"

echo "Packaging /scratch/installed/ from volume '$SCRATCH_VOLUME' (excluding taac-*) ..."
docker run --rm \
    -u "$(id -u):$(id -g)" \
    -v "$SCRATCH_VOLUME":/scratch:ro \
    -v "$TMP_HOST":/out \
    alpine:3 \
    sh -c "cd /scratch/installed && tar -czf /out/fbthrift-python.tar.gz --exclude='taac-*' ."

SIZE_MB=$(du -m "$TARBALL" | awk '{print $1}')
echo "Uploading $TARBALL (${SIZE_MB} MB) -> $TAAC_CACHE_URI ..."
cache_uri_put "$TARBALL" "$TAAC_CACHE_URI"
echo "Done: $TAAC_CACHE_URI"
