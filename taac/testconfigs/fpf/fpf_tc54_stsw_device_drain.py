# (c) Meta Platforms, Inc. and affiliates. Confidential and proprietary.

"""TC54: STSW device drain (strict stable-state) — drain stsw001.s001.

Soft-drains a single STSW (stsw001.s001, which serves the lane-0 plane) via the
on-box LOCAL_DRAINER and re-injects the FPF prefixes with the drain-marker
community, then validates the steady state.

How this differs from the GTSW device drain (tc19) and the drain-tolerant STSW
drain (tc34):
  - The GTSW's own BGP is NOT restarted/depreferenced here — only the STSW's BGP
    changes. So there is NO GTSW-side transient to absorb: we do NOT apply the
    GTSW-drain allowance (no ``use_bgp_snapshot``, no ``skip_fsdb_session_
    precheck``, no gtsw convergence settle). Every control-plane / HRT collector
    is held to the FULL stable-state contract.
  - The ONLY expected deviation from stable state is on the DATA plane: the
    lane-0 plane that stsw001.s001 serves drains, so on BOTH GPU hosts the last
    samples of lane 0 (beth0) egress should read ~0 (not taking traffic). That
    is asserted via the plane-status DRAIN contract on lane 0
    (``impacted_planes_by_host``); everything else stays strictly stable.

NOTE: this config is BUILD-validated only; it has NOT been run on hardware. The
host-spray lane-0-drained expectation in particular should be confirmed/tuned on
the first hardware run.

Usage:
  buck2 run neteng/netcastle:netcastle_taac -- \\
    --team taac --test-config fpf_tc54_stsw_device_drain \\
    --dev --skip-basset-reservation --skip-testbed-isolation \\
    --debug --continue-on-precheck-failure --skip-fboss-rsyslog
"""

from taac.libs.fpf.fpf_prod_prefix_map import get_prefix
from taac.playbooks.playbook_definitions import (
    create_fpf_disruption_only_playbook,
    create_fpf_hardening_playbook_v2,
)
from taac.steps.step_definitions import (
    create_fpf_stsw_drain_and_reinject_steps,
    create_longevity_step,
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
    fpf_ib_traffic_tasks,
    FSDB_COLLECTOR_MODE,
    GPU_HOSTS,
    HRT_MEMORY_HOSTS,
    OBSERVER_GTSWS,
    skip_ssh_dependencies,
    SPRAY_HOSTS,
    TRIGGER_STSWS,
)
from taac.test_as_a_config.types import TestConfig

PREFIX_COUNT = 1000
LONGEVITY_SEC = 300

# STSW plane to drain (the first trigger STSW: stsw001.s001.l202.mwg2), which
# serves lane 0 — the same plane tc19/tc34 monitor on GPU0 of the first GPU host.
DRAIN_TARGET_STSW = TRIGGER_STSWS[0]
# Canonical FPF STSW drain community appended to the re-injected prefixes so the
# drained plane is depreferenced (lane 0 drains) rather than withdrawn.
DRAIN_COMMUNITY = "65446:10"

PROD_PREFIX_HOST = GPU_HOSTS[0]
PROD_PREFIX_DEVICE_ID = 0
PROD_PREFIXES = [get_prefix(PROD_PREFIX_HOST, PROD_PREFIX_DEVICE_ID)]

# stsw001.s001 -> lane 0: the drained data plane on both GPU hosts.
IMPACTED_PLANES_BY_HOST = {PROD_PREFIX_HOST: [0]}


def create_fpf_tc54_test_config() -> TestConfig:
    skip_ssh = skip_ssh_dependencies()
    ib_setup, ib_teardown = fpf_ib_traffic_tasks(skip_ssh)
    spray = None if skip_ssh else SPRAY_HOSTS

    disrupt_steps = [
        *create_fpf_stsw_drain_and_reinject_steps(
            stsw=DRAIN_TARGET_STSW,
            drained=True,
            trigger_stsws=TRIGGER_STSWS,
            prefix_count=PREFIX_COUNT,
            community_list=DEFAULT_COMMUNITY_LIST,
            drain_community=DRAIN_COMMUNITY,
        ),
        create_longevity_step(
            duration=LONGEVITY_SEC,
            description=(
                f"Settle {LONGEVITY_SEC}s after STSW {DRAIN_TARGET_STSW} drain + "
                "reinject"
            ),
        ),
    ]

    disrupt_playbook = create_fpf_disruption_only_playbook(
        gtsws=OBSERVER_GTSWS,
        hosts=GPU_HOSTS,
        trigger_stsws=TRIGGER_STSWS,
        disruption_steps=disrupt_steps,
        playbook_name="fpf_tc54_stsw_device_drain_disrupt",
    )

    # STRICT stable-state longevity: the GTSW BGP is untouched, so unlike tc34 we
    # do NOT pass use_bgp_snapshot / skip_fsdb_session_precheck. Only lane 0's
    # DATA plane is allowed to be drained (plane_status DRAIN contract); every
    # other signal is held to the full stable-state contract.
    longevity_playbook = create_fpf_hardening_playbook_v2(
        gtsws=OBSERVER_GTSWS,
        hosts=GPU_HOSTS,
        trigger_stsws=TRIGGER_STSWS,
        soak_duration_sec=LONGEVITY_SEC,
        stabilization_delay_sec=0,
        prefix_count=PREFIX_COUNT,
        community_list=DEFAULT_COMMUNITY_LIST,
        playbook_name="fpf_tc54_stsw_device_drain_longevity",
        prod_prefixes=PROD_PREFIXES,
        skip_ssh_dependent_checks=skip_ssh,
        fsdb_expected_total=EXPECTED_FSDB_SESSION_COUNT,
        hrt_memory_hosts=HRT_MEMORY_HOSTS,
        hrt_driver_hosts=HRT_MEMORY_HOSTS,
        spray_hosts=spray,
        # Lane 0's data plane drains; assert it DRAINED on the GPU hrtctl
        # plane-status while every other plane stays UP.
        plane_status_check=True,
        prod_prefix_recovery=True,
        local_prod_prefixes=PROD_PREFIXES,
        impacted_planes_by_host=IMPACTED_PLANES_BY_HOST,
    )

    return TestConfig(
        name="fpf_tc54_stsw_device_drain",
        endpoints=create_fpf_endpoints(),
        setup_tasks=[
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


TEST_CONFIG = create_fpf_tc54_test_config()
