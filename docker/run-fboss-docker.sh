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
#   --fbthrift-tarball <path>
#                     for `build-taac-image` only: use this local tarball as
#                     the cache input instead of pulling from S3. The file is
#                     copied into .fbthrift-cache/ as fbthrift-python-<rev>
#                     .tar.gz where <rev> is the current pin; Dockerfile.taac
#                     Layer A2 extracts it like any other cache hit. Useful
#                     for offline builds, custom-built tarballs, or peer-to-
#                     peer sharing without going through the bucket. Mutually
#                     exclusive with --no-cache.
#   --workspace=main  for `build-taac-image` only: shallow-clone main from
#                     github.com/nexthop-ai/private-DNE-Taac into a temp dir
#                     and use that as the docker build context instead of the
#                     local working copy. Useful for CI nightly builds and
#                     for verifying that main is buildable without setting up
#                     a workspace. Combines freely with --no-cache and
#                     --fbthrift-tarball. Today only `main` is supported.
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
FBTHRIFT_TARBALL=""
WORKSPACE=""
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
        --fbthrift-tarball)
            FBTHRIFT_TARBALL="$2"
            shift 2
            ;;
        --workspace=*)
            WORKSPACE="${1#--workspace=}"
            shift
            ;;
        *)
            break
            ;;
    esac
done

if [[ "$NO_CACHE" -eq 1 && -n "$FBTHRIFT_TARBALL" ]]; then
    echo "Error: --no-cache and --fbthrift-tarball are mutually exclusive." >&2
    echo "  --no-cache forces a full source build (ignores any local tarball)." >&2
    echo "  --fbthrift-tarball <path> uses the given tarball as the cache input." >&2
    exit 1
fi

if [[ -n "$WORKSPACE" && "$WORKSPACE" != "main" ]]; then
    echo "Error: --workspace currently only supports 'main' (got: '$WORKSPACE')." >&2
    exit 1
fi

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
# Source for --workspace=main shallow-clone. Keep in lockstep with the
# remote that this repo lives at.
TAAC_PUBLIC_URL="https://github.com/nexthop-ai/private-DNE-Taac.git"

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
  --fbthrift-tarball PATH
                  for \`build-taac-image\` only: use PATH as the cache input
                  instead of pulling from S3. Copied into .fbthrift-cache/ and
                  treated like any other cache hit by Dockerfile Layer A2.
                  Mutually exclusive with --no-cache.
  --workspace=main
                  for \`build-taac-image\` only: shallow-clone main from
                  $TAAC_PUBLIC_URL into a temp dir and use that as the docker
                  build context. Verifies main is buildable without depending
                  on local working state. Today only 'main' is supported.
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
        # Resolve the docker build context. Default is the local working copy
        # ($REPO_ROOT). --workspace=main shallow-clones main into a temp dir
        # and uses that instead — useful for nightly/CI builds that want to
        # verify main is buildable without depending on the runner's local
        # working state.
        if [[ "$WORKSPACE" == "main" ]]; then
            WORKSPACE_TMP=$(mktemp -d)
            trap 'rm -rf "$WORKSPACE_TMP"' EXIT
            echo "--workspace=main: shallow-cloning $TAAC_PUBLIC_URL main -> $WORKSPACE_TMP/checkout ..."
            git clone --depth 1 --branch main "$TAAC_PUBLIC_URL" "$WORKSPACE_TMP/checkout"
            # Record the cloned commit SHA so postmortems can pin failures
            # to a specific revision. main floats, so two runs minutes apart
            # may build different artifacts; this is the only audit trail.
            CLONED_SHA=$(git -C "$WORKSPACE_TMP/checkout" rev-parse HEAD)
            echo "--workspace=main: cloned commit $CLONED_SHA"
            BUILD_CONTEXT="$WORKSPACE_TMP/checkout"
        else
            BUILD_CONTEXT="$REPO_ROOT"
        fi
        # Resolve the fbthrift install-tree cache input. Three modes:
        #   --fbthrift-tarball <path>: explicit local tarball (rtl's "input"
        #     framing). Copy as fbthrift-python-<rev>.tar.gz so Dockerfile
        #     Layer A2 treats it like any other cache hit.
        #   --no-cache: skip everything, force full source build.
        #   default: best-effort pull from the Nexthop bucket. Silent fall-
        #     through on miss.
        # Dockerfile.taac's Layer A2 COPYs .fbthrift-cache/ in and extracts
        # whatever tarball matches the pinned rev (if any). All paths use
        # $BUILD_CONTEXT so --workspace=main resolves the cache against the
        # cloned main's pin, not the local working copy's.
        mkdir -p "$BUILD_CONTEXT/.fbthrift-cache"
        if [[ -n "$FBTHRIFT_TARBALL" ]]; then
            if [[ ! -f "$FBTHRIFT_TARBALL" ]]; then
                echo "Error: --fbthrift-tarball file not found: $FBTHRIFT_TARBALL" >&2
                exit 1
            fi
            # Resolve to an absolute path before any later cd / cp. Cheap
            # insurance: caller might pass a relative path, and downstream
            # code (or future edits) could change the working directory
            # between this check and the cp.
            FBTHRIFT_TARBALL=$(realpath "$FBTHRIFT_TARBALL")
            # shellcheck source=scripts/_lib_rev.sh
            source "$BUILD_CONTEXT/scripts/_lib_rev.sh"
            REV=$(get_fbthrift_rev \
                "$BUILD_CONTEXT/getdeps/manifests/fbthrift-python")
            if [[ -z "$REV" ]]; then
                # An empty REV would produce `fbthrift-python-.tar.gz` which
                # Layer A2 never matches, giving a silent cold build with
                # the user-supplied tarball ignored. Fail loud instead.
                echo "Error: could not parse rev from $BUILD_CONTEXT/getdeps/manifests/fbthrift-python" >&2
                exit 1
            fi
            echo "--fbthrift-tarball: using $FBTHRIFT_TARBALL as cache input (rev=$REV)"
            rm -f "$BUILD_CONTEXT/.fbthrift-cache"/fbthrift-python-*.tar.gz
            cp "$FBTHRIFT_TARBALL" \
                "$BUILD_CONTEXT/.fbthrift-cache/fbthrift-python-$REV.tar.gz"
        elif [[ "$NO_CACHE" -eq 1 ]]; then
            echo "--no-cache: skipping S3 cache restore, forcing full source build"
            rm -f "$BUILD_CONTEXT/.fbthrift-cache"/fbthrift-python-*.tar.gz
        else
            "$BUILD_CONTEXT/scripts/taac-cache-pull.sh" || true
        fi
        echo "Building fboss-taac:$DISTRO from docker/Dockerfile.taac (BASE=$IMAGE_TAG, context=$BUILD_CONTEXT) ..."
        docker build \
            -f "$BUILD_CONTEXT/docker/Dockerfile.taac" \
            --build-arg "BASE=$IMAGE_TAG" \
            -t "fboss-taac:$DISTRO" \
            "$BUILD_CONTEXT"
        echo "Done: fboss-taac:$DISTRO"
        ;;
    *)
        usage
        exit 1
        ;;
esac
