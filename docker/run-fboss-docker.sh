#!/bin/bash
# Build TAAC inside one of FBOSS's open-source Docker images.
#
# This wrapper:
#   - Clones github.com/facebook/fboss to provide the image build context
#     (FBOSS's Dockerfiles COPY from the fboss source tree at build time).
#   - Builds the Docker image (CentOS Stream 9 or Debian Bookworm) using
#     FBOSS's open-source Dockerfile — apt/dnf installs only, ~10 min.
#     This is *not* a TAAC build; the actual TAAC compile (folly + fbthrift
#     + fboss thrift defs etc.; 30-60 min on a clean run) happens later
#     inside the container via the `getdeps-build` subcommand. On CentOS,
#     passes USE_CLANG=false so glog and friends link against system
#     libunwind.so.8 instead of LLVM's libunwind.so.1 (which is not on the
#     runtime search path and breaks auditwheel during fbthrift-python's
#     wheel repair).
#   - Auto-runs scripts/setup_getdeps.sh on the host (one-time, idempotent)
#     if build/fbcode_builder/ isn't already present — that step shallow-
#     clones fbthrift to seed the getdeps tooling under build/.
#   - Runs getdeps.py inside the image with this repo bind-mounted at /taac
#     and a persistent docker-managed named volume mounted at /scratch (the
#     getdeps cache — folly/fbthrift/etc. install tree). The volume lives
#     in docker's volume namespace, NOT on the host filesystem, so the
#     container does not depend on host-side bind-mount layout.
#
# Usage:
#   ./docker/run-fboss-docker.sh --distro {centos|debian} build-base
#   ./docker/run-fboss-docker.sh --distro {centos|debian} shell
#   ./docker/run-fboss-docker.sh --distro {centos|debian} run <CMD...>
#   ./docker/run-fboss-docker.sh --distro {centos|debian} getdeps-build
#
# Optional flags (must precede the subcommand):
#   --network <mode>  passed through to `docker run --network` (e.g. `host`).
#                     Defaults to docker's bridge network. Use `host` to give
#                     the container access to internal-DNS hostnames (e.g.
#                     for live-device runner smokes against fboss101.*).
#   --no-cache        for `build-taac-image` only: skip the S3 cache restore
#                     and force a full source build of fbthrift-python +
#                     transitive deps. Use when you want to validate the
#                     cold path or when the cache is suspected stale.
#
# Env overrides:
#   FBOSS_IMAGE_SRC   Where to clone/find facebook/fboss for the build context
#                     (default: ~/.taac-fboss-image-src)
#   SCRATCH_VOLUME    Docker named volume holding the getdeps cache
#                     (default: fboss-scratch-<distro>). Inspect with
#                     `docker volume inspect <name>`; remove with
#                     `docker volume rm <name>`.

set -e

DISTRO=""
NETWORK=""
NO_CACHE=0
while [[ $# -gt 0 ]]; do
    case "$1" in
        --distro)
            DISTRO="$2"
            shift 2
            ;;
        --network)
            NETWORK="$2"
            shift 2
            ;;
        --no-cache)
            NO_CACHE=1
            shift
            ;;
        *)
            break
            ;;
    esac
done

if [[ -z "$DISTRO" ]]; then
    echo "Error: --distro {centos|debian} is required."
    echo "Run with no arguments after --distro for usage."
    exit 1
fi
if [[ "$DISTRO" != "centos" && "$DISTRO" != "debian" ]]; then
    echo "Error: --distro must be 'centos' or 'debian' (got: $DISTRO)"
    exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
FBOSS_IMAGE_SRC="${FBOSS_IMAGE_SRC:-$HOME/.taac-fboss-image-src}"
# Per-distro scratch lives in a docker named volume (managed by docker, not on
# the host fs). Auto-created by `docker run -v <name>:<path>` if missing.
SCRATCH_VOLUME="${SCRATCH_VOLUME:-fboss-scratch-$DISTRO}"
IMAGE_TAG="fboss-build-env:$DISTRO"
FBOSS_PUBLIC_URL="https://github.com/facebook/fboss.git"

if [[ "$DISTRO" == "centos" ]]; then
    DOCKERFILE_PATH="fboss/oss/docker/Dockerfile"
    BUILD_ARGS=(--build-arg USE_CLANG=false)
else
    DOCKERFILE_PATH="fboss/oss/docker/Dockerfile.debian"
    BUILD_ARGS=()
fi

ensure_fboss_src() {
    if [[ ! -d "$FBOSS_IMAGE_SRC/.git" ]]; then
        echo "Cloning $FBOSS_PUBLIC_URL into $FBOSS_IMAGE_SRC (shallow) ..."
        git clone --depth=1 "$FBOSS_PUBLIC_URL" "$FBOSS_IMAGE_SRC"
    fi
}

build_base() {
    ensure_fboss_src
    echo "Building $IMAGE_TAG from $DOCKERFILE_PATH ..."
    docker build "${BUILD_ARGS[@]}" \
        -t "$IMAGE_TAG" \
        -f "$FBOSS_IMAGE_SRC/$DOCKERFILE_PATH" \
        "$FBOSS_IMAGE_SRC"
    echo "Done: $IMAGE_TAG"
}

run_container() {
    if ! docker image inspect "$IMAGE_TAG" > /dev/null 2>&1; then
        echo "Image $IMAGE_TAG not found - building it first..."
        build_base
    fi

    if [[ ! -d "$REPO_ROOT/build/fbcode_builder" ]]; then
        echo "build/fbcode_builder/ not found — bootstrapping via scripts/setup_getdeps.sh ..."
        "$REPO_ROOT/scripts/setup_getdeps.sh"
    fi

    local tty_flags=()
    if [ -t 0 ] && [ -t 1 ]; then
        tty_flags=(-it)
    fi

    local network_flags=()
    if [[ -n "$NETWORK" ]]; then
        network_flags=(--network "$NETWORK")
    fi

    docker run --rm "${tty_flags[@]}" "${network_flags[@]}" \
        -v "$REPO_ROOT":/taac \
        -v "$SCRATCH_VOLUME":/scratch \
        -w /taac \
        "$IMAGE_TAG" \
        "$@"
}

usage() {
    cat <<EOF
Usage: $0 --distro {centos|debian} [--network <mode>] {build-base|shell|run <CMD...>|getdeps-build|build-taac-image}

  build-base        (re)build the $IMAGE_TAG image from FBOSS's open-source Dockerfile
  shell             drop into an interactive shell with this repo mounted at /taac
  run <CMD...>      run a command inside the container with the repo mounted
  getdeps-build     build taac via getdeps with this repo's defaults
                    (persistent scratch in docker volume \`$SCRATCH_VOLUME\`,
                    --no-tests, --allow-system-packages)
  build-taac-image  build the vendor-shippable derived image fboss-taac:$DISTRO
                    via docker/Dockerfile.taac. The image bakes TAAC + transitive
                    deps in. First build is ~22 min cold; subsequent builds use
                    Docker's layer cache — typical TAAC source edits rebuild in
                    ~45 sec.

Optional flags (must precede the subcommand):
  --network MODE  pass through to docker run --network (e.g. \`host\`); defaults to
                  docker's bridge. Use \`host\` for live-device smokes that need
                  internal-DNS hostnames.
  --no-cache      for \`build-taac-image\` only: skip the S3 cache restore and
                  force a full source build. Use to validate the cold path or
                  when the cache is suspected stale.
EOF
}

case "${1:-}" in
    build-base)
        build_base
        ;;
    shell)
        run_container /bin/bash
        ;;
    run)
        shift
        run_container "$@"
        ;;
    getdeps-build)
        run_container python3 build/fbcode_builder/getdeps.py \
            --scratch-path /scratch \
            --extra-cmake-defines='{"enable_tests": "OFF"}' \
            --allow-system-packages build --no-tests taac
        ;;
    build-taac-image)
        if ! docker image inspect "$IMAGE_TAG" > /dev/null 2>&1; then
            echo "Base image $IMAGE_TAG not found - building it first..."
            build_base
        fi
        # Best-effort restore the fbthrift install tree from the Nexthop
        # bucket. Silent fall-through on miss. Dockerfile.taac's Layer A2
        # COPYs .fbthrift-cache/ in and extracts if a matching tarball is
        # present. --no-cache (flag above) skips this step and wipes any
        # local tarball so Layer A2 falls through to the source build.
        mkdir -p "$REPO_ROOT/.fbthrift-cache"
        if [[ "$NO_CACHE" -eq 1 ]]; then
            echo "--no-cache: skipping S3 cache restore, forcing full source build"
            rm -f "$REPO_ROOT/.fbthrift-cache"/fbthrift-python-*.tar.gz
        else
            "$REPO_ROOT/scripts/taac-cache-pull.sh" || true
        fi
        echo "Building fboss-taac:$DISTRO from docker/Dockerfile.taac (BASE=$IMAGE_TAG) ..."
        docker build \
            -f "$REPO_ROOT/docker/Dockerfile.taac" \
            --build-arg "BASE=$IMAGE_TAG" \
            -t "fboss-taac:$DISTRO" \
            "$REPO_ROOT"
        echo "Done: fboss-taac:$DISTRO"
        ;;
    *)
        usage
        exit 1
        ;;
esac
