# (c) Meta Platforms, Inc. and affiliates. Confidential and proprietary.

# pyre-unsafe

"""Shared constants and device lists for FPF hardening test configs.

All FPF hardening test configs (TC2-TC33) import from this module to keep
device hostnames, prefix counts, and timing parameters in one place.
"""

from taac.test_as_a_config.types import Endpoint

TRIGGER_STSWS = [
    "stsw001.s001.l202.mwg2",
    "stsw001.s002.l202.mwg2",
]

OBSERVER_GTSWS = [
    "gtsw001.l1002.c087.mwg2",
    "gtsw002.l1002.c087.mwg2",
]

GPU_HOSTS = [
    "rtptest1544.mwg2",
    "rtptest1543.mwg2",
]

HARDENING_PREFIX_COUNT = 70000
DEFAULT_STABILIZATION_SEC = 600
DEFAULT_BASELINE_DELAY_SEC = 120
DEFAULT_RECOVERY_WAIT_SEC = 300
DEFAULT_SUBNET_PREFIX = "5000:dd::/32"
DEFAULT_COMMUNITY_LIST = "stsw"
FPF_SERVICES = ["bgpd", "fsdb", "wedge_agent", "qsfp_service"]
DEFAULT_LANES = [0, 1]
DEFAULT_REMOTE_FAILURE_LANES = [0, 1, 2, 3]
REMOTE_FAILURE_SUBNET = "5000:dd::/32"
DRAIN_CONVERGENCE_SLA_SEC = 120


def create_fpf_endpoints() -> list[Endpoint]:
    return [
        Endpoint(name=OBSERVER_GTSWS[0], dut=True),
        Endpoint(name=OBSERVER_GTSWS[1]),
        *[Endpoint(name=stsw) for stsw in TRIGGER_STSWS],
    ]
