#!/bin/bash
# Developer shell into the TAAC container with workspace bind-mounted.
#
# Usage:
#   ./docker/run_taac_docker.sh                          # shell with local source overlay
#   ./docker/run_taac_docker.sh --regen                  # regen thrift bindings on entry, then shell
#   ./docker/run_taac_docker.sh --image <image>          # use a specific image
#   ./docker/run_taac_docker.sh run <cmd>                # run a command instead of interactive shell

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

IMAGE="fboss-taac"
WORKSPACE="$REPO_ROOT"
REGEN=0
SUBCMD=shell

while [[ $# -gt 0 ]]; do
    case "$1" in
        --regen)
            REGEN=1
            shift
            ;;
        --image)
            if [[ $# -lt 2 || -z "${2:-}" ]]; then
                echo "Error: --image requires a value" >&2
                exit 1
            fi
            IMAGE="$2"
            shift 2
            ;;
        --workspace)
            if [[ $# -lt 2 || -z "${2:-}" ]]; then
                echo "Error: --workspace requires a value" >&2
                exit 1
            fi
            WORKSPACE="$(cd "$2" && pwd)"
            shift 2
            ;;
        run)
            SUBCMD=run
            shift
            break
            ;;
        *)
            echo "Usage: $0 [--regen] [--image <name>] [--workspace <path>] [run <cmd...>]" >&2
            exit 1
            ;;
    esac
done

DOCKER_ARGS=(
    --rm -it --network host
    -v "$WORKSPACE":/workspace
)

# Auto-forward TAAC_* env vars (TAAC_OSS, TAAC_SSH_USER, TAAC_SSH_PASSWORD,
# TAAC_DEVICE_INFO_PATH, etc.) so callers can `export TAAC_FOO=bar` on the
# host and have it visible in the container — keeps secrets like
# TAAC_SSH_PASSWORD out of `bash -c '...'` strings + shell history.
while IFS= read -r _taac_var; do
    DOCKER_ARGS+=(-e "$_taac_var")
done < <(env | grep '^TAAC_' | cut -d= -f1)

if [[ "$REGEN" -eq 1 ]]; then
    INIT='taac-regen-thrift --quiet /workspace/taac/thrift /tmp/regen && export PYTHONPATH=/workspace:/tmp/regen/gen-python:$PYTHONPATH'
else
    INIT='export PYTHONPATH=/workspace:$PYTHONPATH'
fi

echo "Using image: $IMAGE" >&2

if [[ "$SUBCMD" = "run" ]]; then
    # Hybrid quoting so command args survive intact: INIT expands at
    # the outer shell (its body uses single-quoted '$PYTHONPATH' to
    # defer to the inner bash); 'exec "$@"' stays literal and is
    # resolved by the inner bash from the positional args we append.
    exec docker run "${DOCKER_ARGS[@]}" "$IMAGE" \
        bash -c "$INIT"' && exec "$@"' _ "$@"
else
    exec docker run "${DOCKER_ARGS[@]}" "$IMAGE" bash -c "$INIT && exec bash"
fi
