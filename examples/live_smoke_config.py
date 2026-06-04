"""TestConfig for the OSS live-device smoke.

A minimal TAAC test configuration that VP1's oss_entry_point can load,
used by examples/smoke_live_device.py and as a working example of a
test_configs file passed via `--test-configs`.

Two playbooks:
  - dummy_playbook:  a DUMMY_STEP, exercises the runner's plumbing.
  - ssh_playbook:    a RUN_SSH_COMMAND_STEP that runs `uname -a` on each
                     DUT, exercising the SSH driver path.

DUTs are supplied at run time via oss_entry_point's `--dut` flag — this
file leaves `endpoints` empty. Per-host OS resolution is driven by the
OSS topology loader from TAAC_DEVICE_INFO_PATH (a device_info.csv).
"""

import json

from taac.test_as_a_config.thrift_types import (
    Params,
    Playbook,
    Stage,
    Step,
    StepName,
    TestConfig,
)


test_config = TestConfig(
    name="live_smoke",
    basset_pool="",  # Meta-internal hardware reservation pool; "" for OSS.
    playbooks=[
        Playbook(
            name="dummy_playbook",
            stages=[Stage(steps=[Step(name=StepName.DUMMY_STEP)])],
        ),
        Playbook(
            name="ssh_playbook",
            stages=[
                Stage(
                    steps=[
                        Step(
                            name=StepName.RUN_SSH_COMMAND_STEP,
                            step_params=Params(
                                json_params=json.dumps(
                                    {"cmd": "uname -a", "log_output": True}
                                )
                            ),
                        )
                    ]
                )
            ],
        ),
    ],
    endpoints=[],          # Populated at run time from oss_entry_point --dut.
    host_os_type_map={},   # Resolved from TAAC_DEVICE_INFO_PATH.
    startup_checks=[],
)
