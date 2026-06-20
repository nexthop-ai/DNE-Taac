# Copyright (c) Meta Platforms, Inc. and affiliates.

# pyre-unsafe

import json

from taac.testconfigs.configerator.speed_flip_helper import (
    create_speed_flip_test_cases,
)
from taac.health_check.health_check import types as hc_thrift
from taac.test_as_a_config import types as taac_thrift

SPEED_FLIP_PORTS = [
    "eth4/5/1",
    "eth6/5/1",
]

test_config = taac_thrift.TestConfig(
    name="SPEED_FLIP_DARWIN_FUJI_QZA1",
    basset_pool="dne.test",
    endpoints=[
        taac_thrift.Endpoint(
            name="rsw004.p004.f01.qza1",
        ),
        taac_thrift.Endpoint(
            name="fsw003.p004.f01.qza1",
            dut=True,
        ),
    ],
    postchecks=[
        taac_thrift.PointInTimeHealthCheck(
            name=hc_thrift.CheckName.UNCLEAN_EXIT_CHECK,
            check_params=taac_thrift.Params(
                jq_params={
                    "start_time": ".test_case_start_time",
                }
            ),
        ),
    ],
    snapshot_checks=[
        taac_thrift.SnapshotHealthCheck(name=hc_thrift.CheckName.CORE_DUMPS_CHECK),
    ],
    playbooks=[
        *create_speed_flip_test_cases(
            speed_flip_ports=SPEED_FLIP_PORTS,
            original_speed=200,
            new_speed=400,
        )
    ],
)

TEST_CONFIG = test_config
