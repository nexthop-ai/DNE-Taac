# Copyright (c) Meta Platforms, Inc. and affiliates.
"""verify_protocols must allow for sessions the CONFIG says never start.

Measured Protocols Summary on crow242 2026-08-28 at full scale:

    BGP Peer    total=16   up=16  down=0  notStarted=0
    BGP+ Peer   total=132  up=82  down=0  notStarted=50
    IPv4        total=25   up=25  down=0  notStarted=0
    IPv6        total=148  up=98  down=0  notStarted=50
    PTP         total=16   up=8   down=8  notStarted=0

The 50 notStarted are ECMP_2 -- a device group the test config creates with
`enable=False` on purpose, switched on mid-test by
test_ecmp_group_overload_limit. The count comes straight from the config
(`DeviceGroupConfig.multiplier` of the disabled groups), so no chassis query is
needed to know it, and the ATTRIBUTION comes from the config too: ECMP_2 has
only a v6 BGP stack, so it may excuse notStarted on the `BGP+ Peer` and `IPv6`
rows and NOT on the v4 rows. A single global allowance would have accepted 50
dead v4 sessions.

The PTP rows are gone rather than filtered: this chassis has no PTP support, so
the conveyor no longer builds PTP stacks (`enable_ptp=False`). Any protocol type
the config does not name is expected fully up -- which is also the right
behaviour if PTP support arrives later.

Deliberately NOT solved by walking the IXIA topology: a single
find_device_groups()/Ethernet/Ipv6/BgpIpv6Peer traversal measured 512s WITHOUT
completing at this scale, i.e. slower than the stat view it would replace.
"""

import threading
import typing as t
import unittest
from unittest.mock import MagicMock, patch

from taac.ixia.ixia import Ixia, IxiaOperationTimeoutError

_STACK_FIELDS = (
    "v4_addresses_config",
    "v6_addresses_config",
    "v4_bgp_config",
    "v6_bgp_config",
)


def _dg(enable: bool, multiplier: t.Optional[int], *stacks: str) -> MagicMock:
    """A DeviceGroupConfig whose unset stacks really are None.

    A bare MagicMock answers every attribute with a truthy Mock, which would
    make every device group look like it had all four stacks.
    """
    d = MagicMock()
    d.enable = enable
    d.multiplier = multiplier
    for field in _STACK_FIELDS:
        setattr(d, field, MagicMock() if field in stacks else None)
    return d


def _ixia_with_groups(groups: t.List[MagicMock]) -> Ixia:
    obj = Ixia.__new__(Ixia)
    obj.logger = MagicMock()
    # `verify_protocols` holds the session snapshot lock while polling `.Rows`
    # (every read is a chassis CSV snapshot). `__new__` skips `__init__`, so the
    # lock has to be supplied here. A real RLock, not a mock, so the lock path
    # is actually exercised.
    obj._snapshot_lock = threading.RLock()
    port = MagicMock()
    port.device_group_configs = groups
    cfg = MagicMock()
    cfg.port_configs = [port]
    obj.ixia_config = cfg
    return obj


def _row(protocol_type: str, not_started: int = 0, down: int = 0) -> t.Dict[str, str]:
    """A Protocols Summary row. Stat-view values arrive as CSV strings."""
    return {
        "Protocol Type": protocol_type,
        "Sessions Not Started": str(not_started),
        "Sessions Down": str(down),
    }


class ExpectedNotStartedByProtocolTest(unittest.TestCase):
    def test_disabled_v6_bgp_group_excuses_only_the_v6_rows(self):
        """ECMP_2's shape: v6 addresses + v6 BGP, disabled, multiplier 50."""
        ix = _ixia_with_groups(
            [_dg(False, 50, "v6_addresses_config", "v6_bgp_config")]
        )
        self.assertEqual(
            {"BGP+ Peer": 50, "IPv6": 50}, ix._expected_not_started_by_protocol()
        )

    def test_enabled_groups_are_not_excused(self):
        ix = _ixia_with_groups(
            [_dg(True, 50, "v6_addresses_config", "v6_bgp_config")]
        )
        self.assertEqual({}, ix._expected_not_started_by_protocol())

    def test_disabled_v4_group_attributes_to_the_v4_rows(self):
        ix = _ixia_with_groups(
            [_dg(False, 8, "v4_addresses_config", "v4_bgp_config")]
        )
        self.assertEqual(
            {"BGP Peer": 8, "IPv4": 8}, ix._expected_not_started_by_protocol()
        )

    def test_multiple_disabled_groups_sum_per_protocol(self):
        ix = _ixia_with_groups(
            [
                _dg(False, 5, "v6_addresses_config"),
                _dg(False, 7, "v6_addresses_config", "v6_bgp_config"),
            ]
        )
        self.assertEqual(
            {"IPv6": 12, "BGP+ Peer": 7}, ix._expected_not_started_by_protocol()
        )

    def test_missing_multiplier_defaults_to_one(self):
        ix = _ixia_with_groups([_dg(False, None, "v6_addresses_config")])
        self.assertEqual({"IPv6": 1}, ix._expected_not_started_by_protocol())

    def test_no_config_is_empty_not_a_crash(self):
        obj = Ixia.__new__(Ixia)
        obj.logger = MagicMock()
        obj.ixia_config = None
        self.assertEqual({}, obj._expected_not_started_by_protocol())


class ProtocolsSummaryFailuresTest(unittest.TestCase):
    def test_healthy_rows_have_no_failures(self):
        rows = [_row("BGP Peer"), _row("IPv4"), _row("IPv6")]
        self.assertEqual([], Ixia._protocols_summary_failures(rows, {}))

    def test_not_started_within_the_allowance_passes(self):
        rows = [_row("BGP+ Peer", not_started=50)]
        self.assertEqual(
            [], Ixia._protocols_summary_failures(rows, {"BGP+ Peer": 50})
        )

    def test_not_started_above_the_allowance_fails(self):
        rows = [_row("BGP+ Peer", not_started=51)]
        failures = Ixia._protocols_summary_failures(rows, {"BGP+ Peer": 50})
        self.assertEqual(1, len(failures))
        self.assertIn("BGP+ Peer", failures[0])
        self.assertIn("51", failures[0])

    def test_an_allowance_does_not_leak_to_another_protocol(self):
        """The v4 row must not be excused by a v6-only device group."""
        rows = [_row("BGP Peer", not_started=50)]
        failures = Ixia._protocols_summary_failures(rows, {"BGP+ Peer": 50})
        self.assertEqual(1, len(failures))
        self.assertIn("BGP Peer", failures[0])

    def test_any_session_down_fails(self):
        rows = [_row("IPv6", down=1)]
        failures = Ixia._protocols_summary_failures(rows, {"IPv6": 50})
        self.assertEqual(1, len(failures))
        self.assertIn("down", failures[0])

    def test_ptp_is_not_filtered_out(self):
        """PTP rows are no longer excluded; a PTP row down is a real failure."""
        rows = [_row("PTP", down=8)]
        failures = Ixia._protocols_summary_failures(rows, {})
        self.assertEqual(1, len(failures))
        self.assertIn("PTP", failures[0])

    def test_blank_stat_values_count_as_zero(self):
        rows = [{"Protocol Type": "IPv6", "Sessions Not Started": "", "Sessions Down": ""}]
        self.assertEqual([], Ixia._protocols_summary_failures(rows, {}))


class VerifyProtocolsTest(unittest.TestCase):
    def _ixia(self, rows_sequence: t.List[t.List[t.Dict[str, str]]]) -> Ixia:
        ix = _ixia_with_groups(
            [_dg(False, 50, "v6_addresses_config", "v6_bgp_config")]
        )
        ix.skip_ixia_protocol_verification = False
        ix.is_uhd_chassis = False
        ix.ixnetwork = MagicMock()
        self._snapshots = 0

        summary = MagicMock()
        remaining = list(rows_sequence)

        def _rows():
            self._snapshots += 1
            return remaining.pop(0) if len(remaining) > 1 else remaining[0]

        type(summary).Rows = property(lambda _self: _rows())
        self._summary = summary
        return ix

    def _run(self, ix: Ixia) -> None:
        with patch("taac.ixia.ixia.IxnStatViewAssistant", return_value=self._summary):
            ix.verify_protocols()

    def test_healthy_setup_passes_on_a_single_snapshot(self):
        """Every Rows access is a full CSV export (6+ min at scale), so the
        number of snapshots is the whole cost of this check."""
        ix = self._ixia([[_row("BGP+ Peer", not_started=50), _row("IPv4")]])
        self._run(ix)
        self.assertEqual(1, self._snapshots)

    def test_it_waits_for_sessions_to_come_up(self):
        ix = self._ixia(
            [[_row("IPv6", down=4)], [_row("IPv6", not_started=50)]]
        )
        with patch("taac.ixia.ixia.time.sleep"):
            self._run(ix)
        self.assertEqual(2, self._snapshots)

    def test_persistent_failure_raises_naming_the_protocol(self):
        ix = self._ixia([[_row("BGP Peer", down=3)]])
        with patch("taac.ixia.ixia.time.sleep"), patch(
            "taac.ixia.ixia.time.monotonic", side_effect=[0, 10_000, 20_000]
        ):
            with self.assertRaises(IxiaOperationTimeoutError) as caught:
                self._run(ix)
        self.assertIn("BGP Peer", str(caught.exception))

    def test_skip_flag_short_circuits(self):
        ix = self._ixia([[_row("BGP Peer", down=3)]])
        ix.skip_ixia_protocol_verification = True
        ix.ixia_protocol_verification_timeout = 0
        self._run(ix)
        self.assertEqual(0, self._snapshots)


if __name__ == "__main__":
    unittest.main()
