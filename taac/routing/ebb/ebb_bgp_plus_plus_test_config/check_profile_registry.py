# Copyright (c) Meta Platforms, Inc. and affiliates.

# pyre-unsafe
"""Check-profile registry — the single source of truth for *which* health
checks each Conveyor test runs and their per-(check, phase) functional params.

Background: previously every test's pre/post/snapshot policy (which checks,
convergence on/off, ``fail_on_eor_expired``, thresholds) was decided ad-hoc at
each playbook/config call site, in three parallel definition styles. That made
"what does test X check" and "flip EOR for test Y" hard to see and easy to drift
(see the dne_routing Conveyor health-check audit). This registry collapses that
into one declarative place: a playbook looks up its profile instead of
hand-assembling check lists.

Two parameter categories, deliberately kept separate:

* **Retry policy** (retry_count / delay / multiplier) — keyed by *check* alone,
  identical across pre/post and across all tests. It is NOT specified here; it
  is pulled from ``retry_policy`` (the SSOT) and baked into each check via the
  factory. Profiles never hand-pass retry numbers, which is what kills the drift.
* **Functional params** (``validate_sequence``, ``fail_on_eor_expired``,
  ``convergence_threshold``, …) — keyed by *(check, phase)* and may differ
  between the pre and post bundles of the SAME check. These ARE declared here,
  explicitly, so an EOR-type issue is a one-line edit in one visible place.

Every profile builder takes a ``ProfileContext`` (a uniform, required arg)
carrying the per-invocation, device-specific runtime values (peer groups,
thresholds, cpu_baseline, …). Standard-shape profiles thread those through the
shared ``create_standard_{pre,post,snapshot}`` factories and fix only the
POLICY; minimal-shape profiles (e.g. ``PERF_SCALING_BOUNDED_ECMP``) hand-pick a
few checks and ignore the context. Keeping the signature uniform means callers
never have to reason about which profiles need a context.

All checks are built via the ``create_*`` factories (never constructed inline)
so the ``test_no_inline_healthcheck_construction`` gate stays satisfied.
"""

from __future__ import annotations

import dataclasses
import enum
import typing as t

from taac.health_checks.healthcheck_definitions import (
    create_bgp_convergence_check,
    create_bgp_rib_fib_consistency_check,
    create_bgp_session_establish_check,
    create_bgp_session_snapshot_check,
    create_core_dumps_snapshot_check,
)
from taac.health_checks.retry_policy import get_retry_kwargs
from taac.routing.ebb.ebb_bgp_plus_plus_test_config.common_health_checks import (
    create_standard_postchecks,
    create_standard_prechecks,
    create_standard_snapshot_checks,
)
from taac.health_check.health_check import types as hc_types
from taac.test_as_a_config.types import PointInTimeHealthCheck, SnapshotHealthCheck


class CheckProfile(enum.Enum):
    """Named check profiles. Add one entry per de-facto test profile and route
    the playbook through ``get_profile_checks`` instead of inlining checks.
    """

    # Standard-shape (compose create_standard_* + a ProfileContext):
    # BGP/agent daemon restart, convergence ON, restart-aware postcheck, strict
    # EOR (EOR-timer expiry fails the convergence check).
    DAEMON_RESTART = "daemon_restart"
    # Full cold start, convergence ON, EOR tolerated, full snapshot.
    COLD_START = "cold_start"
    # BGP route/session oscillation & multipath churn: convergence OFF; which
    # snapshot sub-checks to skip varies by sub-shape (carried in the context).
    OSCILLATION = "oscillation"

    # Minimal-shape (accept the context for a uniform API, but ignore it):
    # bag012 perf-scaling, bounded-ECMP-sets (case9).
    PERF_SCALING_BOUNDED_ECMP = "perf_scaling_bounded_ecmp"


@dataclasses.dataclass(frozen=True)
class ProfileContext:
    """Per-invocation, device-specific values threaded into a profile.

    These are NOT policy (they vary per device/run); standard profiles fix the
    policy and pass these through to the shared ``create_standard_*`` factories.
    Minimal-shape profiles ignore this. All profile builders accept it (an empty
    ``ProfileContext()`` is fine for profiles that don't use any field) so the
    ``get_profile_checks`` signature stays uniform.
    """

    # Required for standard-shape profiles (threaded into create_standard_*,
    # which take non-optional ``str``); minimal-shape profiles ignore them, so
    # the empty-string default is only ever seen by profiles that don't use it.
    peergroup_ibgp_v6: str = ""
    peergroup_ibgp_v4: str = ""
    precheck_thresholds: t.Optional[t.Any] = None
    postcheck_thresholds: t.Optional[t.Any] = None
    # Default matches the standard-shape playbook entry points (8.0), which are
    # the only profiles that thread this into create_standard_prechecks. NOT
    # create_standard_prechecks' own 4.0 default — drain/churn want the factory
    # 4.0 and get it by not passing cpu_baseline at all, so this default is only
    # ever read by the 8.0 consumers. Keeping it 8.0 means a direct
    # get_profile_checks(DAEMON_RESTART, ProfileContext()) matches the playbook.
    cpu_baseline: float = 8.0
    check_ibgp_pnh: bool = False
    expected_peer_identity: t.Optional[t.Dict[str, str]] = None
    parent_prefixes_to_ignore: t.Optional[t.List[str]] = None
    exclude_bgp_mon: bool = True
    # Cold-start tolerates an expired EOR timer by default.
    fail_on_eor_expired: bool = False
    # Oscillation: expected established session count at precheck, and which
    # snapshot sub-checks to skip (sessions intentionally flap during the test).
    expected_established_sessions: int = 0
    snapshot_skip_flap: bool = False
    snapshot_skip_uptime: bool = False


class ProfileChecks(t.NamedTuple):
    """Resolved checks for a profile, split by phase."""

    prechecks: t.List[PointInTimeHealthCheck]
    postchecks: t.List[PointInTimeHealthCheck]
    snapshot_checks: t.List[SnapshotHealthCheck]


def _daemon_restart(ctx: ProfileContext) -> ProfileChecks:
    """BGP/agent daemon restart: convergence ON, restart-aware postcheck, strict
    EOR (inherits create_standard_postchecks default fail_on_eor_expired=True),
    snapshot skips uptime (sessions are expected to have just come back up).
    """
    return ProfileChecks(
        prechecks=create_standard_prechecks(
            peergroup_ibgp_v6=ctx.peergroup_ibgp_v6,
            peergroup_ibgp_v4=ctx.peergroup_ibgp_v4,
            precheck_thresholds=ctx.precheck_thresholds,
            cpu_baseline=ctx.cpu_baseline,
            check_ibgp_pnh=ctx.check_ibgp_pnh,
            exclude_bgp_mon=ctx.exclude_bgp_mon,
        ),
        postchecks=create_standard_postchecks(
            postcheck_thresholds=ctx.postcheck_thresholds,
            expected_restarted_services=["Bgp"],
            restart_start_time_jq_var="daemon_restart_time",
            exclude_bgp_mon=ctx.exclude_bgp_mon,
        ),
        snapshot_checks=create_standard_snapshot_checks(
            skip_uptime_check=True,
            expected_peer_identity=ctx.expected_peer_identity,
            parent_prefixes_to_ignore=ctx.parent_prefixes_to_ignore,
            exclude_bgp_mon=ctx.exclude_bgp_mon,
        ),
    )


def _cold_start(ctx: ProfileContext) -> ProfileChecks:
    """Full cold start: convergence ON, EOR tolerated (fail_on_eor_expired from
    the context, default False), full snapshot (flap + uptime checks ON).
    """
    return ProfileChecks(
        prechecks=create_standard_prechecks(
            peergroup_ibgp_v6=ctx.peergroup_ibgp_v6,
            peergroup_ibgp_v4=ctx.peergroup_ibgp_v4,
            precheck_thresholds=ctx.precheck_thresholds,
            cpu_baseline=ctx.cpu_baseline,
            check_ibgp_pnh=ctx.check_ibgp_pnh,
            exclude_bgp_mon=ctx.exclude_bgp_mon,
        ),
        postchecks=create_standard_postchecks(
            postcheck_thresholds=ctx.postcheck_thresholds,
            fail_on_eor_expired=ctx.fail_on_eor_expired,
            expected_restarted_services=["Bgp"],
            restart_start_time_jq_var="daemon_restart_time",
            exclude_bgp_mon=ctx.exclude_bgp_mon,
        ),
        snapshot_checks=create_standard_snapshot_checks(
            expected_peer_identity=ctx.expected_peer_identity,
            exclude_bgp_mon=ctx.exclude_bgp_mon,
        ),
    )


def _oscillation(ctx: ProfileContext) -> ProfileChecks:
    """BGP route/session oscillation & multipath churn: standard prechecks,
    postchecks with convergence OFF (routes/sessions intentionally churn), and a
    snapshot whose flap/uptime skips are set per sub-shape via the context.
    """
    return ProfileChecks(
        prechecks=create_standard_prechecks(
            peergroup_ibgp_v6=ctx.peergroup_ibgp_v6,
            peergroup_ibgp_v4=ctx.peergroup_ibgp_v4,
            precheck_thresholds=ctx.precheck_thresholds,
            expected_established_sessions=ctx.expected_established_sessions,
            cpu_baseline=ctx.cpu_baseline,
            check_ibgp_pnh=ctx.check_ibgp_pnh,
            exclude_bgp_mon=ctx.exclude_bgp_mon,
        ),
        postchecks=create_standard_postchecks(
            postcheck_thresholds=ctx.postcheck_thresholds,
            check_bgp_convergence=False,
            exclude_bgp_mon=ctx.exclude_bgp_mon,
        ),
        snapshot_checks=create_standard_snapshot_checks(
            skip_flap_check=ctx.snapshot_skip_flap,
            skip_uptime_check=ctx.snapshot_skip_uptime,
            expected_peer_identity=ctx.expected_peer_identity,
            parent_prefixes_to_ignore=ctx.parent_prefixes_to_ignore,
            exclude_bgp_mon=ctx.exclude_bgp_mon,
        ),
    )


def _perf_scaling_bounded_ecmp(ctx: ProfileContext) -> ProfileChecks:
    """Profile for the bag012 bounded-ECMP-sets (case9) playbook.

    Minimal shape (ignores ``ctx``). Behavior-preserving vs. the prior inline
    list, with the one intended improvement: the post-test session / RIB-FIB /
    convergence checks now carry the standardized retry from the SSOT
    (previously single-shot), so transient post-disruption settling no longer
    trips a false failure.
    """
    return ProfileChecks(
        prechecks=[],
        postchecks=[
            create_bgp_session_establish_check(
                **get_retry_kwargs(hc_types.CheckName.BGP_SESSION_ESTABLISH_CHECK),
            ),
            create_bgp_rib_fib_consistency_check(
                **get_retry_kwargs(hc_types.CheckName.BGP_RIB_FIB_CONSISTENCY_CHECK),
            ),
            create_bgp_convergence_check(
                convergence_threshold=600,
                # Functional knob (per check, phase). Kept True to preserve the
                # current bag012 behavior (the prior call omitted it, inheriting
                # the server-side default True). Flip to False here to align with
                # the fleet standard (BGP_STANDARD_POSTCHECKS) if an expired EOR
                # timer under bounded-ECMP stress is deemed acceptable.
                fail_on_eor_expired=True,
                check_id="postcheck_bgp_convergence_time",
                **get_retry_kwargs(hc_types.CheckName.BGP_CONVERGENCE_CHECK),
            ),
        ],
        snapshot_checks=[
            create_core_dumps_snapshot_check(),
            create_bgp_session_snapshot_check(
                skip_flap_check=True, skip_uptime_check=True
            ),
        ],
    )


# Explicit profile -> builder mapping (no decorator/registration side effects, per
# the lazy-import guidance). Builders are referenced, not called, at import time.
_PROFILE_BUILDERS: t.Dict[CheckProfile, t.Callable[[ProfileContext], ProfileChecks]] = {
    CheckProfile.DAEMON_RESTART: _daemon_restart,
    CheckProfile.COLD_START: _cold_start,
    CheckProfile.OSCILLATION: _oscillation,
    CheckProfile.PERF_SCALING_BOUNDED_ECMP: _perf_scaling_bounded_ecmp,
}


def get_profile_checks(profile: CheckProfile, ctx: ProfileContext) -> ProfileChecks:
    """Resolve a ``CheckProfile`` to its (prechecks, postchecks, snapshot_checks).

    ``ctx`` carries per-invocation runtime values; it is required for every
    profile (pass an empty ``ProfileContext()`` for minimal-shape profiles that
    ignore it) so the entry point is uniform. Each call constructs fresh check
    objects (thrift structs are mutable, so callers must not share instances
    across playbooks).
    """
    builder = _PROFILE_BUILDERS.get(profile)
    if builder is None:
        raise ValueError(f"Unknown CheckProfile: {profile}")
    return builder(ctx)
