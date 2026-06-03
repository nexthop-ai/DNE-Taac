#!/bin/bash
# Entrypoint for fboss-taac:<distro> images (built from docker/Dockerfile.taac).
#
# Resolves the per-config install hash + native lib search paths so that
# `python3 -c 'import taac.libs.taac_runner'` (and any TAAC entry point)
# works out of the box. TAAC_OSS defaults to 1; override with
# `docker run -e TAAC_OSS=0 ...` if needed.

set -e

TAAC_INSTALL=$(ls -d /scratch/installed/taac-* 2>/dev/null | head -1)
if [[ -z "$TAAC_INSTALL" ]]; then
    echo "taac-entrypoint: /scratch/installed/taac-* not found — image is broken." >&2
    exit 1
fi

export PYTHONPATH="/taac:${TAAC_INSTALL}/lib/python3/site-packages${PYTHONPATH:+:${PYTHONPATH}}"
export LD_LIBRARY_PATH="$(find /scratch/installed -maxdepth 2 -type d -name lib | tr '\n' ':')${LD_LIBRARY_PATH:+:${LD_LIBRARY_PATH}}"
: "${TAAC_OSS:=1}"
export TAAC_OSS

exec "$@"
