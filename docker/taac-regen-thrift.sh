#!/bin/bash
# taac-regen-thrift — regenerate TAAC Python bindings from edited .thrift files.
#
# Designed for the "pull slim image, edit thrift on host workspace, run in
# container" workflow. Wraps the fbthrift compiler (`thrift1`) with the
# include paths needed to resolve TAAC's `include "fboss/..."` and
# `include "thrift/annotation/..."` directives.
#
# Usage:
#   taac-regen-thrift <thrift_src_dir> [<output_dir>]
#
#   thrift_src_dir  Path to a directory containing .thrift files (the
#                   helper walks it recursively). Typically your
#                   bind-mounted workspace's taac/thrift/ tree.
#   output_dir      Where to write generated Python bindings. Defaults
#                   to /tmp/taac-regen.
#
# After running, prepend <output_dir>/gen-python to PYTHONPATH so the
# regenerated bindings override the ones baked into the image:
#
#   export PYTHONPATH=<output_dir>/gen-python:$PYTHONPATH
#
# Output layout matches mstch_python's convention: for a thrift file with
# `namespace py3 X.Y`, generated `.py` files land at
# <output_dir>/gen-python/X/Y/{thrift_types,thrift_enums,...}.py.

set -euo pipefail

QUIET=0
if [[ "${1:-}" = "--quiet" ]]; then
    QUIET=1
    shift
fi

SRC="${1:?Usage: taac-regen-thrift [--quiet] <thrift_src_dir> [<output_dir>]}"
OUT="${2:-/tmp/taac-regen}"

THRIFT1=/scratch/installed/fbthrift-python/bin/thrift1
FBTHRIFT_INCLUDE=/scratch/installed/fbthrift-python/include
# Point at the root of the fboss-thrift-defs install — TAAC schemas
# include paths like `common/fb303/if/fb303.thrift`, `fboss/agent/...`,
# `configerator/...`, all relative to this root.
FBOSS_SCHEMAS=$(ls -d /scratch/installed/fboss-thrift-defs-* 2>/dev/null | head -1)

if [[ ! -x "$THRIFT1" ]]; then
    echo "Error: thrift1 not found at $THRIFT1" >&2
    exit 1
fi
if [[ -z "$FBOSS_SCHEMAS" || ! -d "$FBOSS_SCHEMAS" ]]; then
    echo "Error: FBOSS thrift schemas not found under /scratch/installed/fboss-thrift-defs-*/" >&2
    exit 1
fi
if [[ ! -d "$SRC" ]]; then
    echo "Error: thrift source dir not found: $SRC" >&2
    exit 1
fi

mkdir -p "$OUT"

# Upstream-tracked .thrift files at $SRC/{taac,ixia,neteng}/... use
# Meta-internal monorepo include paths (e.g.
# `include "configerator/structs/neteng/taac/health_check.thrift"`).
# Build a symlink farm at $OUT/staging/ where each include path resolves
# to the actual file under $SRC, then add the staging dir to thrift1 -I.
# Keeps include statements byte-for-byte identical to Meta's upstream.
STAGING="$OUT/staging"
rm -rf "$STAGING"
mkdir -p "$STAGING/configerator/structs/neteng/taac" \
         "$STAGING/configerator/structs/neteng/ixia" \
         "$STAGING/neteng/test_infra/dne/utils/if"
ln -sf "$SRC/taac/health_check.thrift" \
       "$STAGING/configerator/structs/neteng/taac/health_check.thrift"
ln -sf "$SRC/taac/test_as_a_config.thrift" \
       "$STAGING/configerator/structs/neteng/taac/test_as_a_config.thrift"
ln -sf "$SRC/ixia/ixia.thrift" \
       "$STAGING/configerator/structs/neteng/ixia/ixia.thrift"
ln -sf "$SRC/neteng/test_infra/dne/utils/if/qos_config.thrift" \
       "$STAGING/neteng/test_infra/dne/utils/if/qos_config.thrift"

# thrift_files is computed via process substitution (not a pipe) so the
# while loop runs in the current shell and `count` survives the loop.
count=0
while IFS= read -r -d '' f; do
    "$THRIFT1" --gen mstch_python \
        -I "$STAGING" \
        -I "$FBOSS_SCHEMAS" \
        -I "$FBTHRIFT_INCLUDE" \
        -o "$OUT" \
        "$f" 2>/dev/null
    count=$((count + 1))
done < <(find "$SRC" -name '*.thrift' -type f -print0)

# Emit legacy-style compatibility shims alongside each generated
# thrift_types.py — TAAC code uses both `thrift_types` (new) and
# `types` / `ttypes` (legacy). Same logic the cmake `install(CODE ...)`
# block in thrift/CMakeLists.txt runs at install time.
while IFS= read -r -d '' f; do
    dir=$(dirname "$f")
    echo 'from .thrift_types import *' > "$dir/types.py"
    echo 'from .thrift_types import *' > "$dir/ttypes.py"
done < <(find "$OUT/gen-python" -name 'thrift_types.py' -print0)

while IFS= read -r -d '' f; do
    dir=$(dirname "$f")
    echo 'from .thrift_clients import *' > "$dir/clients.py"
done < <(find "$OUT/gen-python" -name 'thrift_clients.py' -print0)

echo "Regenerated $count .thrift file(s) → $OUT/gen-python/"

if [[ "$QUIET" -eq 0 ]]; then
    echo ""
    echo "To pick them up, prepend the regen tree to PYTHONPATH:"
    echo "  export PYTHONPATH=$OUT/gen-python:\$PYTHONPATH"
    echo ""
    echo "If your workspace is bind-mounted at e.g. /workspace, prepend it too"
    echo "so edited TAAC .py source overrides the baked-in install tree:"
    echo "  export PYTHONPATH=/workspace:$OUT/gen-python:\$PYTHONPATH"
fi
