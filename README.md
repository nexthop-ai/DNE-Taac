# DNE-Taac

Test As A Config (TAAC) — a configuration-driven network test automation framework. TAAC provides a declarative approach to FBOSS network device testing, where test scenarios are expressed as structured configurations rather than imperative scripts.

## Quick start

Tested on Ubuntu 24.04.

### System dependencies

```bash
sudo apt-get install -y \
    git cmake ninja-build g++ python3 python3-dev python3-pip \
    libssl-dev libdouble-conversion-dev libgflags-dev libgoogle-glog-dev \
    libboost-all-dev libevent-dev libsodium-dev zlib1g-dev libzstd-dev \
    liblz4-dev libsnappy-dev liblzma-dev libdwarf-dev libunwind-dev \
    libiberty-dev libaio-dev cython3 autoconf automake libtool pkg-config \
    bison flex curl ca-certificates patchelf

# auditwheel is invoked by the fbthrift-python wheel build step
sudo pip3 install --break-system-packages auditwheel
```

### Build

```bash
# One-time bootstrap of build/fbcode_builder/
./scripts/setup_getdeps.sh

# Build TAAC + transitive thrift bindings (--scratch-path for cache reuse)
python3 build/fbcode_builder/getdeps.py \
    --scratch-path ~/.taac-build-scratch \
    --allow-system-packages build --no-tests taac
```

First build takes 30–60 min (folly + fizz + wangle + mvfst + fbthrift compile from source). Subsequent builds reuse the persistent install cache under the scratch directory.

## Outputs

After `getdeps.py build` completes, generated thrift bindings + the TAAC Python source land under:

```
<scratch-path>/installed/taac-<HASH>/lib/python3/site-packages/
```

containing `taac/`, `ixia/`, `neteng/`, `facebook/`, `fb303/`. Each generated `thrift_types.py` ships a co-located `types.py` / `ttypes.py` / `clients.py` shim so legacy-style imports resolve.

## Using the bindings

The fbthrift Python runtime is built by getdeps as a wheel; install it:

```bash
pip3 install --break-system-packages --no-index \
    --find-links <scratch-path>/installed/fbthrift-python/share/thrift/wheels thrift
pip3 install --break-system-packages -r requirements.txt
```

Set `PYTHONPATH` to the install prefix and `LD_LIBRARY_PATH` to the native lib search path:

```bash
export PYTHONPATH=<scratch-path>/installed/taac-<HASH>/lib/python3/site-packages
export LD_LIBRARY_PATH=$(find <scratch-path>/installed -maxdepth 2 -type d -name lib | tr '\n' ':')
```

Then:

```python
from neteng.fboss.ctrl.thrift_types import NdpEntryThrift
from taac.test_as_a_config.thrift_types import TestConfig
```

The `<HASH>` suffix is getdeps' per-configuration cache key — it changes if you pass different `--extra-cmake-defines` to `getdeps.py build`.

## License

This project is licensed under the Apache License 2.0 — see the [LICENSE](LICENSE) file for details.
