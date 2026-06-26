# (c) Meta Platforms, Inc. and affiliates. Confidential and proprietary.

"""TC55: full GTSW device reboot (FULL_SYSTEM_REBOOT) on the DUT GTSW.

Reboots the whole DUT GTSW box (gtsw001, which owns lane 0), waits 5 minutes for
it to come back up, then asserts recovery. Unlike tc27 (agent coldboot, which
only restarts wedge_agent with the cold-boot file), this power-cycles the entire
switch.

Two-playbook structure (per design):
  Playbook 1 (DISRUPT): inject + stabilize + record + REBOOT + 5-min come-up,
    then assert the disrupted-state contract. The reboot churns every per-lane
    HRT/RDMA collector on lane 0 for the whole window, so the disrupt postchecks
    reuse the SAME allowances as the service-kill contract
    (``build_kill_disrupt_postchecks``): the per-lane session-stat + host-spray
    collectors are NOT asserted here, and lane-0 churn is tolerated. The contract
    is modelled on the wedge_agent kill (``killed_service="wedge_agent"``)
    because a full reboot, like a wedge_agent coldboot, takes bgp + ports + every
    service DOWN with a legitimately "unclean" teardown — so bgp-establish,
    port-state, bgp-RIB convergence, and unclean-exit are NOT asserted in this
    churn window; only the service-agnostic safety signals (systemctl minus the
    bounced services, core dumps, HRT mem/driver, ODS congestion) are checked.
  Playbook 2 (LONGEVITY, strict): full stable-state contract — once the box has
    settled, EVERYTHING (bgp, ports, sessions, all lanes incl. lane 0) must be
    fully recovered. This is where recovery is verified at full strength.

DESIGN NOTES (to validate/tune on the first hardware run):
  - ``create_system_reboot_step`` does not carry an explicit device target; the
    runner scopes it via the playbook/endpoints. VERIFY it targets only the DUT
    GTSW before the first hardware run.

NOTE: this config is BUILD-validated only; it has NOT been run on hardware.

Usage:
  buck2 run neteng/netcastle:netcastle_taac -- \\
    --team taac --test-config fpf_tc55_gtsw_device_reboot \\
    --dev --skip-basset-reservation --skip-testbed-isolation \\
    --debug --continue-on-precheck-failure --skip-fboss-rsyslog
"""

from taac.libs.fpf.fpf_prod_prefix_map import get_prefix
from taac.playbooks.playbook_definitions import (
    create_fpf_disrupt_window_playbook,
    create_fpf_hardening_playbook_v2,
)
from taac.steps.step_definitions import (
    create_fpf_bgp_prefix_injection_step,
    create_fpf_record_disruption_time_step,
    create_longevity_step,
    create_system_reboot_step,
)
from taac.task_definitions import (
    create_fpf_start_collectors_task,
    create_fpf_stop_collectors_task,
)
from taac.testconfigs.fpf.fpf_hardening_common import (
    ALLOW_BASELINE_FAILURES,
    create_fpf_endpoints,
    DEFAULT_COMMUNITY_LIST,
    DEFAULT_SUBNET_PREFIX,
    EXPECTED_FSDB_SESSION_COUNT,
    fpf_clean_slate_setup_task,
    fpf_ib_traffic_tasks,
    FSDB_COLLECTOR_MODE,
    GPU_HOSTS,
    HRT_MEMORY_HOSTS,
    OBSERVER_GTSWS,
    skip_ssh_dependencies,
    SPRAY_HOSTS,
    TRIGGER_STSWS,
)
from taac.testconfigs.fpf.fpf_kill_contract import (
    build_kill_disrupt_postchecks,
)
from taac.test_as_a_config import types as taac_types
from taac.test_as_a_config.types import TestConfig

PREFIX_COUNT = 1000
STABILIZATION_DELAY_SEC = 120
REBOOT_COMEUP_SEC = 300  # 5 min for the box to reboot + rejoin the fabric
LONGEVITY_SOAK_SEC = 300
LONGEVITY_SETTLE_SEC = 120
SESSION_LOOKBACK_SEC = 1000

# A full reboot takes bgp + ports + every service DOWN with an unclean teardown,
# exactly like the wedge_agent coldboot — so the disrupt window uses the
# wedge_agent kill contract (no bgp/ports/unclean-exit asserts mid-churn). Full
# recovery is verified in the strict longevity playbook. lane 0 = gtsw001.
REBOOT_CONTRACT_SERVICE = "wedge_agent"

PROD_PREFIX_HOST = GPU_HOSTS[0]
PROD_PREFIX_DEVICE_ID = 0
PROD_PREFIXES = [get_prefix(PROD_PREFIX_HOST, PROD_PREFIX_DEVICE_ID)]


def create_fpf_tc55_test_config() -> TestConfig:
    skip_ssh = skip_ssh_dependencies()
    ib_setup, ib_teardown = fpf_ib_traffic_tasks(skip_ssh)
    spray = None if skip_ssh else SPRAY_HOSTS

    disrupt_steps = [
        create_fpf_bgp_prefix_injection_step(
            devices=TRIGGER_STSWS,
            count=PREFIX_COUNT,
            community_list=DEFAULT_COMMUNITY_LIST,
            description=f"Inject {PREFIX_COUNT} test prefixes on the trigger STSWs",
        ),
        create_longevity_step(
            duration=STABILIZATION_DELAY_SEC,
            description=f"Stabilize {STABILIZATION_DELAY_SEC}s before the reboot",
        ),
        create_fpf_record_disruption_time_step(
            description="Record GTSW reboot disruption time"
        ),
        create_system_reboot_step(
            trigger=taac_types.SystemRebootTrigger.FULL_SYSTEM_REBOOT,
            description="FULL_SYSTEM_REBOOT of the DUT GTSW",
        ),
        create_longevity_step(
            duration=REBOOT_COMEUP_SEC,
            description=f"Wait {REBOOT_COMEUP_SEC}s for the GTSW to come back up",
        ),
    ]

    disrupt_playbook = create_fpf_disrupt_window_playbook(
        playbook_name="fpf_tc55_gtsw_device_reboot_disrupt",
        disruption_steps=disrupt_steps,
        postchecks=build_kill_disrupt_postchecks(
            killed_service=REBOOT_CONTRACT_SERVICE,
            observer_gtsws=OBSERVER_GTSWS,
            hrt_memory_hosts=HRT_MEMORY_HOSTS,
            spray_hosts=spray,
            kill_duration_sec=REBOOT_COMEUP_SEC,
            prefix_count=PREFIX_COUNT,
            skip_ssh=skip_ssh,
            expected_fsdb_total=EXPECTED_FSDB_SESSION_COUNT,
            session_lookback_sec=SESSION_LOOKBACK_SEC,
        ),
    )

    longevity_playbook = create_fpf_hardening_playbook_v2(
        gtsws=OBSERVER_GTSWS,
        hosts=GPU_HOSTS,
        trigger_stsws=TRIGGER_STSWS,
        soak_duration_sec=LONGEVITY_SOAK_SEC,
        stabilization_delay_sec=0,
        prefix_count=PREFIX_COUNT,
        community_list=DEFAULT_COMMUNITY_LIST,
        playbook_name="fpf_tc55_gtsw_device_reboot_longevity",
        prod_prefixes=PROD_PREFIXES,
        skip_ssh_dependent_checks=skip_ssh,
        fsdb_expected_total=EXPECTED_FSDB_SESSION_COUNT,
        hrt_memory_hosts=HRT_MEMORY_HOSTS,
        hrt_driver_hosts=HRT_MEMORY_HOSTS,
        spray_hosts=spray,
        convergence_settle_sec=LONGEVITY_SETTLE_SEC,
    )

    return TestConfig(
        name="fpf_tc55_gtsw_device_reboot",
        endpoints=create_fpf_endpoints(),
        setup_tasks=[
            fpf_clean_slate_setup_task(),
            *ib_setup,
            create_fpf_start_collectors_task(
                gtsws=OBSERVER_GTSWS,
                hosts=GPU_HOSTS,
                subnet_prefix=DEFAULT_SUBNET_PREFIX,
                prod_prefixes=PROD_PREFIXES,
                prod_prefix_host=PROD_PREFIX_HOST,
                prod_prefix_device_id=PROD_PREFIX_DEVICE_ID,
                fsdb_mode=FSDB_COLLECTOR_MODE,
                allow_baseline_failures=ALLOW_BASELINE_FAILURES,
                enable_fsdb_session_collector=True,
                fsdb_session_host=GPU_HOSTS[0],
                fsdb_session_expected=EXPECTED_FSDB_SESSION_COUNT,
            ),
        ],
        teardown_tasks=[
            create_fpf_stop_collectors_task(
                trigger_stsws=TRIGGER_STSWS,
                prefix_count=PREFIX_COUNT,
                community_list=DEFAULT_COMMUNITY_LIST,
            ),
            *ib_teardown,
        ],
        playbooks=[disrupt_playbook, longevity_playbook],
        tags=["fpf"],
    )


TEST_CONFIG = create_fpf_tc55_test_config()
