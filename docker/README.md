# `docker/` — Docker build stack

## Files

| File | Purpose |
|---|---|
| `run-fboss-docker.sh` | Wrapper script. Builds FBOSS's public base image and offers subcommands (`build-base`, `getdeps-build`, `shell`, `run`, `build-taac-image`). Entry point for everything below. |
| `Dockerfile.taac` | Multi-stage recipe for the vendor-shippable derived image (`fboss-taac:<distro>`). Stage 1 (builder) uses `fboss-build-env` to compile TAAC + transitive deps and prune compile-time-only artifacts; Stage 2 (runtime) uses a slim CentOS Stream 9 base with only the Python interpreter and the runtime system libs the compiled `.so` files dynamically need. |
| `taac-entrypoint.sh` | `ENTRYPOINT` for the derived image. Resolves the per-config install hash + native lib paths and exports `PYTHONPATH` / `LD_LIBRARY_PATH` / `TAAC_OSS` before exec'ing the user command. |

## Build flow

```
FBOSS public Dockerfile               (~/.taac-fboss-image-src/fboss/oss/docker/Dockerfile)
        │
        │  ./docker/run-fboss-docker.sh build-base
        ▼
fboss-build-env:<distro>              (FBOSS's open-source build environment, ~4 GB)
        │
        │  Stage 1 (builder) in Dockerfile.taac, via build-arg BASE.
        │  Runs the getdeps build + pip installs, then prunes
        │  compile-time-only artifacts (static archives, headers, cmake
        │  configs, thrift compiler, wheelhouses; strip .so debug symbols).
        ▼
[builder stage]                       (intermediate, not tagged)
        │
        │  Stage 2 (runtime) in Dockerfile.taac, FROM centos:stream9.
        │  Installs Python 3.12 + runtime system libs (via dnf, with
        │  EPEL + CRB enabled for libsodium / libdwarf / libunwind);
        │  selectively COPY --from=builder the pruned install tree and
        │  Python site-packages.
        │
        │  ./docker/run-fboss-docker.sh build-taac-image
        ▼
fboss-taac:<distro>                    (vendor-shippable, ~2.6 GB; entrypoint baked in)
```

`run-fboss-docker.sh` and `Dockerfile.taac` both default to `--distro centos` / `BASE=fboss-build-env:centos`. Pass `--distro debian` or `BASE=fboss-build-env:debian` for the Debian variant.

**Distro status (today):** the CentOS variant is fully working. The Debian variant builds, but won't run TAAC as-is — Debian Bookworm ships Python 3.11, while TAAC contains f-string syntax that requires Python 3.12+. FBOSS's CentOS Dockerfile installs 3.12 explicitly (via dnf); the Debian Dockerfile uses Bookworm's default. Either FBOSS bumps the Debian Dockerfile's Python or TAAC drops the 3.12-only syntax — until then, use CentOS at runtime.

## When to rebuild what

`Dockerfile.taac` is laid out so Docker's layer cache keeps the heavy work cached when only TAAC source changes. Roughly:

| Change | What rebuilds | Approximate cost |
|---|---|---|
| `getdeps/manifests/*` or `scripts/setup_getdeps.sh` | Builder Layer A onward: full deps compile (folly, fizz, wangle, mvfst, fbthrift) + cleanup + runtime stage COPYs | ~22 min |
| `requirements.txt` | Builder Layer E onward: pip install + TAAC build + cleanup + runtime stage COPYs | ~1-2 min |
| Any other TAAC source | Builder Layer D onward: COPY context + TAAC's own getdeps build (just thrift codegen + Python install) + cleanup + runtime stage COPYs | ~1-2 min |
| Runtime stage `dnf install` line | Runtime layer onward only (builder cached) | ~30 sec |
| `docker/Dockerfile.taac` itself | Depends which line moves; usually just the modified layer onward | seconds–minutes |
| `docker/taac-entrypoint.sh` | Final two runtime layers only | ~1 sec |

The `getdeps-build` subcommand (separate from `build-taac-image`) instead writes to a docker-managed scratch volume (`fboss-scratch-<distro>`) — that workflow is for contributors iterating on the TAAC source itself; `build-taac-image` is for producing the artifact.

## Where to look for details

- **Multi-stage layout + layer cache contract**: header comment in [`Dockerfile.taac`](Dockerfile.taac) — describes both the builder/runtime split and the volatility split inside the builder stage.
- **Entrypoint internals**: header in [`taac-entrypoint.sh`](taac-entrypoint.sh).
- **Wrapper subcommands**: header in [`run-fboss-docker.sh`](run-fboss-docker.sh) plus `--help`-style usage at the bottom.
- **End-user usage**: top-level [`README.md`](../README.md).
