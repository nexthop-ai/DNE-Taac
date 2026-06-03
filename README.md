# DNE-Taac

Test As A Config (TAAC) — a configuration-driven network test automation framework. TAAC provides a declarative approach to FBOSS network device testing, where test scenarios are expressed as structured configurations rather than imperative scripts.

## Quick start

Smoke-tested via [facebook/fboss](https://github.com/facebook/fboss)'s public Docker images on **CentOS Stream 9**. Docker is the only host-side dependency.

```bash
# Build the vendor-shippable TAAC image (auto-builds base image if missing)
./docker/build-taac-image.sh
```

That single command builds the FBOSS CentOS base image if missing, compiles the full dep tree (folly, fizz, wangle, mvfst, fbthrift), builds TAAC, and produces `fboss-taac` — a self-contained image with all transitive deps baked in.

The image's entrypoint sets `PYTHONPATH` and `LD_LIBRARY_PATH` automatically, so vendors can `docker run --rm fboss-taac python3 ...` with no host-side state. See [`docker/README.md`](docker/README.md) for the build-flow diagram and layer-cache contract.

For iterative work on TAAC source or thrift schemas in a bind-mounted workspace — no image rebuild required — see the in-container iteration section in [`docker/README.md`](docker/README.md) (Python source edits work via `PYTHONPATH`; thrift edits use the baked-in `taac-regen-thrift` helper).

### Build cost

First build takes ~22 min cold (mostly the deps compile). Docker's layer cache makes subsequent rebuilds after TAAC-only source changes finish in ~30 sec. See [`docker/README.md`](docker/README.md) for the layer cache contract and when to rebuild what.

## Outputs

Inside the `fboss-taac` image, generated thrift bindings + the TAAC Python source land under:

```
/scratch/installed/taac-<HASH>/lib/python3/site-packages/
```

They contain `taac/`, `ixia/`, `neteng/`, `facebook/`, `fb303/`. Each generated `thrift_types.py` ships a co-located `types.py` / `ttypes.py` / `clients.py` shim so legacy-style imports resolve.

The `<HASH>` suffix is getdeps' per-configuration cache key — it changes if you pass different `--extra-cmake-defines` to `getdeps.py build`.

## Using the bindings

The image's entrypoint automatically sets `PYTHONPATH` and `LD_LIBRARY_PATH`, so imports work out of the box:

```bash
docker run --rm fboss-taac python3 -c '
    from neteng.fboss.ctrl.thrift_types import NdpEntryThrift
    from taac.test_as_a_config.thrift_types import TestConfig
    print("ok")
'
```

## Running TAAC modules under OSS

TAAC's Python modules (e.g. `taac.libs.taac_runner`) include Meta-internal imports that aren't shipped in this slice. Set `TAAC_OSS=1` so the imports take their OSS branch:

```bash
export TAAC_OSS=1
python3 -c 'import taac.libs.taac_runner; print("ok")'
```

Some runtime functionality is stubbed in OSS mode (NDS drainer, COOP patcher, ValidationStep, AristaSSHHelper, etc.) and will raise `NotImplementedError` if invoked on a code path that requires it. Imports succeed; trying to actually use those features fails.

## Running TAAC modules under OSS

TAAC's Python modules (e.g. `taac.libs.taac_runner`) include Meta-internal imports that aren't shipped in this slice. Set `TAAC_OSS=1` so the imports take their OSS branch:

```bash
export TAAC_OSS=1
python3 -c 'import taac.libs.taac_runner; print("ok")'
```

Some runtime functionality is stubbed in OSS mode (NDS drainer, COOP patcher, ValidationStep, AristaSSHHelper, etc.) and will raise `NotImplementedError` if invoked on a code path that requires it. Imports succeed; trying to actually use those features fails.

## License

This project is licensed under the Apache License 2.0 — see the [LICENSE](LICENSE) file for details.
