# `docker/` — Docker build stack

## Files

| File | Purpose |
|---|---|
| `run-fboss-docker.sh` | Wrapper script. Builds FBOSS's public base image and offers subcommands (`build-base`, `getdeps-build`, `shell`, `run`, `build-taac-image`). Entry point for everything below. |
| `Dockerfile.fbthrift` | **Pipeline 1** dockerfile — builds only the fbthrift install tree (fbthrift-python + fboss-thrift-defs + transitive deps) and emits it as a tarball baked into a `FROM scratch` stage. Driven by `scripts/taac-cache-build.sh`; consumed by the cache-publish workflow. |
| `Dockerfile.taac` | **Pipeline 2** dockerfile — multi-stage recipe for the vendor-shippable derived image (`fboss-taac:<distro>`). Stage 1 (builder) restores the Pipeline 1 tarball if present (or falls through to a full source build on cache miss / `--no-cache`), then builds TAAC and prunes compile-time artifacts; Stage 2 (runtime) uses the **same** `fboss-build-env` base for a single ABI surface across build and run, with selective `COPY --from=builder` to pull in just the pruned install tree and Python site-packages. |
| `taac-entrypoint.sh` | `ENTRYPOINT` for the derived image. Resolves the per-config install hash + native lib paths and exports `PYTHONPATH` / `LD_LIBRARY_PATH` / `TAAC_OSS` before exec'ing the user command. |
| `taac-regen-thrift.sh` | Installed as `/usr/local/bin/taac-regen-thrift` inside the derived image. Regenerates TAAC's Python thrift bindings from a bind-mounted workspace using the baked-in `thrift1` compiler + fbthrift annotation headers + FBOSS schema tree. Enables "pull image, edit thrift on host, run in container" iteration without rebuilding the image. |

## Pipelines overview

Two independent pipelines share `fboss-build-env:<distro>` as their base and produce different artifacts:

```
                FBOSS public Dockerfile
                        │
                        │  ./docker/run-fboss-docker.sh build-base
                        ▼
                fboss-build-env:<distro>           (shared base, ~4 GB)
                        │
            ┌───────────┴────────────┐
            ▼                        ▼
       PIPELINE 1               PIPELINE 2
       (publish cache)          (build TAAC image)
       Dockerfile.fbthrift      Dockerfile.taac
       taac-cache-build.sh      run-fboss-docker.sh build-taac-image
            │                        │
            ▼                        │
       fbthrift-python-              │
       <sha>.tar.gz                  │
            │                        │
            ▼                        │
       configured                    │
       cache bucket                  │
            │                        │
            └──── cache restore  ────┤
                  (auto on           │
                   build-taac-image, │
                   bypass with       │
                   --no-cache or     │
                   --fbthrift-       │
                   tarball)          │
                                     ▼
                              fboss-taac:<distro>
                              (vendor-shippable, ~1.3 GB;
                               entrypoint + thrift1 baked in)
```

- **Pipeline 1** rebuilds the dep tree (fbthrift-python + fboss-thrift-defs + transitive) from source and uploads the tarball. Run nightly / on-demand whenever the fbthrift pin moves. See [First-build acceleration](#two-pipeline-split-fbthrift-install-tree-cache) below.
- **Pipeline 2** builds the vendor-shippable TAAC image. With cache hit, ~2-3 min; without (or with `--no-cache`), ~22 min cold. Run by every developer / vendor / CI consumer.

## Pipeline 2 internals (Dockerfile.taac)

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

## Two-pipeline split: fbthrift install-tree cache

The TAAC build is split into two independent pipelines:

- **Pipeline 1** (build & publish fbthrift compiler tarball) — produces an install-tree tarball at a configured cache URI. Dedicated [`Dockerfile.fbthrift`](Dockerfile.fbthrift). Run nightly / on-demand to keep the cache fresh.
- **Pipeline 2** (build TAAC environment) — consumes the cached tarball, builds TAAC source on top, produces the slim runtime image `fboss-taac:<distro>`. [`Dockerfile.taac`](Dockerfile.taac). Run by every developer / vendor.

On a fresh checkout or machine, building `fbthrift-python` + transitive C++ deps via getdeps is the dominant cost (~20 min). With the Pipeline 1 cache in place, Pipeline 2 restores the prebuilt tree and skips the heavy compile entirely — `build-taac-image` runs in ~2-3 min instead of ~22 min.

### Storage configuration

The cache scripts (`taac-cache-pull.sh`, `taac-cache-push.sh`, `taac-cache-build.sh`) read a single env var holding the full tarball URI; pull/push dispatch on URI scheme:

- `TAAC_CACHE_URI` — full URL of the tarball. Supported schemes:
    - `file:///abs/path/fbthrift-python-<rev>.tar.gz` (local, `cp`)
    - `ng://bucket/path/fbthrift-python-<rev>.tar.gz` (Nexthop bucket, `ng bucket get/put`)
    - `s3://bucket/path/fbthrift-python-<rev>.tar.gz` (AWS S3, `aws s3 cp`)
    - `https://host/path/fbthrift-python-<rev>.tar.gz` (static HTTPS, pull-only via `curl`)

The URI names the full object — the caller is responsible for encoding the manifest rev (or any other cache-key axis) into the URL.

Locally, set it in [`scripts/_cache-config.sh`](../scripts/_cache-config.sh.example) (gitignored — copy `_cache-config.sh.example` and fill in the value). In CI, set it via repo vars / secrets at job level. Without the config the cache scripts silently no-op and Pipeline 2 falls through to source build.

### Pipeline 1: build & publish

Manual (host or runner):

```bash
./scripts/taac-cache-build.sh --distro centos --push
```

What happens:

1. Reads the pinned rev from [`getdeps/manifests/fbthrift-python`](../getdeps/manifests/fbthrift-python) (single source of truth for the cache key).
2. Runs `docker buildx build -f docker/Dockerfile.fbthrift --target export --output type=local,dest=.fbthrift-cache .` — the Dockerfile builds fbthrift-python + fboss-thrift-defs from source via getdeps and bakes the tarball at build time. The `export` stage (`FROM scratch`) holds only the tarball + rev marker.
3. `docker buildx` writes the tarball directly to `.fbthrift-cache/fbthrift-python-<sha>.tar.gz` on the host.
4. `--push` uploads to `$TAAC_CACHE_URI` via the scheme's backend tool.

CI: [`.github/workflows/cache-publish.yml`](../.github/workflows/cache-publish.yml) runs `taac-cache-build.sh --push` on a self-hosted runner. Currently `workflow_dispatch`-only — fire it from the Actions tab when the pin gets bumped. Once validated, the trigger can flip to `push: branches: [main]` for auto-publish on every main merge.

### Pipeline 2: build the TAAC image (cache consumer)

The standard `build-taac-image` path. The host wrapper auto-resolves the cache:

```bash
./docker/run-fboss-docker.sh --distro centos build-taac-image
```

What happens:

1. [`run-fboss-docker.sh`](run-fboss-docker.sh) invokes [`scripts/taac-cache-pull.sh`](../scripts/taac-cache-pull.sh) on the host before docker build. The script reads `$TAAC_CACHE_URI` and fetches it into `.fbthrift-cache/` under the URI's basename via the scheme's backend tool; exits 0 either way. A URI change auto-prunes any stale tarball with a different basename. If storage isn't configured, the cache silently no-ops and Layer B falls through to the source build.
2. `Dockerfile.taac` Layer A2 COPYs `.fbthrift-cache/` in and, if a tarball is present (globbing `*.tar.gz` — the filename is opaque from this layer), extracts it into `/scratch/installed/` and writes a sentinel file `/scratch/.cache-hit`. Layer B detects the sentinel and **skips the getdeps invocation entirely**, trusting the restored install tree. Layer F (TAAC's own build) uses `--no-deps` so it doesn't re-assess transitive deps either.
3. **Cache miss / `--no-cache`**: no sentinel, Layer B does the full source build inline (~22 min). Layer F's `--no-deps` still applies — the deps are valid either way.

The "skip entirely" strategy (vs. "let getdeps verify the install tree") avoids a subtle issue: getdeps's `GitFetcher.update()` re-clones source into `/scratch/repos/` when missing and sets `sources_changed=True`, which forces a full rebuild even with a valid install tree. Skipping at the layer boundary sidesteps this — we own the cache trust decision, not getdeps.

### Alternative: publish from a local named volume

Pipeline 1 builds fbthrift in a fresh docker context — clean, reproducible, CI-friendly. For local dev when you've already done a `run-fboss-docker.sh getdeps-build` (which populates the `fboss-scratch-<distro>` named volume) and want to publish that specific build without re-running getdeps, use [`scripts/taac-cache-push.sh`](../scripts/taac-cache-push.sh) `--distro <d>`. It tars from the named volume and uploads to `$TAAC_CACHE_URI`.

### Explicit cache input: `--fbthrift-tarball <path>`

By default, `build-taac-image` auto-resolves the cache by pulling from the bucket keyed on the current rev pin. For cases where you want to supply an explicit tarball instead — offline builds, debugging against a custom-built compiler, peer-to-peer sharing without going through the bucket — pass `--fbthrift-tarball <path>`:

```bash
./docker/run-fboss-docker.sh --distro centos \
    --fbthrift-tarball /tmp/my-fbthrift-python.tar.gz \
    build-taac-image
```

The wrapper copies the file into `.fbthrift-cache/` as `fbthrift-python-<rev>.tar.gz` (using the current pin's rev) and Dockerfile.taac's Layer A2 treats it like any other cache hit. Tarball contents are trusted blindly — getdeps's freshness contract isn't consulted, so if the tarball was built against a different manifest set, you may get a broken image. Use when you know what's in the file.

Mutually exclusive with `--no-cache`. The three modes are:

| Mode | Source of /scratch/installed | When to use |
|---|---|---|
| (default) | S3 bucket via cache-pull | Normal builds — auto, transparent |
| `--no-cache` | Source build inline | Validating cold path, debugging the cache itself |
| `--fbthrift-tarball <path>` | Local file | Offline, debugging, peer-to-peer |

### Explicit workspace input: `--workspace=main`

The default docker build context is the local working copy. For local debugging where you want to verify `main` is buildable without your in-progress changes, pass `--workspace=main`:

```bash
./docker/run-fboss-docker.sh --distro centos --workspace=main build-taac-image
```

The wrapper shallow-clones main from `github.com/nexthop-ai/private-DNE-Taac` into a temp dir and uses that as the docker build context. Cache resolution (cache-pull or `--fbthrift-tarball` or `--no-cache`) runs against the cloned tree's manifest pin, so the build is fully deterministic against main.

Combines freely with `--no-cache` and `--fbthrift-tarball` — pick the workspace independently of the cache input. Today only `main` is supported; arbitrary refs would be a small extension.

**For CI / nightly publish (Pipeline 1)**: `--workspace=main` isn't needed explicitly — `cache-publish.yml`'s `actions/checkout@v6` step (with no `ref:` specified) checks out the default branch by default when triggered manually via `workflow_dispatch`. So Pipeline 1's CI run automatically builds against `main`, which is what the build/runtime spec calls for ("if local workspace unspecified, clones from main"). The `--workspace=main` flag remains for the local-debug-of-main case.

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
