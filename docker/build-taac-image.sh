#!/bin/bash
# Build the vendor-shippable TAAC Docker image (fboss-taac).
#
# Builds the FBOSS base image if missing, then runs
# docker/Dockerfile.taac to produce the final image.
#
# Usage:
#   ./docker/build-taac-image.sh                       # default tag, default parallelism
#   ./docker/build-taac-image.sh --tag my-taac:v1      # custom tag
#   ./docker/build-taac-image.sh --no-cache            # skip Docker layer cache
#   ./docker/build-taac-image.sh --num-jobs 4          # cap getdeps parallelism
#
# Parallelism note: the fbthrift / cc1plus compile phase is the main
# memory hog (~5 GiB per worker). On memory-constrained hosts (<~6 GiB
# per worker) the OOM killer will reap workers — and often sshd along
# with them — long before disk or CPU saturates. Default leaves
# getdeps' own default in place (= nproc); pass `--num-jobs N` to cap
# when you've seen the OOM killer fire. Rule of thumb: N = min(nproc,
# floor(RAM_GiB / 5)).
#
# Env overrides:
#   FBOSS_IMAGE_SRC   Where to clone/find facebook/fboss for the base image
#                     build context (default: ~/.taac-fboss-image-src)

set -euo pipefail

TAG="fboss-taac"
NO_CACHE=0
NUM_JOBS=""
USE_CLASSIC_BUILDER=0
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
        --num-jobs)
            if [[ $# -lt 2 || -z "${2:-}" ]]; then
                echo "Error: --num-jobs requires a value" >&2
                exit 1
            fi
            if ! [[ "$2" =~ ^[1-9][0-9]*$ ]]; then
                echo "Error: --num-jobs must be a positive integer, got: $2" >&2
                exit 1
            fi
            NUM_JOBS="$2"
            shift 2
            ;;
        --use-classic-builder)
            USE_CLASSIC_BUILDER=1
            shift
            ;;
        *)
            echo "Error: unknown argument: $1" >&2
            echo "Usage: $0 [--tag <name>] [--no-cache] [--num-jobs <N>] [--use-classic-builder]" >&2
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
# Empty NUM_JOBS arg lets Dockerfile.taac fall through to getdeps'
# nproc default; only forward when the caller set --num-jobs N.
if [[ -n "$NUM_JOBS" ]]; then
    DOCKER_BUILD_ARGS+=(--build-arg "NUM_JOBS=$NUM_JOBS")
    echo "Capping getdeps parallelism at $NUM_JOBS"
fi

echo "Building $TAG from docker/Dockerfile.taac ..."
if [[ "$USE_CLASSIC_BUILDER" -eq 1 ]]; then
    # Escape hatch for unclipped diagnostics on a failing RUN step.
    # BuildKit caps each step's daemon-side scrollback (default 1 MiB);
    # `--progress=plain` controls render format, not buffer size. The
    # classic builder streams the full output. The trade-off is its
    # single-threaded `commitContainer` phase on multi-GB layers, which
    # can take an hour-plus on the fbthrift install tree — only worth
    # it when you need to read what cc1plus printed before it died.
    echo "Using classic builder (DOCKER_BUILDKIT=0)"
    DOCKER_BUILDKIT=0 docker build \
        "${DOCKER_BUILD_ARGS[@]}" \
        -f "$REPO_ROOT/docker/Dockerfile.taac" \
        -t "$TAG" \
        "$REPO_ROOT"
else
    # BUILDKIT_STEP_LOG_MAX_SIZE=-1 lifts the per-step log buffer cap.
    # The dockerd-side env is what actually moves the needle — see
    # scripts/setup-host-buildkit-config.sh for the systemd drop-in
    # that puts this on the docker.service environment (the client-
    # side env here is best-effort; some Docker versions propagate
    # it to the embedded BuildKit, others read it only from dockerd).
    #
    # --cache-to/--cache-from with a local-FS backend persists the
    # BuildKit layer cache to TAAC_BUILDKIT_CACHE_DIR (default
    # ~/.taac-buildkit-cache) so daemon restarts and `docker system
    # prune` don't drop the ~20 min fbthrift+fboss-thrift-defs compile.
    CACHE_DIR="${TAAC_BUILDKIT_CACHE_DIR:-$HOME/.taac-buildkit-cache}"
    mkdir -p "$CACHE_DIR"
    echo "Using BuildKit; local-FS cache at $CACHE_DIR"
    BUILDKIT_STEP_LOG_MAX_SIZE=-1 docker build \
        --progress=plain \
        --cache-to "type=local,dest=$CACHE_DIR,mode=max" \
        --cache-from "type=local,src=$CACHE_DIR" \
        "${DOCKER_BUILD_ARGS[@]}" \
        -f "$REPO_ROOT/docker/Dockerfile.taac" \
        -t "$TAG" \
        "$REPO_ROOT"
fi

echo "Done: $TAG"
