# Copyright (c) Meta Platforms, Inc. and affiliates.

# pyre-unsafe

"""TC8: FSDB GR — Expiry Beyond GR Window.

Unlike the loop-kill tests (tc51), this STOPS fsdb continuously on the DUT GTSW
(gtsw001 = lane 0) and holds it down past the ~120s FSDB graceful-restart hold.
Because HRT's disconnected_gr_hold timer only resets when HRT RECONNECTS, a
continuous stop lets the timer EXPIRE → lane-0 routes are purged → beth0 egress
DRAINS on the impacted GPU host. Other lanes (beth1-3) are unaffected.

Stop duration = 240s (120s GR window + 120s settle), so we stop at least 2 min
past the 120s mark; the host-spray check then reads lane 0 over the post-GR tail
([disruption+120, disruption+240]) with the default avg(1m),latest transform, so
the "latest 1-minute" reading reflects the fully-drained state, not the GR-hold
transient. Within-window behavior (stop < 120s, lane 0 keeps spraying) is the
tc7 companion.

Requires ib_write_bw traffic flowing so the per-lane beth egress is observable.
"""

from taac.health_checks.healthcheck_definitions import (
    create_fpf_host_spray_check,
)
from taac.playbooks.playbook_definitions import (
    create_fpf_hardening_playbook,
)
from taac.steps.step_definitions import (
    create_fpf_record_disruption_time_step,
    create_longevity_step,
    create_service_convergence_step,
    create_service_interruption_step,
)
from taac.testconfigs.fpf.fpf_hardening_common import (
    create_fpf_endpoints,
    fpf_clean_slate_setup_task,
    fpf_ib_traffic_tasks,
    GPU_HOSTS,
    HARDENING_PREFIX_COUNT,
    OBSERVER_GTSWS,
    skip_ssh_dependencies,
    SPRAY_HOSTS,
    TRIGGER_STSWS,
)
from taac.test_as_a_config import types as taac_types
from taac.test_as_a_config.types import TestConfig

GR_WINDOW_SEC = 120
# Stop >= 2 min past the 120s GR mark so lane 0 is fully drained + settled.
STOP_DURATION_SEC = GR_WINDOW_SEC + 120  # 240s
SPRAY_FLOOR_GBPS = 75.0
SPRAY_IMPACTED_MAX_GBPS = 10.0


def create_fpf_tc08_test_config() -> TestConfig:
    skip_ssh = skip_ssh_dependencies()
    ib_setup, ib_teardown = fpf_ib_traffic_tasks(skip_ssh)
    spray = None if skip_ssh else SPRAY_HOSTS

    disruption_steps = [
        create_fpf_record_disruption_time_step(
            description="Record FSDB-stop disruption time (anchors the spray window)"
        ),
        create_service_interruption_step(
            service=taac_types.Service.FSDB,
            trigger=taac_types.ServiceInterruptionTrigger.SYSTEMCTL_STOP,
            description="Stop FSDB on DUT GTSW (held down past GR window)",
        ),
        create_longevity_step(
            duration=STOP_DURATION_SEC,
            description=(
                f"Hold FSDB down {STOP_DURATION_SEC}s "
                f"(>{GR_WINDOW_SEC}s GR window — lane-0 routes purge, beth0 drains)"
            ),
        ),
        create_service_interruption_step(
            service=taac_types.Service.FSDB,
            trigger=taac_types.ServiceInterruptionTrigger.SYSTEMCTL_START,
            description="Restart FSDB on DUT GTSW after GR expiry",
        ),
        create_service_convergence_step(
            services=[taac_types.Service.FSDB],
            timeout=600,
            description="Wait for FSDB convergence after GR expiry recovery",
        ),
    ]

    postchecks = []
    if spray:
        # Over the POST-GR tail [disruption+120, disruption+240] (fsdb still
        # stopped), assert lane 0 (beth0) is DRAINED (<10 Gbps) on every spray
        # host while beth1-3 stay sprayed (>75 Gbps). window_offset_sec skips the
        # GR-hold transient; the default transform is avg(1m),latest so the
        # "latest 1m" reads the fully-drained state.
        postchecks.append(
            create_fpf_host_spray_check(
                hosts=SPRAY_HOSTS,
                min_egress_gbps=SPRAY_FLOOR_GBPS,
                impacted_lanes_by_host={h: ["beth0"] for h in SPRAY_HOSTS},
                impacted_max_gbps=SPRAY_IMPACTED_MAX_GBPS,
                window_from_disruption_time=True,
                window_offset_sec=GR_WINDOW_SEC,
                window_duration_sec=STOP_DURATION_SEC - GR_WINDOW_SEC,
                label=(
                    "[fsdb-stop >GR] lane0(beth0) drained <10G; lanes1-3 spray >75G"
                ),
                check_id="fpf_tc08_host_spray_lane0_drained",
            )
        )

    playbook = create_fpf_hardening_playbook(
        gtsws=OBSERVER_GTSWS,
        hosts=GPU_HOSTS,
        trigger_stsws=TRIGGER_STSWS,
        disruption_steps=disruption_steps,
        disruption_duration_sec=600,
        prefix_count=HARDENING_PREFIX_COUNT,
        additional_postchecks=postchecks,
        playbook_name="fpf_tc08_fsdb_gr_beyond_window",
    )

    return TestConfig(
        name="fpf_tc08_fsdb_gr_beyond_window",
        endpoints=create_fpf_endpoints(),
        setup_tasks=[fpf_clean_slate_setup_task(), *ib_setup],
        teardown_tasks=[*ib_teardown],
        playbooks=[playbook],
    )


TEST_CONFIG = create_fpf_tc08_test_config()
