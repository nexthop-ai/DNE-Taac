# Copyright (c) Meta Platforms, Inc. and affiliates.

# pyre-unsafe
import asyncio
import time
import typing as t

from neteng.fboss.bgp_thrift.types import BgpInitializationEvent
from taac.constants import TestDevice
from taac.health_checks.abstract_health_check import (
    AbstractDeviceHealthCheck,
)
from taac.health_check.health_check import types as hc_types


class BgpConvergenceHealthCheck(AbstractDeviceHealthCheck[hc_types.BaseHealthCheckIn]):
    CHECK_NAME = hc_types.CheckName.BGP_CONVERGENCE_CHECK
    OPERATING_SYSTEMS = [
        "FBOSS",
        "EOS",
    ]

    # Canonical happy-path BGP++ initialization-event order. Excludes
    # EOR_TIMER_EXPIRED (the unhappy-path substitute for ALL_EOR_RECEIVED) and
    # FSDB_SUBSCRIBED (not emitted on EOS/bgpcpp devices). Used by the opt-in
    # `validate_sequence` check.
    EXPECTED_EVENT_SEQUENCE = [
        BgpInitializationEvent.INITIALIZING,
        BgpInitializationEvent.AGENT_CONFIGURED,
        BgpInitializationEvent.PEER_INFO_LOADED,
        BgpInitializationEvent.ALL_EOR_RECEIVED,
        BgpInitializationEvent.RIB_COMPUTED,
        BgpInitializationEvent.FIB_SYNCED,
        BgpInitializationEvent.EOR_SENT,
        BgpInitializationEvent.INITIALIZED,
    ]

    async def _run(
        self,
        obj: TestDevice,
        input: hc_types.BaseHealthCheckIn,
        check_params: t.Dict[str, t.Any],
    ) -> hc_types.HealthCheckResult:
        convergence_threshold = check_params.get(
            "convergence_threshold", 150
        )  # 150 seconds
        start_event = check_params.get(
            "start_event", BgpInitializationEvent.AGENT_CONFIGURED.value
        )
        end_event = check_params.get(
            "end_event", BgpInitializationEvent.INITIALIZED.value
        )
        fail_on_eor_expired = check_params.get("fail_on_eor_expired", True)
        validate_sequence = check_params.get("validate_sequence", False)
        start_event_enum = BgpInitializationEvent(int(start_event))
        end_event_enum = BgpInitializationEvent(int(end_event))
        bgp_initialization_events = (
            # pyrefly: ignore [missing-attribute]
            await self.driver.async_get_bgp_initialization_events()
        )
        if (
            fail_on_eor_expired
            and BgpInitializationEvent.EOR_TIMER_EXPIRED in bgp_initialization_events
        ):
            return hc_types.HealthCheckResult(
                status=hc_types.HealthCheckStatus.FAIL,
                message=f"EOR timer expired on {obj.name} during BGP convergence",
            )
        if not bgp_initialization_events.get(
            end_event_enum
        ) or not bgp_initialization_events.get(start_event_enum):
            end_time = time.time() + convergence_threshold
            CHECK_INTERVAL = 5
            while time.time() < end_time:
                await asyncio.sleep(CHECK_INTERVAL)
                if hasattr(self.driver, "is_bgp_converged_fib_ready"):
                    converged = await self.driver.is_bgp_converged_fib_ready()
                elif hasattr(self.driver, "async_is_bgp_initialization_converged"):
                    converged = (
                        await self.driver.async_is_bgp_initialization_converged()
                    )
                else:
                    converged = False
                if converged:
                    break
            bgp_initialization_events = (
                # pyrefly: ignore [missing-attribute]
                await self.driver.async_get_bgp_initialization_events()
            )

        # Build detailed stage timing: each event's ABSOLUTE time-from-start
        # (ms->s), matching the `show bgpcpp initialization-events` "Time From
        # Start" column. Sorted by timestamp so out-of-order events (e.g. a late
        # ALL_EOR_RECEIVED after EOR_TIMER_EXPIRED) still read chronologically.
        def get_stage_details(events_dict):
            if not events_dict:
                return "No events recorded"

            sorted_events = sorted(events_dict.items(), key=lambda x: x[1])
            return ", ".join(
                f"{event.name}: {timestamp / 1000:.2f}s"
                for event, timestamp in sorted_events
            )

        stage_details = get_stage_details(bgp_initialization_events)

        if (
            fail_on_eor_expired
            and BgpInitializationEvent.EOR_TIMER_EXPIRED in bgp_initialization_events
        ):
            return hc_types.HealthCheckResult(
                status=hc_types.HealthCheckStatus.FAIL,
                message=f"EOR timer expired on {obj.name} during BGP convergence. Stage times: {stage_details}",
            )
        if not bgp_initialization_events.get(
            start_event_enum
        ) or not bgp_initialization_events.get(end_event_enum):
            msg = (
                f"BGP did not publish {start_event_enum.name} and/or {end_event_enum.name} event on {obj.name} "
                f"within {convergence_threshold} seconds. Stage times: {stage_details}"
            )
            self.logger.debug(msg)
            return hc_types.HealthCheckResult(
                status=hc_types.HealthCheckStatus.FAIL,
                message=msg,
            )

        convergence_time_in_sec = (
            bgp_initialization_events[end_event_enum]
            - bgp_initialization_events[start_event_enum]
        ) / 1000
        if convergence_time_in_sec > convergence_threshold:
            msg = (
                f"BGP transitioned from event {start_event_enum.name} to {end_event_enum.name} on {obj.name} in "
                f"{convergence_time_in_sec:.2f} seconds which is more than the threshold of {convergence_threshold} seconds. "
                f"Stage times: {stage_details}"
            )
            self.logger.debug(msg)
            return hc_types.HealthCheckResult(
                status=hc_types.HealthCheckStatus.FAIL,
                message=msg,
            )
        if validate_sequence:
            sequence_error = self._validate_event_sequence(
                bgp_initialization_events, obj.name
            )
            if sequence_error is not None:
                self.logger.debug(sequence_error)

                return hc_types.HealthCheckResult(
                    status=hc_types.HealthCheckStatus.FAIL,
                    message=f"{sequence_error}. Stage times: {stage_details}",
                )

        self.logger.debug(
            f"BGP transitioned from event {start_event_enum.name} to {end_event_enum.name} on {obj.name} in {convergence_time_in_sec} seconds"
        )

        return hc_types.HealthCheckResult(
            status=hc_types.HealthCheckStatus.PASS,
            message=f"BGP converged in {convergence_time_in_sec:.2f} seconds (from {start_event_enum.name} to {end_event_enum.name}). Stage times: {stage_details}",
        )

    def _validate_event_sequence(
        self,
        events_dict: t.Mapping[BgpInitializationEvent, int],
        device_name: str,
    ) -> t.Optional[str]:
        """Validate BGP++ init events occurred in the canonical order.

        Robust by design: only the canonical happy-path events that are
        actually present are ordered, so a legitimately-absent intermediate
        does not produce a false failure. Returns an error message when the
        sequence is invalid (terminal INITIALIZED missing, or a present
        canonical event out of timestamp order), or None when healthy.
        """
        if BgpInitializationEvent.INITIALIZED not in events_dict:
            return (
                f"BGP did not reach INITIALIZED on {device_name}; "
                "initialization sequence incomplete"
            )

        present = [
            (event, events_dict[event])
            for event in self.EXPECTED_EVENT_SEQUENCE
            if event in events_dict
        ]
        for prev, curr in zip(present, present[1:]):
            if curr[1] < prev[1]:
                return (
                    f"BGP initialization events out of order on {device_name}: "
                    f"{prev[0].name} ({prev[1] / 1000:.2f}s) occurred after "
                    f"{curr[0].name} ({curr[1] / 1000:.2f}s)"
                )

        return None
