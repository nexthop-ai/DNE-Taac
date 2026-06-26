# (c) Meta Platforms, Inc. and affiliates. Confidential and proprietary.

"""TC4: wedge_agent WARM BOOT on the DUT GTSW.

Warm boot = a plain ``systemctl restart`` of wedge_agent WITHOUT writing the
cold-boot file, so the agent restores its forwarding/DOCA state on restart (the
data plane is preserved across the bounce). This is the agent analogue of the
bgpd graceful restart (tc23): same steps, same playbook, same health checks,
same "tolerate a short dip during the restart then re-converge within SLA"
contract — the ONLY differences from tc27 (agent COLDBOOT) are
``create_cold_boot_file=False`` and the shorter graceful settle/SLA.

Expectation (per design, mirrors tc23):
  - HRT (bulk / remote-failure / prod-prefix / plane-status): NO churn — HRT is
    queried on the GPU host and a warm boot preserves the data plane.
  - FSDB ribMap: unchanged (fsdb is not restarted).
  - BGP RIB: the bgp thrift collector goes null/unresponsive for a few polls
    while the agent re-initializes (tolerated, not a failure); the BGP RIB must
    return to the expected prefix count within bgp_restart_reconverge_sla_sec of
    the recorded warm-boot moment.

Headless run restarts wedge_agent via SSH — kick off from a Kerberos-ticketed
terminal.

Usage:
  buck2 run neteng/netcastle:netcastle_taac -- \\
    --team taac --test-config fpf_tc04_wedge_agent_warmboot \\
    --dev --skip-basset-reservation --skip-testbed-isolation \\
    --debug --continue-on-precheck-failure --skip-fboss-rsyslog
"""

from taac.libs.fpf.fpf_prod_prefix_map import get_prefix
from taac.playbooks.playbook_definitions import (
    create_fpf_service_restart_playbook,
)
from taac.task_definitions import (
    create_fpf_inject_vf_groups_task,
    create_fpf_restart_service_task,
    create_fpf_start_collectors_task,
    create_fpf_stop_collectors_task,
    create_fpf_withdraw_vf_groups_task,
)
from taac.testconfigs.fpf.fpf_hardening_common import (
    ALL_LANES,
    ALL_STSWS,
    ALLOW_BASELINE_FAILURES,
    create_fpf_endpoints,
    DEFAULT_COMMUNITY_LIST,
    EXPECTED_FSDB_SESSION_COUNT,
    fpf_ib_traffic_tasks,
    fpf_rf_vf_groups,
    fpf_vf_injection_groups,
    FSDB_COLLECTOR_MODE,
    GPU_HOSTS,
    OBSERVER_GTSWS,
    skip_ssh_dependencies,
    SPRAY_HOSTS,
    VF_COLLECTOR_SUBNET,
    VF_GROUP_PREFIX_COUNT,
)
from taac.test_as_a_config import types as taac_types
from taac.test_as_a_config.types import TestConfig

# Prefixes injected on ALL 8 STSWs, split per VF group (VF1 5000:dd on s001-s004,
# VF2 5000:ee on s005-s008), via the fpf_inject_bgp_prefixes SETUP TASK — this
# netcastle run is fully self-contained. The fabric is VF-segregated (VF1 only on
# lanes 0-3, VF2 only on lanes 4-7), so each observer GTSW / lane sees only its
# own VF group's count: PREFIX_COUNT = VF_GROUP_PREFIX_COUNT. Collector subnet is
# 5000::/16 to count both groups.
INJECTION_GROUPS = fpf_vf_injection_groups()
RF_VF_GROUPS = fpf_rf_vf_groups()
PREFIX_COUNT = VF_GROUP_PREFIX_COUNT
INJECT_SETTLE_SEC = 120
INJECTED_LANES = ALL_LANES
TRIGGER_STSWS = ALL_STSWS
PROD_PREFIX_HOST = GPU_HOSTS[0]
PROD_PREFIXES = [get_prefix(PROD_PREFIX_HOST, 0)]
HRT_MEMORY_HOSTS = ["rtptest1544.mwg2", "rtptest1575.mwg2"]
DUT_GTSW = OBSERVER_GTSWS[0]


def create_fpf_tc04_test_config() -> TestConfig:
    skip_ssh = skip_ssh_dependencies()
    ib_setup, ib_teardown = fpf_ib_traffic_tasks(skip_ssh)
    playbook = create_fpf_service_restart_playbook(
        gtsws=OBSERVER_GTSWS,
        hosts=GPU_HOSTS,
        trigger_stsws=TRIGGER_STSWS,
        service=taac_types.Service.AGENT,
        restart_device_regexes=[DUT_GTSW],
        # Warm boot preserves the data plane (no cold-boot file). The agent's bgp
        # thrift read blips during the restart, so "bgp" is the affected rib.
        affected_rib="bgp",
        create_cold_boot_file=False,
        prefix_count=PREFIX_COUNT,
        community_list=DEFAULT_COMMUNITY_LIST,
        injected_lanes=INJECTED_LANES,
        prod_prefixes=PROD_PREFIXES,
        hrt_memory_hosts=HRT_MEMORY_HOSTS,
        hrt_driver_hosts=HRT_MEMORY_HOSTS,
        fsdb_expected_total=EXPECTED_FSDB_SESSION_COUNT,
        stabilization_delay_sec=120,
        settle_after_restart_sec=120,
        skip_ssh_dependent_checks=skip_ssh,
        spray_hosts=None if skip_ssh else SPRAY_HOSTS,
        # Prefixes injected once by the setup task (8-STSW split-per-VF).
        skip_injection=True,
        rf_vf_groups=RF_VF_GROUPS,
        playbook_name="fpf_tc04_wedge_agent_warmboot",
    )
    return TestConfig(
        name="fpf_tc04_wedge_agent_warmboot",
        endpoints=create_fpf_endpoints(stsws=ALL_STSWS),
        setup_tasks=[
            *ib_setup,
            create_fpf_start_collectors_task(
                gtsws=OBSERVER_GTSWS,
                hosts=GPU_HOSTS,
                subnet_prefix=VF_COLLECTOR_SUBNET,
                prod_prefixes=PROD_PREFIXES,
                prod_prefix_host=PROD_PREFIX_HOST,
                prod_prefix_device_id=0,
                fsdb_mode=FSDB_COLLECTOR_MODE,
                allow_baseline_failures=ALLOW_BASELINE_FAILURES,
                rf_vf_groups=RF_VF_GROUPS,
            ),
            create_fpf_inject_vf_groups_task(
                groups=INJECTION_GROUPS,
                settle_sec=INJECT_SETTLE_SEC,
            ),
        ],
        teardown_tasks=[
            create_fpf_withdraw_vf_groups_task(groups=INJECTION_GROUPS),
            # Robust catch-all: restart bgpd on all 8 STSWs to clear injected +
            # any leftover prefixes (reloads persistent config).
            create_fpf_restart_service_task(devices=ALL_STSWS, service="BGP"),
            create_fpf_stop_collectors_task(
                trigger_stsws=TRIGGER_STSWS,
                withdraw=False,
                community_list=DEFAULT_COMMUNITY_LIST,
            ),
            *ib_teardown,
        ],
        playbooks=[playbook],
        tags=["fpf"],
    )


TEST_CONFIG = create_fpf_tc04_test_config()
