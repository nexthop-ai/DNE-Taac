# Copyright (c) Meta Platforms, Inc. and affiliates.

# pyre-unsafe
"""Unit tests for BgpConvergenceHealthCheck, focused on the opt-in
`validate_sequence` initialization-event-order assertion."""

import unittest
from unittest.mock import AsyncMock, MagicMock

from neteng.fboss.bgp_thrift.types import BgpInitializationEvent
from neteng.netcastle.logger import ConsoleFileLogger
from taac.constants import TestDevice
from taac.health_checks.device_health_checks.bgp_convergence_health_check import (
    BgpConvergenceHealthCheck,
)
from taac.health_check.health_check import types as hc_types


def _full_ordered_events():
    """Canonical happy-path event map (timestamps in ms, monotonic).

    FSDB_SUBSCRIBED is intentionally omitted (not emitted on EOS/bgpcpp).
    """
    return {
        BgpInitializationEvent.INITIALIZING: 0,
        BgpInitializationEvent.AGENT_CONFIGURED: 1000,
        BgpInitializationEvent.PEER_INFO_LOADED: 2000,
        BgpInitializationEvent.ALL_EOR_RECEIVED: 3000,
        BgpInitializationEvent.RIB_COMPUTED: 4000,
        BgpInitializationEvent.FIB_SYNCED: 5000,
        BgpInitializationEvent.EOR_SENT: 6000,
        BgpInitializationEvent.INITIALIZED: 7000,
    }


class TestBgpConvergenceHealthCheck(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.logger = MagicMock(spec=ConsoleFileLogger)
        self.health_check = BgpConvergenceHealthCheck(logger=self.logger)
        self.health_check.driver = AsyncMock()
        self.device = MagicMock(spec=TestDevice)
        self.device.name = "bag012.ash6"
        self.input = hc_types.BaseHealthCheckIn()

    # ---- _validate_event_sequence (pure helper) ----
    def test_sequence_helper_ok(self):
        self.assertIsNone(
            self.health_check._validate_event_sequence(_full_ordered_events(), "dev")
        )

    def test_sequence_helper_missing_initialized(self):
        events = _full_ordered_events()
        del events[BgpInitializationEvent.INITIALIZED]
        err = self.health_check._validate_event_sequence(events, "dev")
        self.assertIsNotNone(err)
        self.assertIn("INITIALIZED", err)

    def test_sequence_helper_out_of_order(self):
        events = _full_ordered_events()
        # FIB_SYNCED occurs before RIB_COMPUTED -> inversion
        events[BgpInitializationEvent.FIB_SYNCED] = 3500
        err = self.health_check._validate_event_sequence(events, "dev")
        self.assertIsNotNone(err)
        self.assertIn("out of order", err)

    def test_sequence_helper_ignores_absent_intermediate(self):
        """A legitimately-absent intermediate must not fail the sequence."""
        events = _full_ordered_events()
        del events[BgpInitializationEvent.PEER_INFO_LOADED]
        self.assertIsNone(self.health_check._validate_event_sequence(events, "dev"))

    # ---- _run end-to-end ----
    async def test_run_validate_sequence_pass(self):
        self.health_check.driver.async_get_bgp_initialization_events = AsyncMock(
            return_value=_full_ordered_events()
        )
        result = await self.health_check._run(
            self.device, self.input, {"validate_sequence": True}
        )
        self.assertEqual(result.status, hc_types.HealthCheckStatus.PASS)

    async def test_run_validate_sequence_out_of_order_fail(self):
        events = _full_ordered_events()
        events[BgpInitializationEvent.FIB_SYNCED] = 3500
        self.health_check.driver.async_get_bgp_initialization_events = AsyncMock(
            return_value=events
        )
        result = await self.health_check._run(
            self.device, self.input, {"validate_sequence": True}
        )
        self.assertEqual(result.status, hc_types.HealthCheckStatus.FAIL)
        self.assertIn("out of order", result.message)

    async def test_run_eor_timer_expired_fail(self):
        events = _full_ordered_events()
        events[BgpInitializationEvent.EOR_TIMER_EXPIRED] = 2500
        self.health_check.driver.async_get_bgp_initialization_events = AsyncMock(
            return_value=events
        )
        result = await self.health_check._run(
            self.device, self.input, {"validate_sequence": True}
        )
        self.assertEqual(result.status, hc_types.HealthCheckStatus.FAIL)
        self.assertIn("EOR timer", result.message)

    async def test_run_validate_sequence_false_skips_ordering(self):
        """Default (validate_sequence omitted) preserves prior behavior: an
        out-of-order intermediate still PASSes as long as endpoints + timing
        are healthy."""
        events = _full_ordered_events()
        events[BgpInitializationEvent.FIB_SYNCED] = 3500
        self.health_check.driver.async_get_bgp_initialization_events = AsyncMock(
            return_value=events
        )
        result = await self.health_check._run(self.device, self.input, {})
        self.assertEqual(result.status, hc_types.HealthCheckStatus.PASS)

    async def test_stage_times_absolute_format(self):
        """Stage times report each event's ABSOLUTE time-from-start (ms/1000),
        not a per-stage '+delta', so out-of-order events stay readable."""
        self.health_check.driver.async_get_bgp_initialization_events = AsyncMock(
            return_value=_full_ordered_events()
        )
        result = await self.health_check._run(
            self.device, self.input, {"validate_sequence": True}
        )
        self.assertIn("Stage times:", result.message)
        # Absolute time-from-start per event, not a delta from the previous one.
        self.assertIn("INITIALIZING: 0.00s", result.message)
        self.assertIn("AGENT_CONFIGURED: 1.00s", result.message)
        self.assertIn("INITIALIZED: 7.00s", result.message)
        # The old per-stage delta format ("EVENT: +Xs") must be gone.
        self.assertNotIn(": +", result.message)
