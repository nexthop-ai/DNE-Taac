# `docker/` — Docker build stack

## Files

| File | Purpose |
|---|---|
| `build-taac-image.sh` | Entry point. Builds `fboss-taac` from `Dockerfile.taac`. Auto-builds the FBOSS base image if missing. |
| `Dockerfile.taac` | Multi-stage dockerfile — builds fbthrift-python + fboss-thrift-defs + transitive deps + TAAC in a builder stage, then produces a slim CentOS Stream 9 runtime image. |
| `taac-entrypoint.sh` | `ENTRYPOINT` for `fboss-taac`. Resolves the per-config install hash + native lib paths and exports `PYTHONPATH` / `LD_LIBRARY_PATH` / `TAAC_OSS` before exec'ing the user command. |
| `taac-regen-thrift.sh` | Installed as `/usr/local/bin/taac-regen-thrift` inside the image. Regenerates Python thrift bindings from a bind-mounted workspace using the baked-in `thrift1` compiler. |
| `run_taac_docker.sh` | Developer wrapper. Shells into the container with workspace bind-mounted and `PYTHONPATH` pre-configured. `--regen` regenerates thrift bindings on entry. |

## Build flow

```
                FBOSS public Dockerfile
                        │
                        │  (auto-built if missing)
                        ▼
                fboss-build-env:centos              (shared base, ~4 GB)
                        │
                        ▼
                  Dockerfile.taac
                  build-taac-image.sh
                        │
                        ▼
                  fboss-taac
                  (vendor-shippable, ~1.3 GB)
```

The full build takes ~22 min cold (folly + fizz + wangle + mvfst + fbthrift compiled from source). Docker's layer cache makes subsequent rebuilds fast when only TAAC source changes.

## Usage

**Build the TAAC image:**

```bash
./docker/build-taac-image.sh
```

**Custom tag:**

```bash
./docker/build-taac-image.sh --tag my-taac:v1
```

## When to rebuild

Docker's layer cache keeps the heavy dep compile cached when only TAAC source changes:

| Change | What rebuilds | Approximate cost |
|---|---|---|
| TAAC source (`.py`, `.thrift`, etc.) | Builder layers C–E + runtime COPYs | ~30 sec |
| `requirements.txt` | Builder layers D–E + runtime COPYs | ~1-2 min |
| `getdeps/manifests/*` or `scripts/setup_getdeps.sh` | Entire builder + runtime | ~22 min |
| `docker/taac-entrypoint.sh` or `docker/taac-regen-thrift.sh` | Runtime `COPY . /taac` + `cp` layer | ~1 sec |

## Deps and the fbthrift pin

The pinned rev in [`getdeps/manifests/fbthrift-python`](../getdeps/manifests/fbthrift-python) (`rev = <sha>`) is the single source of truth. `setup_getdeps.sh` clones the matching fbthrift tooling at that SHA so the build infrastructure stays in lockstep with the dep versions.

**Bumping the pin:** edit the `rev = ...` line and commit. The next `build-taac-image.sh` run will rebuild the full dep tree.

## In-container iteration

After pulling the derived image, local edits to TAAC source or thrift schemas can be picked up by the running container without rebuilding the image. Use `run_taac_docker.sh`:

```bash
# Shell in with local source on PYTHONPATH (Python edits only)
./docker/run_taac_docker.sh

# Shell in + regenerate thrift bindings (for .thrift edits)
./docker/run_taac_docker.sh --regen

# Use a specific image
./docker/run_taac_docker.sh --image <image> --regen

# Run a one-shot command
./docker/run_taac_docker.sh run python3 -c 'import taac; print("ok")'
```

The wrapper bind-mounts the repo at `/workspace`, sets up `PYTHONPATH` so local source overrides baked-in modules, and (with `--regen`) regenerates thrift bindings automatically.

### How the overlay works

Python's namespace-package mechanism merges three contributors under `taac.__path__` (and friends):

  1. `/workspace` — bind-mounted source, overlays edited `.py` files
  2. `/tmp/regen/gen-python` — regenerated thrift bindings (only with `--regen`)
  3. `/scratch/installed/taac-*/lib/python3/site-packages/` — baked-in install tree (fallback for unchanged modules)

So source edits AND regenerated bindings both override the baked-in versions; everything else falls through to the image.

### Manual docker run

If you need more control than `run_taac_docker.sh` provides:

```bash
# Python source edits only
docker run --rm -it --network host \
    -v "$PWD":/workspace \
    fboss-taac \
    bash -c 'export PYTHONPATH=/workspace:$PYTHONPATH && exec bash'

# With thrift regen
docker run --rm -it --network host \
    -v "$PWD":/workspace \
    fboss-taac \
    bash -c 'taac-regen-thrift /workspace/thrift /tmp/regen && export PYTHONPATH=/workspace:/tmp/regen/gen-python:$PYTHONPATH && exec bash'
```

### How the overlay works

Python's namespace-package mechanism merges three contributors under `taac.__path__` (and friends):

  1. `/workspace` — bind-mounted source, overlays edited `.py` files
  2. `/tmp/regen/gen-python` — regenerated thrift bindings (only when `taac-regen-thrift` is run)
  3. `/scratch/installed/taac-*/lib/python3/site-packages/` — baked-in install tree (fallback for unchanged modules)

So source edits AND regenerated bindings both override the baked-in versions; everything else falls through to the image.

## Where to look for details

- **Multi-stage layout + layer cache contract**: header comment in [`Dockerfile.taac`](Dockerfile.taac).
- **Entrypoint internals**: header in [`taac-entrypoint.sh`](taac-entrypoint.sh).
- **Script usage**: header comment in [`build-taac-image.sh`](build-taac-image.sh).
- **End-user usage**: top-level [`README.md`](../README.md).
