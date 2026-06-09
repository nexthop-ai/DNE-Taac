#!/bin/bash
# Configure dockerd so BuildKit doesn't truncate per-step log scrollback.
#
# BuildKit caps each RUN step's daemon-side log buffer at 1 MiB by
# default. On long-running steps (e.g. the fbthrift + fboss-thrift-defs
# compile), an early failure — cc1plus OOM-kill, compile error,
# auditwheel hiccup — scrolls off and you're left with a generic
# "exit code 1" at the tail. BUILDKIT_STEP_LOG_MAX_SIZE=-1 removes
# the cap.
#
# The env var is read by buildkitd (the BuildKit daemon), not by the
# `docker build` client. For Docker's embedded BuildKit, that means
# the env has to live in dockerd's own environment — a systemd
# Environment= entry. Setting it on the client (e.g. in
# docker/build-taac-image.sh) is best-effort: some Docker versions
# propagate the var into the embedded BuildKit; others don't.
#
# Run with sudo. One-time host setup; idempotent.

set -euo pipefail

if [[ $EUID -ne 0 ]]; then
    echo "Run with sudo." >&2
    exit 1
fi

OVERRIDE_DIR=/etc/systemd/system/docker.service.d
OVERRIDE_FILE="$OVERRIDE_DIR/buildkit-log-cap.conf"

mkdir -p "$OVERRIDE_DIR"
cat > "$OVERRIDE_FILE" <<'EOF'
[Service]
Environment=BUILDKIT_STEP_LOG_MAX_SIZE=-1
EOF

systemctl daemon-reload
systemctl restart docker

echo "Wrote $OVERRIDE_FILE"
echo "Restarted docker.service with BUILDKIT_STEP_LOG_MAX_SIZE=-1"
