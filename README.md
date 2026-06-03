# DNE-Taac

Test As A Config (TAAC) — a configuration-driven network test automation framework. TAAC provides a declarative approach to FBOSS network device testing, where test scenarios are expressed as structured configurations rather than imperative scripts.

## Quick start

Smoke-tested via [facebook/fboss](https://github.com/facebook/fboss)'s public Docker images on **CentOS Stream 9** and **Debian Bookworm**. Docker is the only host-side dependency.

```bash
# Build TAAC inside the FBOSS CentOS image (or --distro debian for Debian Bookworm)
./docker/run-fboss-docker.sh --distro centos getdeps-build
```

That single command does everything: shallow-clones fbthrift to seed `build/fbcode_builder/` if not already present, clones `facebook/fboss` for the Docker image build context, builds the Docker image (~10 min apt/dnf installs), then runs getdeps inside the container with this repo bind-mounted at `/taac` and a per-distro docker-managed named volume mounted at `/scratch` (default volume name `fboss-scratch-<distro>`). Subcommands: `build-base`, `shell`, `run <cmd>`, `getdeps-build`. Pass `--network host` before the subcommand for live-device runs that need internal-DNS hostnames.

### Build cost

First build takes 30–60 min — folly + fizz + wangle + mvfst + fbthrift are compiled from source. The expensive output is the install tree under `/scratch/installed/` inside the container (in the `fboss-scratch-<distro>` docker volume), not anything `setup_getdeps.sh` produces (that script just copies fbthrift's `build/fbcode_builder/` into the repo and is fast). getdeps caches the install tree per cmake-defines hash, so subsequent invocations against the same volume skip rebuilding unchanged dependencies and finish in seconds. For nightly / shared-CI use, the whole volume is the artifact: persist with `docker volume export` / re-import, or tar from a throwaway container.

## Outputs

After `getdeps-build` completes, generated thrift bindings + the TAAC Python source land under (container path):

```
/scratch/installed/taac-<HASH>/lib/python3/site-packages/
```

inside the `fboss-scratch-<distro>` docker volume. They contain `taac/`, `ixia/`, `neteng/`, `facebook/`, `fb303/`. Each generated `thrift_types.py` ships a co-located `types.py` / `ttypes.py` / `clients.py` shim so legacy-style imports resolve.

The `<HASH>` suffix is getdeps' per-configuration cache key — it changes if you pass different `--extra-cmake-defines` to `getdeps.py build`.

## Using the bindings

The bindings link against native libs that were compiled inside the build container, so the easiest way to use them is to run inside the same container. Drop into a shell:

```bash
./docker/run-fboss-docker.sh --distro centos shell
```

Inside the container, install the fbthrift Python runtime wheel and the project's pip deps, then point Python at the install prefix:

```bash
python3 -m pip install --break-system-packages --no-index \
    --find-links /scratch/installed/fbthrift-python/share/thrift/wheels thrift
python3 -m pip install --break-system-packages -r /taac/requirements.txt

export PYTHONPATH=/scratch/installed/taac-<HASH>/lib/python3/site-packages
export LD_LIBRARY_PATH=$(find /scratch/installed -maxdepth 2 -type d -name lib | tr '\n' ':')
```

Then:

```python
from neteng.fboss.ctrl.thrift_types import NdpEntryThrift
from taac.test_as_a_config.thrift_types import TestConfig
```

(Substitute `<HASH>` with the actual install-dir hash from `ls /scratch/installed/`.)

## Running TAAC modules under OSS

TAAC's Python modules (e.g. `taac.libs.taac_runner`) include Meta-internal imports that aren't shipped in this slice. Set `TAAC_OSS=1` so the imports take their OSS branch:

```bash
export TAAC_OSS=1
python3 -c 'import taac.libs.taac_runner; print("ok")'
```

Some runtime functionality is stubbed in OSS mode (NDS drainer, COOP patcher, ValidationStep, AristaSSHHelper, etc.) and will raise `NotImplementedError` if invoked on a code path that requires it. Imports succeed; trying to actually use those features fails.

## License

This project is licensed under the Apache License 2.0 — see the [LICENSE](LICENSE) file for details.
