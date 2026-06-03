#!/bin/bash
# Build the vendor-shippable TAAC Docker image (fboss-taac).
#
# Builds the FBOSS base image if missing, then runs
# docker/Dockerfile.taac to produce the final image.
#
# Usage:
#   ./docker/build-taac-image.sh                    # default tag
#   ./docker/build-taac-image.sh --tag my-taac:v1   # custom tag
#   ./docker/build-taac-image.sh --no-cache         # skip Docker layer cache
#
# Env overrides:
#   FBOSS_IMAGE_SRC   Where to clone/find facebook/fboss for the base image
#                     build context (default: ~/.taac-fboss-image-src)

set -euo pipefail

TAG="fboss-taac"
NO_CACHE=0
while [[ $# -gt 0 ]]; do
    case "$1" in
        --tag)
            if [[ $# -lt 2 || -z "${2:-}" ]]; then
                echo "Error: --tag requires a value" >&2
                exit 1
            fi
            TAG="$2"
            shift 2
            ;;
        --no-cache)
            NO_CACHE=1
            shift
            ;;
        *)
            echo "Error: unknown argument: $1" >&2
            echo "Usage: $0 [--tag <name>] [--no-cache]" >&2
            exit 1
            ;;
    esac
done

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
FBOSS_IMAGE_SRC="${FBOSS_IMAGE_SRC:-$HOME/.taac-fboss-image-src}"
FBOSS_PUBLIC_URL="https://github.com/facebook/fboss.git"
BASE_IMAGE="fboss-build-env:centos"

# Build the FBOSS base image if missing.
if ! docker image inspect "$BASE_IMAGE" >/dev/null 2>&1; then
    echo "Base image $BASE_IMAGE not found — building..."
    if [[ ! -d "$FBOSS_IMAGE_SRC/.git" ]]; then
        echo "Cloning $FBOSS_PUBLIC_URL into $FBOSS_IMAGE_SRC (shallow) ..."
        git clone --depth=1 "$FBOSS_PUBLIC_URL" "$FBOSS_IMAGE_SRC"
    fi
    # USE_CLANG=false: on CentOS, this makes glog and friends link
    # against system libunwind.so.8 instead of LLVM's libunwind.so.1,
    # which isn't on the runtime search path and breaks auditwheel
    # during fbthrift-python wheel repair.
    docker build --build-arg USE_CLANG=false \
        -t "$BASE_IMAGE" \
        -f "$FBOSS_IMAGE_SRC/fboss/oss/docker/Dockerfile" \
        "$FBOSS_IMAGE_SRC"
    echo "Built $BASE_IMAGE"
fi

DOCKER_BUILD_ARGS=()
if [[ "$NO_CACHE" -eq 1 ]]; then
    DOCKER_BUILD_ARGS+=(--no-cache)
fi

echo "Building $TAG from docker/Dockerfile.taac ..."
docker build \
    "${DOCKER_BUILD_ARGS[@]}" \
    -f "$REPO_ROOT/docker/Dockerfile.taac" \
    -t "$TAG" \
    "$REPO_ROOT"

echo "Done: $TAG"
