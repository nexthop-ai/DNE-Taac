# DNE-Taac

Test As A Config (TAAC) — a configuration-driven network test automation framework.

## Overview

TAAC provides a declarative approach to network device testing, where test scenarios
are expressed as structured configurations rather than imperative scripts.

## Getting Started

See the [documentation](https://github.com/facebook/DNE-Taac) for setup instructions.

### Driving a minimal test

```python
import asyncio
from taac.test_as_a_config.thrift_types import (
    TestConfig, Playbook, Stage, Step, StepName, Endpoint, DeviceOsType,
)
from taac.libs.taac_runner import TaacRunner

cfg = TestConfig(
    name='smoke',
    basset_pool='',
    playbooks=[Playbook(
        name='dummy_playbook',
        stages=[Stage(steps=[Step(name=StepName.DUMMY_STEP)])],
    )],
    endpoints=[Endpoint(name='your-host', dut=True)],
    host_os_type_map={'your-host': DeviceOsType.FBOSS},
    startup_checks=[],
)

# skip_post_setup_wait skips a 180s interface-stabilization sleep
# that's only useful when booting real hardware.
async def main():
    runner = TaacRunner(test_config=cfg, skip_post_setup_wait=True)
    await runner.async_test_setUp()
    await runner.run_tests()

asyncio.run(main())
```

### Plugging in a custom driver

`DEVICE_OS_DRIVER_CLASS_MAP` ships with `FbossSwitch` registered for `DeviceOsType.FBOSS`. For other OS types (Arista, Cisco, etc.), register your own `AbstractSwitch` subclass:

```python
from taac.utils.driver_factory import register_driver_class
from taac.test_as_a_config.thrift_types import DeviceOsType
from my_pkg.my_driver import MyArista  # your subclass of AbstractSwitch

register_driver_class(DeviceOsType.ARISTA_OS, MyArista)
```

## License

This project is licensed under the Apache License 2.0 — see the [LICENSE](LICENSE) file for details.
