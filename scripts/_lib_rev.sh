# Shared helper for parsing the `rev = <sha>` pin out of a getdeps
# manifest. Sourced (not executed) by host-side scripts that need to
# read the pinned fbthrift-python revision — avoids duplicating the
# same grep/awk/tr pipeline.
#
# Note: this file is intentionally NOT executable and starts with no
# shebang. Source it from bash:
#
#   source "$SCRIPT_DIR/_lib_rev.sh"
#   REV=$(get_fbthrift_rev "$MANIFEST_PATH")
#   if [[ -z "$REV" ]]; then ...caller-specific error handling... fi
#
# Returns the rev string on stdout, or empty string if the file is
# missing or has no matching line. Callers do their own error
# handling — different consumers want different behavior (cache-pull
# silently falls through on a missing pin; cache-push and
# setup_getdeps fail loud).
#
# The Dockerfile RUN steps in Dockerfile.taac (Layer A2) and
# Dockerfile.fbthrift inline the same grep pipeline directly rather
# than sourcing this file — they don't have access to the host
# filesystem at the right time. Keep the inline pipeline in those
# Dockerfiles in sync with the one below if either ever needs to
# change.

get_fbthrift_rev() {
    grep -E '^rev[[:space:]]*=' "$1" 2>/dev/null \
        | head -1 \
        | awk -F'=' '{print $2}' \
        | tr -d ' '
}
