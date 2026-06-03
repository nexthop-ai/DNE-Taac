# `docker/` — Docker build stack

## Files

| File | Purpose |
|---|---|
| `run-fboss-docker.sh` | Wrapper script. Builds FBOSS's public base image and offers subcommands (`build-base`, `getdeps-build`, `shell`, `run`, `build-taac-image`). Entry point for everything below. |
| `Dockerfile.taac` | Multi-stage recipe for the vendor-shippable derived image (`fboss-taac:<distro>`). Stage 1 (builder) uses `fboss-build-env` to compile TAAC + transitive deps and prune compile-time-only artifacts; Stage 2 (runtime) uses the **same** `fboss-build-env` base for a single ABI surface across build and run, with selective `COPY --from=builder` to pull in just the pruned install tree and Python site-packages. |
| `taac-entrypoint.sh` | `ENTRYPOINT` for the derived image. Resolves the per-config install hash + native lib paths and exports `PYTHONPATH` / `LD_LIBRARY_PATH` / `TAAC_OSS` before exec'ing the user command. |
| `taac-regen-thrift.sh` | Installed as `/usr/local/bin/taac-regen-thrift` inside the derived image. Regenerates TAAC's Python thrift bindings from a bind-mounted workspace using the baked-in `thrift1` compiler + fbthrift annotation headers + FBOSS schema tree. Enables "pull image, edit thrift on host, run in container" iteration without rebuilding the image. |

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
        │  compile-time-only artifacts (static .a archives, duplicate
        │  .so, cmake configs, most include/ subdirs, pkgconfig,
        │  wheelhouses; strip .so debug symbols).
        │  KEEPS thrift1, fbthrift annotation includes, and the FBOSS
        │  thrift schema tree so the runtime image can regenerate
        │  Python bindings in-place via taac-regen-thrift.
        ▼
[builder stage]                       (intermediate, not tagged)
        │
        │  Stage 2 (runtime) in Dockerfile.taac, FROM fboss-build-env
        │  (same base as Stage 1 — single ABI surface, no separate dnf
        │  install needed). Selectively COPY --from=builder the pruned
        │  install tree, Python site-packages, and taac-regen-thrift
        │  helper.
        │
        │  ./docker/run-fboss-docker.sh build-taac-image
        ▼
fboss-taac:<distro>                    (vendor-shippable, ~1.3 GB; entrypoint + thrift1 baked in)
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
| `docker/Dockerfile.taac` itself | Depends which line moves; usually just the modified layer onward | seconds–minutes |
| `docker/taac-entrypoint.sh` | Final two runtime layers only | ~1 sec |

The `getdeps-build` subcommand (separate from `build-taac-image`) instead writes to a docker-managed scratch volume (`fboss-scratch-<distro>`) — that workflow is for contributors iterating on the TAAC source itself; `build-taac-image` is for producing the artifact.

## First-build acceleration: fbthrift install-tree cache

On a fresh checkout or machine, building `fbthrift-python` + transitive C++ deps via getdeps is the dominant cost (~20 min). To avoid every developer paying that on their first `build-taac-image`, the builder stage pulls a prebuilt install-tree tarball from a configured cache URI (local, Nexthop bucket, S3, or static HTTPS).

### How it works

1. [`getdeps/manifests/fbthrift-python`](../getdeps/manifests/fbthrift-python) pins fbthrift to a specific upstream SHA via the `[git] rev = ...` field. The bootstrap clone in `setup_getdeps.sh` and getdeps' own checkout derive from this pin. The cache `TAAC_CACHE_URI` is set externally — the operator is responsible for matching it to the current pin (the upload step typically encodes the rev in the URL).

2. **Pull (auto, on `build-taac-image`)**: [`run-fboss-docker.sh`](run-fboss-docker.sh) invokes [`scripts/taac-cache-pull.sh`](../scripts/taac-cache-pull.sh) on the host before docker build. The script reads `TAAC_CACHE_URI` (the full URL of the tarball — `file://`, `ng://`, `s3://`, or `https://`) and fetches it into `.fbthrift-cache/` under the URI's basename; exits 0 either way. A URI change auto-prunes any stale tarball with a different basename. `TAAC_CACHE_URI` comes from `scripts/_cache-config.sh` (gitignored) — see `scripts/_cache-config.sh.example`. Without the config the cache silently no-ops.

3. **Restore (in docker build, Layer A2)**: `Dockerfile.taac` COPYs `.fbthrift-cache/` in and, if a tarball is present (globbing `*.tar.gz` since the filename is opaque), extracts it into `/scratch/installed/` and writes a sentinel file `/scratch/.cache-hit`. Layer B detects the sentinel and **skips the getdeps invocation entirely**, trusting the restored install tree. Layer F (TAAC's own build) uses `--no-deps` so it doesn't re-assess transitive deps either.

   The "skip entirely" strategy (vs. "let getdeps verify the install tree") avoids a subtle issue: getdeps's `GitFetcher.update()` re-clones source into `/scratch/repos/` when missing and sets `sources_changed=True`, which forces a full rebuild even with a valid install tree. Skipping at the layer boundary sidesteps this — we own the cache trust decision, not getdeps.

4. **Push (manual)**: After a successful build via `run-fboss-docker.sh getdeps-build`, run [`scripts/taac-cache-push.sh`](../scripts/taac-cache-push.sh) `--distro <d>` to publish the resulting install tree to `TAAC_CACHE_URI`. Caller is responsible for setting `TAAC_CACHE_URI` to the destination URL appropriate for the current rev (e.g. `ng://vol-shared/fboss/taac/fbthrift-python-<sha>.tar.gz`), so the next developer's pull from the same URI hits.

### What's cached

Everything under `/scratch/installed/` except `taac-*` (TAAC's own build is fast and source-dependent). That covers folly, fizz, wangle, mvfst, fbthrift, fbthrift-python, fboss-thrift-defs, and all their transitive deps — anything that would otherwise rebuild when `getdeps/manifests/*` or `scripts/setup_getdeps.sh` changes.

### Cache miss semantics

Anything that would interrupt a smooth cache hit — unset `TAAC_CACHE_URI`, network failure, the scheme's CLI missing on the host (e.g. `ng` for `ng://`, `aws` for `s3://`), 404 from the URL, corrupt tarball — falls through to the normal source build. No build fails because of a cache miss; the cache is strictly an optimization.

### Bumping the fbthrift pin

Edit the `rev = ...` line in `getdeps/manifests/fbthrift-python` and commit. `setup_getdeps.sh` will clone the bootstrap tooling at the matching SHA. To re-hit the cache after a pin bump, also update `TAAC_CACHE_URI` to point at a tarball built at the new SHA — until that's done (or someone runs `taac-cache-push.sh` to publish one), builds fall through to a one-time source rebuild.

We pin `fbthrift-python` rather than `fbthrift` because `fbthrift-python` is the actual getdeps build target Layer B uses — the two are separate upstream manifests, and `fbthrift-python` doesn't transitively depend on `fbthrift`. Pinning `fbthrift` would silently no-op.

## In-container iteration

After pulling the derived image, local edits to TAAC source or thrift schemas in a bind-mounted workspace can be picked up by the running container without rebuilding the image.

### Python source edits

Edited `.py` files (e.g. `taac/libs/taac_runner.py`, anything in `taac/runner/`, `examples/`) are picked up by bind-mounting the workspace and prepending it to `PYTHONPATH`:

```bash
docker run --rm --network host \
    -v "$PWD":/workspace:ro \
    fboss-taac:centos \
    bash -c '
        export PYTHONPATH=/workspace:$PYTHONPATH
        python3 /workspace/examples/smoke_live_device.py ...
    '
```

The image's entrypoint pre-sets `PYTHONPATH` to point at the baked-in install tree. Prepending `/workspace` makes Python prefer the workspace's `taac/` for any module — e.g. `from taac.libs.taac_runner import TaacRunner` loads `/workspace/taac/libs/taac_runner.py` instead of the baked-in copy. No regen, no helper.

### Thrift schema edits

Edited `.thrift` files need their Python bindings regenerated first. Use the baked-in `taac-regen-thrift` helper:

```bash
docker run --rm --network host \
    -v "$PWD":/workspace:ro \
    fboss-taac:centos \
    bash -c '
        taac-regen-thrift /workspace/thrift /tmp/regen
        export PYTHONPATH=/workspace:/tmp/regen/gen-python:$PYTHONPATH
        python3 -m taac.runner.oss_entry_point --test-configs ... --dut ...
    '
```

`taac-regen-thrift` wraps `thrift1 --gen mstch_python` with the right `-I` paths (the workspace's `thrift/`, the FBOSS thrift schema tree at `/scratch/installed/fboss-thrift-defs-*/`, and the fbthrift annotation includes at `/scratch/installed/fbthrift-python/include/`). After codegen it also emits the legacy `types.py` / `ttypes.py` / `clients.py` shims (`from .thrift_types import *`) that TAAC's older import sites still use — same logic the `install(CODE ...)` block in `thrift/CMakeLists.txt` runs at install time.

### How the overlay works

Python's namespace-package mechanism merges three contributors under `taac.__path__` (and friends):

  1. `/workspace` — bind-mounted source, overlays edited `.py` files
  2. `/tmp/regen/gen-python` — regenerated thrift bindings (only when `taac-regen-thrift` is run)
  3. `/scratch/installed/taac-*/lib/python3/site-packages/` — baked-in install tree (fallback for unchanged modules)

So source edits AND regenerated bindings both override the baked-in versions; everything else falls through to the image.

## Where to look for details

- **Multi-stage layout + layer cache contract**: header comment in [`Dockerfile.taac`](Dockerfile.taac) — describes both the builder/runtime split and the volatility split inside the builder stage.
- **Entrypoint internals**: header in [`taac-entrypoint.sh`](taac-entrypoint.sh).
- **Wrapper subcommands**: header in [`run-fboss-docker.sh`](run-fboss-docker.sh) plus `--help`-style usage at the bottom.
- **End-user usage**: top-level [`README.md`](../README.md).
