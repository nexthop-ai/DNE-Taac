# (c) Meta Platforms, Inc. and affiliates. Confidential and proprietary.

# pyre-unsafe
"""Unit tests for BgpPeerRouteSetEqualityHealthCheck.

The HC compares per-peer ``postpolicy_sent_prefix_count`` (the DUT-side
gauge for "routes currently advertised to this peer") across baseline +
tested peers. It mocks ``driver.async_get_bgp_sessions()`` returning
``TBgpSession``-shaped objects with ``peer_addr`` and
``postpolicy_sent_prefix_count`` attributes.

The thrift-prefix path (``getPostfilterAdvertisedNetworks``) was abandoned
because BGP++ with UG enabled does not populate per-peer adj-RIB-out --
the postfilter API returns 0 prefixes even when routes are being advertised
(see T271301144). The gauge is the same counter shown in
``show bgpcpp summary`` PS column and works correctly under UG.
"""

import json
import unittest
from unittest.mock import AsyncMock, MagicMock

from neteng.netcastle.logger import ConsoleFileLogger
from taac.constants import TestDevice
from taac.health_checks.device_health_checks.bgp_peer_route_set_equality_health_check import (
    BgpPeerRouteSetEqualityHealthCheck,
)
from taac.health_checks.healthcheck_definitions import (
    create_bgp_peer_route_set_equality_check,
)
from taac.health_check.health_check import types as hc_types


def _session(peer_addr: str, sent: int):
    """Build a TBgpSession-shaped mock with the fields the HC reads."""
    s = MagicMock()
    s.peer_addr = peer_addr
    s.postpolicy_sent_prefix_count = sent
    return s


BASELINE = "2401:db00::11"
TESTED_1 = "2401:db00::13"
TESTED_2 = "2401:db00::15"


class BgpPeerRouteSetEqualityHealthCheckTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.logger = MagicMock(spec=ConsoleFileLogger)
        self.hc = BgpPeerRouteSetEqualityHealthCheck(logger=self.logger)
        self.hc.driver = AsyncMock()
        self.device = MagicMock(spec=TestDevice)
        self.device.name = "bag012.ash6"
        self.input = hc_types.BaseHealthCheckIn()

    def _wire(self, counts):
        """Wire async_get_bgp_sessions to return one TBgpSession per peer."""
        sessions = [_session(peer, sent) for peer, sent in counts.items()]
        self.hc.driver.async_get_bgp_sessions = AsyncMock(return_value=sessions)

    async def test_passes_when_baseline_and_tested_counts_match(self):
        self._wire({BASELINE: 300, TESTED_1: 300, TESTED_2: 300})
        result = await self.hc._run(
            self.device,
            self.input,
            {
                "baseline_peer_addr": BASELINE,
                "tested_peer_addrs": [TESTED_1, TESTED_2],
            },
        )
        self.assertEqual(result.status, hc_types.HealthCheckStatus.PASS)

    async def test_fails_when_tested_count_differs_from_baseline(self):
        self._wire({BASELINE: 300, TESTED_1: 250})
        result = await self.hc._run(
            self.device,
            self.input,
            {
                "baseline_peer_addr": BASELINE,
                "tested_peer_addrs": [TESTED_1],
            },
        )
        self.assertEqual(result.status, hc_types.HealthCheckStatus.FAIL)
        self.assertIn(TESTED_1, result.message)
        self.assertIn("250", result.message)
        self.assertIn("300", result.message)

    async def test_anchor_route_count_passes_at_exact_value(self):
        self._wire({BASELINE: 300, TESTED_1: 300})
        result = await self.hc._run(
            self.device,
            self.input,
            {
                "baseline_peer_addr": BASELINE,
                "tested_peer_addrs": [TESTED_1],
                "anchor_route_count": 300,
            },
        )
        self.assertEqual(result.status, hc_types.HealthCheckStatus.PASS)

    async def test_anchor_route_count_passes_within_tolerance(self):
        """Anchor allows +/-tolerance; baseline == tested still required for
        the count-equality check (the impl checks anchor AND equality)."""
        self._wire({BASELINE: 299, TESTED_1: 299})
        result = await self.hc._run(
            self.device,
            self.input,
            {
                "baseline_peer_addr": BASELINE,
                "tested_peer_addrs": [TESTED_1],
                "anchor_route_count": 300,
                "count_tolerance": 2,
            },
        )
        self.assertEqual(result.status, hc_types.HealthCheckStatus.PASS)

    async def test_anchor_route_count_fails_when_both_off(self):
        """The "all peers wrong with the same count" failure: count equality
        passes (both 500) but the anchor catches the actual error (e.g.
        stale 500 when we expected 300 post-withdrawal)."""
        self._wire({BASELINE: 500, TESTED_1: 500})
        result = await self.hc._run(
            self.device,
            self.input,
            {
                "baseline_peer_addr": BASELINE,
                "tested_peer_addrs": [TESTED_1],
                "anchor_route_count": 300,
            },
        )
        self.assertEqual(result.status, hc_types.HealthCheckStatus.FAIL)
        # Both baseline and tested should be flagged by the anchor check.
        self.assertIn("Baseline", result.message)
        self.assertIn("Tested", result.message)

    async def test_baseline_peer_missing_from_sessions_fails(self):
        """No TBgpSession for baseline -> fail (can't compare against
        nothing). Common signal that the peer isn't established yet."""
        self._wire({TESTED_1: 300})
        result = await self.hc._run(
            self.device,
            self.input,
            {
                "baseline_peer_addr": BASELINE,
                "tested_peer_addrs": [TESTED_1],
            },
        )
        self.assertEqual(result.status, hc_types.HealthCheckStatus.FAIL)
        self.assertIn("no BGP session", result.message)

    async def test_tested_peer_missing_from_sessions_fails(self):
        self._wire({BASELINE: 300})
        result = await self.hc._run(
            self.device,
            self.input,
            {
                "baseline_peer_addr": BASELINE,
                "tested_peer_addrs": [TESTED_1],
            },
        )
        self.assertEqual(result.status, hc_types.HealthCheckStatus.FAIL)
        self.assertIn("no BGP session", result.message)

    async def test_missing_required_params_returns_fail(self):
        result = await self.hc._run(self.device, self.input, {})
        self.assertEqual(result.status, hc_types.HealthCheckStatus.FAIL)
        self.assertIn("baseline_peer_addr", result.message)

    async def test_thrift_error_returns_error(self):
        self.hc.driver.async_get_bgp_sessions = AsyncMock(
            side_effect=RuntimeError("connection refused")
        )
        result = await self.hc._run(
            self.device,
            self.input,
            {
                "baseline_peer_addr": BASELINE,
                "tested_peer_addrs": [TESTED_1],
            },
        )
        self.assertEqual(result.status, hc_types.HealthCheckStatus.ERROR)

    async def test_arista_path_delegates_to_thrift(self):
        """ARISTA_FBOSS path: thin shim that just calls _run. BGP++ doesn't
        expose the EOS received-routes CLI surface, so there's no separate
        CLI implementation to test."""
        self._wire({BASELINE: 300, TESTED_1: 300})
        result = await self.hc._run_arista(
            self.device,
            self.input,
            {
                "baseline_peer_addr": BASELINE,
                "tested_peer_addrs": [TESTED_1],
            },
        )
        self.assertEqual(result.status, hc_types.HealthCheckStatus.PASS)

    # --- factory ---

    def test_factory_emits_correct_check_name(self):
        check = create_bgp_peer_route_set_equality_check(
            baseline_peer_addr=BASELINE,
            tested_peer_addrs=[TESTED_1],
            anchor_route_count=300,
        )
        self.assertEqual(
            check.name, hc_types.CheckName.BGP_PEER_ROUTE_SET_EQUALITY_CHECK
        )
        params = json.loads(check.check_params.json_params)
        self.assertEqual(params["baseline_peer_addr"], BASELINE)
        self.assertEqual(params["tested_peer_addrs"], [TESTED_1])
        self.assertEqual(params["anchor_route_count"], 300)
