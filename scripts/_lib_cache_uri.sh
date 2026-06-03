# Cache URI scheme dispatch. Sourced by taac-cache-pull.sh and
# taac-cache-push.sh. Caller supplies an absolute URI; helpers route
# to the right backend tool.
#
#   file:///path/to/tarball.tar.gz       cp
#   ng://bucket/path/tarball.tar.gz      ng bucket {get,put --mkdir}
#   s3://bucket/path/tarball.tar.gz      aws s3 cp
#   https://host/path/tarball.tar.gz     curl -fL -o   (pull-only)
#
# The URI points at the full tarball location (not a prefix). Callers
# that previously composed `<prefix>/<rev>.tar.gz` should set TAAC_CACHE_URI
# to the full URL themselves.

cache_uri_scheme() {
    case "$1" in
        file://*)  echo file ;;
        ng://*)    echo ng ;;
        s3://*)    echo s3 ;;
        https://*) echo https ;;
        http://*)  echo http ;;
        *) return 1 ;;
    esac
}

# Binary the scheme needs on PATH. Callers can `command -v` this to give
# a clean "tool missing" error rather than a cryptic spawn failure.
cache_uri_get_bin() {
    case "$(cache_uri_scheme "$1")" in
        file)       echo cp ;;
        ng)         echo ng ;;
        s3)         echo aws ;;
        http|https) echo curl ;;
        *) return 1 ;;
    esac
}

cache_uri_put_bin() {
    case "$(cache_uri_scheme "$1")" in
        file)       echo cp ;;
        ng)         echo ng ;;
        s3)         echo aws ;;
        http|https) return 1 ;;
        *) return 1 ;;
    esac
}

cache_uri_get() {
    local uri="$1" dst="$2"
    case "$(cache_uri_scheme "$uri")" in
        file)       cp "${uri#file://}" "$dst" ;;
        ng)         ng bucket get "${uri#ng://}" "$dst" ;;
        s3)         aws s3 cp "$uri" "$dst" ;;
        http|https) curl -fL -o "$dst" "$uri" ;;
        *) echo "cache: unrecognized URI scheme: $uri" >&2; return 2 ;;
    esac
}

cache_uri_put() {
    local src="$1" uri="$2"
    case "$(cache_uri_scheme "$uri")" in
        file)
            local dst="${uri#file://}"
            mkdir -p "$(dirname "$dst")" && cp "$src" "$dst"
            ;;
        ng)         ng bucket put --mkdir "$src" "${uri#ng://}" ;;
        s3)         aws s3 cp "$src" "$uri" ;;
        http|https) echo "cache: HTTPS/HTTP push not supported" >&2; return 2 ;;
        *) echo "cache: unrecognized URI scheme: $uri" >&2; return 2 ;;
    esac
}
