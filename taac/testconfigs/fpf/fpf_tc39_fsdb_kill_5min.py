# (c) Meta Platforms, Inc. and affiliates. Confidential and proprietary.

# pyre-unsafe

"""TC39: Kill FSDB on the DUT GTSW for 5 minutes (BEYOND graceful restart).

Repeatedly SIGKILLs ``fsdb`` on gtsw001 (every 1s for 300s = 5 min) so the
daemon never exits gracefully AND the outage outlasts the FSDB graceful-restart
(GR) hold window. fsdb owns lane 0 (gtsw001 -> lane 0 = ``beth0`` on the GPU
NIC hosts). Unlike the brief 60s kill in tc28 — which stays inside GR so the
data plane keeps forwarding — a SUSTAINED 5-min kill past GR PURGES lane-0
routes: ``beth0`` data-plane egress DRAINS on the GPU host cabled to gtsw001
while beth1-3 keep spraying, and the overall HRT CONNECTED FSDB-session census
dips 32 -> 28 and must recover to 32 once the kill stops. The other GPU host's
beth0 lands on a different plane-0 GTSW (LLDP-confirmed: only GPU_HOSTS[0]
neighbors gtsw001), so it is unaffected — a blast-radius-containment control.

Two-playbook "longevity-anchored health check" structure:

  Playbook 1 (disruption-only): inject test prefixes, stabilize 120s, record the
    disruption moment, repeatedly SIGKILL fsdb (1s x 300s) on gtsw001, then a
    120s stable wait. Two POSTCHECKS:
      - session-stat (mode="disruption"): census 32 -> 28 on lane 0 during the
        kill -> recover to 32 and hold >= 60s. Its window anchors via a wide
        lookback (1200s) spanning stabilize(120) + kill(300) + stable(120).
      - host-spray "spray #1": over the KILL WINDOW (anchored at the recorded
        disruption_time for the 300s kill duration), lane 0 (``beth0``) on the
        GPU host cabled to gtsw001 must be DRAINED (< 10 Gbps) while its other 3
        lanes keep spraying (> 75 Gbps). This is the data-plane signal that the
        sustained, past-GR kill actually purged lane-0 forwarding. The other GPU
        host (beth0 on a different plane-0 GTSW) keeps all 4 lanes > 75 Gbps as a
        blast-radius-containment control.

  Playbook 2 (stable-state longevity, 5 min): the FULL stable-state hardening
    contract (create_fpf_hardening_playbook_v2). The TaacRunner re-stamps
    test_case_start_time at THIS playbook's start, so every HC anchors at
    longevity start (the disruption window is excluded) and asserts the recovered
    steady state, including the session-stat check in STABLE mode (32, no churn)
    and host-spray "spray #2" (labeled "[longevity] all 4 lanes >75Gbps") proving
    FULL recovery — all 4 lanes, including lane 0, back to spraying.

ASSUMPTIONS:
  - The 5-min (300s) continuous SIGKILL exceeds the FSDB GR window (~120s), so
    lane 0 is fully withdrawn (purged) during the kill — beth0 egress drains on
    the GPU host cabled to gtsw001 (GPU_HOSTS[0]); the other GPU host is on a
    different plane-0 GTSW and stays fully sprayed (containment control).
  - lookback_sec=1200 on the disruption-mode session-stat postcheck is wide
    enough to cover stabilize(120) + kill(300) + stable(120) within Playbook 1.
  - host-spray spray #1 uses window_from_disruption_time so it evaluates ONLY the
    kill window (disruption_time .. disruption_time+300), excluding pre-kill
    healthy samples.
  - All OTHER health checks are stable-state, anchored at the longevity
    (Playbook 2) start by the runner's per-playbook test_case_start_time
    re-stamp.

Headless run kills fsdb via the driver crash path — kick off from a
Kerberos-ticketed terminal.

Usage:
  buck2 run neteng/netcastle:netcastle_taac -- \\
    --team taac --test-config fpf_tc39_fsdb_kill_5min \\
    --dev --skip-basset-reservation --skip-testbed-isolation \\
    --debug --continue-on-precheck-failure --skip-fboss-rsyslog
"""

from taac.health_checks.healthcheck_definitions import (
    create_fpf_host_spray_check,
    create_fpf_hrt_session_stat_check,
)
from taac.libs.fpf.fpf_prod_prefix_map import get_prefix
from taac.playbooks.playbook_definitions import (
    create_fpf_disrupt_window_playbook,
    create_fpf_hardening_playbook_v2,
)
from taac.steps.step_definitions import (
    create_fpf_bgp_prefix_injection_step,
    create_fpf_record_disruption_time_step,
    create_fpf_repeated_service_crash_step,
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
    TRIGGER_STSWS,
)
from taac.test_as_a_config import types as taac_types
from taac.test_as_a_config.types import TestConfig

PREFIX_COUNT = 1000
STABILIZATION_DELAY_SEC = 120
KILL_EVERY_SEC = 1
KILL_DURATION_SEC = 300  # 5 min, beyond the FSDB GR window: lane-0 routes purge.
STABLE_AFTER_KILL_SEC = 120
LONGEVITY_SOAK_SEC = 300
# Wide enough for stabilize(120) + kill(300) + stable(120) within Playbook 1.
SESSION_LOOKBACK_SEC = 1200
RECOVERY_MIN_SEC = 60

# fsdb on gtsw001 owns lane 0; killing it impacts lane 0 of all 4 GPUs -> 32-4=28.
DUT_GTSW = OBSERVER_GTSWS[0]
# Only the GPU host whose beth0 is physically cabled to DUT_GTSW (gtsw001) drains
# its lane 0 when gtsw001's fsdb is killed — confirmed by LLDP on gtsw001
# (rtptest1544/beth0 -> gtsw001 eth1/41/5). The other GPU host's beth0 lands on a
# different plane-0 GTSW, so it is unaffected (all 4 lanes keep spraying) and
# serves as a blast-radius-containment control. GPU_HOSTS[0] is the config's
# primary host (also prod-prefix and fsdb-session host) cabled to DUT_GTSW.
DUT_HOST = GPU_HOSTS[0]
IMPACTED_LANES = [0]
CONNECTED_DURING = EXPECTED_FSDB_SESSION_COUNT - 4  # 28

PROD_PREFIX_HOST = GPU_HOSTS[0]
PROD_PREFIX_DEVICE_ID = 0
PROD_PREFIXES = [get_prefix(PROD_PREFIX_HOST, PROD_PREFIX_DEVICE_ID)]


def create_fpf_tc39_test_config() -> TestConfig:
    skip_ssh = skip_ssh_dependencies()
    ib_setup, ib_teardown = fpf_ib_traffic_tasks(skip_ssh)

    # --- Playbook 1: disruption-only — session-stat + host-spray (spray #1). ---
    disrupt_steps = [
        create_fpf_bgp_prefix_injection_step(
            devices=TRIGGER_STSWS,
            count=PREFIX_COUNT,
            community_list=DEFAULT_COMMUNITY_LIST,
            description=f"Inject {PREFIX_COUNT} test prefixes on the trigger STSWs",
        ),
        create_longevity_step(
            duration=STABILIZATION_DELAY_SEC,
            description=f"Stabilize {STABILIZATION_DELAY_SEC}s before the FSDB kill",
        ),
        create_fpf_record_disruption_time_step(
            description="Record FSDB-kill disruption time"
        ),
        create_fpf_repeated_service_crash_step(
            service=taac_types.Service.FSDB,
            every_sec=KILL_EVERY_SEC,
            duration_sec=KILL_DURATION_SEC,
            device_regexes=[DUT_GTSW],
            description=(
                f"SIGKILL fsdb every {KILL_EVERY_SEC}s for {KILL_DURATION_SEC}s "
                f"on {DUT_GTSW} (unclean exit, beyond GR -> lane-0 routes purge)"
            ),
        ),
        create_longevity_step(
            duration=STABLE_AFTER_KILL_SEC,
            description=f"Stable {STABLE_AFTER_KILL_SEC}s after the FSDB kill stops",
        ),
    ]
    disrupt_playbook = create_fpf_disrupt_window_playbook(
        playbook_name="fpf_tc39_fsdb_kill5m_disrupt",
        disruption_steps=disrupt_steps,
        postchecks=[
            create_fpf_hrt_session_stat_check(
                mode="disruption",
                expected_connected=EXPECTED_FSDB_SESSION_COUNT,
                expected_connected_during=CONNECTED_DURING,
                impacted_lanes=IMPACTED_LANES,
                recovery_min_sec=RECOVERY_MIN_SEC,
                lookback_sec=SESSION_LOOKBACK_SEC,
                check_id="fpf_tc39_fsdb_kill5m_session_stat",
            ),
            # spray #1: over the kill window, lane 0 (beth0) drained < 10 Gbps on
            # the GPU host cabled to gtsw001 (DUT_HOST) while its lanes 1-3 keep
            # spraying > 75 Gbps. The other GPU host is unaffected (beth0 on a
            # different plane-0 GTSW) — all 4 lanes > 75 Gbps (containment).
            create_fpf_host_spray_check(
                hosts=GPU_HOSTS,
                impacted_lanes_by_host={DUT_HOST: ["beth0"]},
                impacted_max_gbps=10.0,
                min_egress_gbps=75.0,
                window_from_disruption_time=True,
                window_duration_sec=KILL_DURATION_SEC,
                label=(
                    "[fsdb-kill window] DUT-host lane0(beth0) drained <10Gbps + "
                    "its lanes1-3 >75Gbps; other host all 4 lanes >75Gbps "
                    "(containment)"
                ),
                check_id="fpf_tc39_fsdb_kill5m_host_spray_kill",
            ),
        ],
    )

    # --- Playbook 2: full stable-state longevity (5 min); host-spray spray #2. ---
    longevity_playbook = create_fpf_hardening_playbook_v2(
        gtsws=OBSERVER_GTSWS,
        hosts=GPU_HOSTS,
        trigger_stsws=TRIGGER_STSWS,
        soak_duration_sec=LONGEVITY_SOAK_SEC,
        stabilization_delay_sec=0,
        prefix_count=PREFIX_COUNT,
        community_list=DEFAULT_COMMUNITY_LIST,
        playbook_name="fpf_tc39_fsdb_kill5m_longevity",
        prod_prefixes=PROD_PREFIXES,
        skip_ssh_dependent_checks=skip_ssh,
        hrt_memory_hosts=HRT_MEMORY_HOSTS,
        hrt_driver_hosts=HRT_MEMORY_HOSTS,
        spray_hosts=GPU_HOSTS,
        host_spray_label="[longevity] all 4 lanes >75Gbps",
        fsdb_expected_total=EXPECTED_FSDB_SESSION_COUNT,
    )

    return TestConfig(
        name="fpf_tc39_fsdb_kill_5min",
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
        # Strict order: disruption first, then stable-state longevity.
        playbooks=[disrupt_playbook, longevity_playbook],
        tags=["fpf"],
    )


TEST_CONFIG = create_fpf_tc39_test_config()
