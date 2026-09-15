#!/usr/bin/env python3
# Copyright (c) Meta Platforms, Inc. and affiliates.

# pyre-unsafe

"""A precheck's default window is too narrow to contain a collector sample.

The runner stamps the test-case start immediately before prechecks run, so
``[test_case_start_time, now]`` comes out 0-1s wide while the collector polls
every 5s. Both measurement checks then found no sample and returned SKIP,
losing the check entirely -- and for most test configs the memory check is a
precheck only, so that was its only measurement.

The ODS path never had this problem: it sleeps before querying and widens any
window under 60s. These pin the collector-path equivalent.
"""

import typing as t
import unittest
from unittest.mock import MagicMock

from taac.health_checks.device_health_checks.cpu_utilization_health_check import (
    CpuUtilizationHealthCheck,
)
from taac.health_checks.device_health_checks.memory_utilization_health_check import (
    MemoryUtilizationHealthCheck,
)
from taac.libs.collectors.cpu_utilization_collector import CpuUtilizationCollector
from taac.libs.collectors.memory_utilization_collector import (
    MemoryUtilizationCollector,
)
from taac.libs.collectors.registry import (
    clear_collectors,
    register_collector,
    set_test_case_start_time,
)
from taac.health_check.health_check import types as hc_types


_HOST = "dut01"
_POLL_INTERVAL = 5.0
# Playbook start, as the runner stamps it just before prechecks run.
_TEST_CASE_START = 3000.0


def _seed(collector, epochs: t.Sequence[float], per_service) -> None:
    """Rows at ``epochs``, as a collector polling every 5s would have left."""
    for epoch in epochs:
        collector.rows.append(
            collector._make_sample(
                timestamp="",
                epoch=epoch,
                per_service=dict(per_service),
                notes="",
            )
        )


class TestCollectorWindowFloor(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        clear_collectors()
        self.device = MagicMock()
        self.device.name = _HOST
        # Every sample predates the playbook: the collector starts at test
        # setUp and the last poll lands before the precheck fires.
        self.epochs = [_TEST_CASE_START - 10.0, _TEST_CASE_START - 5.0]

    def tearDown(self) -> None:
        clear_collectors()

    async def _run_memory(self, window_end: float) -> hc_types.HealthCheckResult:
        collector = MemoryUtilizationCollector(
            driver=MagicMock(),
            services=["bgpd"],
            host=_HOST,
            interval_sec=_POLL_INTERVAL,
            tmp_path="/dev/null",
        )
        _seed(collector, self.epochs, {"bgpd": 1024})
        register_collector("memory_utilization", collector)
        set_test_case_start_time(_TEST_CASE_START)
        params = {"window_end": window_end}
        return await MemoryUtilizationHealthCheck(
            MagicMock()
        )._run_oss_via_collector(self.device, ["bgpd"], 0, {}, params)

    async def _run_cpu(self, window_end: float) -> hc_types.HealthCheckResult:
        collector = CpuUtilizationCollector(
            driver=MagicMock(),
            services=["bgpd"],
            host=_HOST,
            interval_sec=_POLL_INTERVAL,
            tmp_path="/dev/null",
        )
        _seed(collector, self.epochs, {"bgpd": 1.5})
        register_collector("cpu_utilization", collector)
        set_test_case_start_time(_TEST_CASE_START)
        params = {"window_end": window_end}
        return await CpuUtilizationHealthCheck(MagicMock())._run_oss_via_collector(
            self.device, ["bgpd"], 0, {}, params
        )

    async def test_memory_zero_width_precheck_window_evaluates(self) -> None:
        """window_end == test_case_start_time: the shape seen in the logs."""
        result = await self._run_memory(_TEST_CASE_START)
        self.assertEqual(result.status, hc_types.HealthCheckStatus.PASS)

    async def test_memory_one_second_precheck_window_evaluates(self) -> None:
        result = await self._run_memory(_TEST_CASE_START + 1.0)
        self.assertEqual(result.status, hc_types.HealthCheckStatus.PASS)

    async def test_cpu_zero_width_precheck_window_evaluates(self) -> None:
        result = await self._run_cpu(_TEST_CASE_START)
        self.assertEqual(result.status, hc_types.HealthCheckStatus.PASS)

    async def test_memory_still_skips_when_collector_has_no_samples(self) -> None:
        """The floor widens the window; it must not invent a verdict. A
        collector that has genuinely never polled still SKIPs."""
        self.epochs = []
        result = await self._run_memory(_TEST_CASE_START)
        self.assertEqual(result.status, hc_types.HealthCheckStatus.SKIP)


if __name__ == "__main__":
    unittest.main()
