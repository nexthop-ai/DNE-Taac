#!/bin/bash
# Host-side cache publish for the fbthrift install tree.
#
# Tars /scratch/installed/ (sans taac-* runtime build) from the named
# docker volume `fboss-scratch-<distro>` and uploads to the Nexthop
# bucket key `vol-shared/fboss/taac/fbthrift-python-<sha>.tar.gz`, where
# <sha> is the pinned rev from getdeps/manifests/fbthrift-python.
# Consumed by taac-cache-pull.sh on subsequent builds.
#
# We pin `fbthrift-python` (the actual getdeps build target) not
# `fbthrift` — the two are separate upstream manifests.
#
# Prerequisites:
#   - Successful prior build via run-fboss-docker.sh getdeps-build,
#     which populates the named volume.
#   - `ng` CLI on PATH (uploads via `ng bucket put`).
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
MANIFEST="$REPO_ROOT/getdeps/manifests/fbthrift-python"
SCRATCH_VOLUME="fboss-scratch-$DISTRO"
BUCKET_PREFIX="vol-shared/fboss/taac"

if [ ! -f "$MANIFEST" ]; then
    echo "ERROR: $MANIFEST not found" >&2
    exit 1
fi

REV=$(grep -E '^rev[[:space:]]*=' "$MANIFEST" | head -1 | awk -F'=' '{print $2}' | tr -d ' ')
if [ -z "$REV" ]; then
    echo "ERROR: no rev pinned in $MANIFEST" >&2
    exit 1
fi

if ! command -v ng >/dev/null 2>&1; then
    echo "ERROR: 'ng' CLI not on PATH" >&2
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

TARBALL_NAME="fbthrift-python-$REV.tar.gz"
TARBALL="$TMP_HOST/$TARBALL_NAME"

echo "Packaging /scratch/installed/ from volume '$SCRATCH_VOLUME' (excluding taac-*) ..."
docker run --rm \
    -u "$(id -u):$(id -g)" \
    -v "$SCRATCH_VOLUME":/scratch:ro \
    -v "$TMP_HOST":/out \
    alpine:3 \
    sh -c "cd /scratch/installed && tar -czf /out/$TARBALL_NAME --exclude='taac-*' ."

SIZE_MB=$(du -m "$TARBALL" | awk '{print $1}')
# `ng bucket put` takes a destination DIRECTORY (trailing /), not a file
# path — the local file's basename becomes the remote key automatically.
DST_DIR="$BUCKET_PREFIX/"
echo "Uploading $TARBALL (${SIZE_MB} MB) -> $DST_DIR$TARBALL_NAME ..."
ng bucket put --mkdir "$TARBALL" "$DST_DIR"
echo "Done: $DST_DIR$TARBALL_NAME"
