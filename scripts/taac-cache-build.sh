#!/bin/bash
# Pipeline 1 (build & publish the fbthrift install-tree cache tarball).
#
# Reads the pinned fbthrift SHA from getdeps/manifests/fbthrift-python,
# builds docker/Dockerfile.fbthrift via `docker buildx`, extracts the
# baked-in tarball from the `export` stage into $REPO_ROOT/.fbthrift-cache/,
# and (with --push) uploads via the configured cache CLI.
#
# Self-contained — no dependency on the named docker volume that
# `run-fboss-docker.sh getdeps-build` populates. CI-friendly: just needs
# docker (with buildx) and (for --push) the configured cache CLI on the
# runner.
#
# Use scripts/taac-cache-push.sh instead if you've already done a
# `getdeps-build` locally and want to publish from that named volume.
#
# Prerequisites:
#   - fboss-build-env:<distro> image (build via run-fboss-docker.sh build-base)
#   - docker buildx (Docker 19.03+; standard in modern installs)
#   - For --push: scripts/_cache-config.sh present (or env vars set in CI)
#     defining TAAC_CACHE_BUCKET_PREFIX + TAAC_CACHE_PUT_CMD. See
#     scripts/_cache-config.sh.example.
#
# Usage:
#   ./scripts/taac-cache-build.sh                       # build tarball only
#   ./scripts/taac-cache-build.sh --push                # build + upload
#   ./scripts/taac-cache-build.sh --distro debian       # debian variant
#   ./scripts/taac-cache-build.sh --distro centos --push

set -euo pipefail

DISTRO=centos
PUSH=0
while [[ $# -gt 0 ]]; do
    case "$1" in
        --distro) DISTRO="$2"; shift 2 ;;
        --push)   PUSH=1; shift ;;
        *) echo "ERROR: unknown arg $1" >&2; exit 1 ;;
    esac
done

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
MANIFEST="$REPO_ROOT/getdeps/manifests/fbthrift-python"
BASE_IMAGE="fboss-build-env:$DISTRO"
OUT_DIR="$REPO_ROOT/.fbthrift-cache"

# Source org-specific cache config if present (defines
# TAAC_CACHE_BUCKET_PREFIX + TAAC_CACHE_PUT_CMD). Only needed for --push.
if [ -f "$SCRIPT_DIR/_cache-config.sh" ]; then
    # shellcheck source=scripts/_cache-config.sh.example
    source "$SCRIPT_DIR/_cache-config.sh"
fi

if [ ! -f "$MANIFEST" ]; then
    echo "ERROR: $MANIFEST not found" >&2
    exit 1
fi

# shellcheck source=scripts/_lib_rev.sh
source "$SCRIPT_DIR/_lib_rev.sh"
REV=$(get_fbthrift_rev "$MANIFEST")
if [ -z "$REV" ]; then
    echo "ERROR: no rev pinned in $MANIFEST" >&2
    exit 1
fi

if ! docker image inspect "$BASE_IMAGE" >/dev/null 2>&1; then
    echo "ERROR: $BASE_IMAGE not found." >&2
    echo "  Build via: ./docker/run-fboss-docker.sh --distro $DISTRO build-base" >&2
    exit 1
fi

if ! docker buildx version >/dev/null 2>&1; then
    echo "ERROR: docker buildx not available. Need Docker 19.03+." >&2
    exit 1
fi

# `docker buildx build --output type=local` requires an active builder
# instance. On fresh Docker installs (or older `docker-container` driver
# setups) `docker buildx build` can fail with a cryptic error if no
# builder is registered. Bootstrap the default builder if possible; fall
# back to creating a named one. Idempotent on already-set-up runners.
if ! docker buildx inspect --bootstrap >/dev/null 2>&1; then
    echo "No buildx builder found; creating 'taac-cache-builder' ..."
    docker buildx create --use --name taac-cache-builder
fi

mkdir -p "$OUT_DIR"

# Drop any stale tarballs in the output dir so the buildx extract is the
# only thing that lands there.
#
# NOTE: side effect — if a developer ran `taac-cache-pull.sh` on this
# same machine earlier and is now running `taac-cache-build.sh` to
# rebuild from source, this wipes the previously-pulled tarball. That's
# usually what you want (you're rebuilding because you don't trust the
# pulled one), but worth knowing if you call cache-build interactively
# without expecting the side effect.
rm -f "$OUT_DIR"/fbthrift-python-*.tar.gz "$OUT_DIR"/fbthrift-python-rev.txt

echo "Building fbthrift install-tree cache for rev=$REV (distro=$DISTRO) ..."
docker buildx build \
    -f "$REPO_ROOT/docker/Dockerfile.fbthrift" \
    --build-arg "BASE=$BASE_IMAGE" \
    --build-arg "REV=$REV" \
    --target export \
    --output "type=local,dest=$OUT_DIR" \
    "$REPO_ROOT"

TARBALL="$OUT_DIR/fbthrift-python-$REV.tar.gz"
if [ ! -s "$TARBALL" ]; then
    echo "ERROR: build did not produce $TARBALL" >&2
    ls -la "$OUT_DIR" >&2
    exit 1
fi

SIZE_MB=$(du -m "$TARBALL" | awk '{print $1}')
echo "Built $TARBALL (${SIZE_MB} MB)"

if [ "$PUSH" -eq 1 ]; then
    if [ -z "${TAAC_CACHE_BUCKET_PREFIX:-}" ] || [ -z "${TAAC_CACHE_PUT_CMD:-}" ]; then
        echo "ERROR: cache storage not configured" >&2
        echo "  Set TAAC_CACHE_BUCKET_PREFIX and TAAC_CACHE_PUT_CMD via scripts/_cache-config.sh" >&2
        echo "  (see scripts/_cache-config.sh.example)." >&2
        exit 1
    fi
    PUT_BIN="$(echo "$TAAC_CACHE_PUT_CMD" | awk '{print $1}')"
    if ! command -v "$PUT_BIN" >/dev/null 2>&1; then
        echo "ERROR: '$PUT_BIN' (from TAAC_CACHE_PUT_CMD) not on PATH" >&2
        exit 1
    fi
    DST_DIR="$TAAC_CACHE_BUCKET_PREFIX/"
    echo "Uploading $TARBALL -> $DST_DIR$(basename "$TARBALL") ..."
    $TAAC_CACHE_PUT_CMD "$TARBALL" "$DST_DIR"
    echo "Done: $DST_DIR$(basename "$TARBALL")"
fi
