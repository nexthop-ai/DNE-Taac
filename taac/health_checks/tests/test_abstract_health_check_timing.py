# Copyright (c) Meta Platforms, Inc. and affiliates.

# pyre-unsafe
"""Unit tests for heal-latency instrumentation in AbstractPointInTimeHealthCheck.

Validates the always-on timing annotation (Part A of paste P2390924278)
and the opt-in post-verdict probe hook (Part B). Both must be
verdict-preserving — annotations may only enrich `message`.
"""

import typing as t
import unittest
from unittest.mock import MagicMock, patch

from taac.health_checks.abstract_health_check import (
    AbstractPointInTimeHealthCheck,
)
from taac.utils.oss_taac_lib_utils import ConsoleFileLogger
from taac.health_check.health_check import types as hc_types


class _ScriptedCheck(AbstractPointInTimeHealthCheck):
    """Test double that returns a scripted sequence of HealthCheckResults
    from _run() and an optional probe annotation string."""

    CHECK_NAME = hc_types.CheckName.BGP_RIB_FIB_CONSISTENCY_CHECK

    def __init__(
        self,
        logger,
        result_script: t.List[hc_types.HealthCheckResult],
        per_attempt_diff_script: t.Optional[t.List[t.Optional[int]]] = None,
        probe_annotation: t.Optional[str] = None,
        probe_raises: t.Optional[Exception] = None,
    ):
        super().__init__(logger=logger)
        self._result_script = list(result_script)
        self._diff_script = (
            list(per_attempt_diff_script) if per_attempt_diff_script is not None else []
        )
        self._probe_annotation = probe_annotation
        self._probe_raises = probe_raises
        self.probe_called_count = 0
        self.attempt_count = 0

    async def _run(self, obj, input, check_params):
        idx = self.attempt_count
        self.attempt_count += 1
        if self._diff_script and idx < len(self._diff_script):
            self._last_attempt_diff = self._diff_script[idx]
        return self._result_script[idx]

    async def _run_post_verdict_probe(self, obj, input, check_params, t0_monotonic):
        self.probe_called_count += 1
        if self._probe_raises is not None:
            raise self._probe_raises
        return self._probe_annotation


def _ok():
    return hc_types.HealthCheckResult(status=hc_types.HealthCheckStatus.PASS)


def _fail(msg: str = "diff"):
    return hc_types.HealthCheckResult(
        status=hc_types.HealthCheckStatus.FAIL, message=msg
    )


class AbstractHealthCheckTimingTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.logger = MagicMock(spec=ConsoleFileLogger)
        # No-op the everpaste shortening so message content survives intact
        # for assertions (network calls would otherwise fail in the
        # network_access=none test sandbox).
        self._shorten_patch = patch.object(
            AbstractPointInTimeHealthCheck,
            "_safe_shorten",
            new=lambda self_inner, msg, shorten_fburl=False: _identity(msg),
        )
        self._shorten_patch.start()
        # Avoid awaiting real sleeps on retry paths.
        self._sleep_patch = patch(
            "neteng.test_infra.dne.taac.health_checks.abstract_health_check.asyncio.sleep",
            new=_noop_sleep,
        )
        self._sleep_patch.start()

    def tearDown(self):
        self._shorten_patch.stop()
        self._sleep_patch.stop()

    async def test_pass_first_try_no_timing_annotation(self):
        """First-try PASS is the common path — no annotation appended."""
        check = _ScriptedCheck(self.logger, result_script=[_ok()])
        result = await check.run(
            obj=MagicMock(), input=None, default_input=None, check_params={}
        )
        self.assertEqual(result.status, hc_types.HealthCheckStatus.PASS)
        self.assertNotIn("[timing:", result.message or "")
        self.assertEqual(check.probe_called_count, 0)

    async def test_pass_on_retry_annotates_attempts(self):
        """Pass-on-retry records attempts_to_pass + elapsed in message."""
        check = _ScriptedCheck(
            self.logger,
            result_script=[_fail("attempt1"), _fail("attempt2"), _ok()],
        )
        result = await check.run(
            obj=MagicMock(),
            input=None,
            default_input=None,
            check_params={
                "retry_count": 3,
                "retry_delay_seconds": 0,
                "retry_delay_multiplier": 1.0,
            },
        )
        self.assertEqual(result.status, hc_types.HealthCheckStatus.PASS)
        self.assertIn("[timing:", result.message)
        self.assertIn("passed@attempt=3", result.message)
        # Probe must not fire on PASS.
        self.assertEqual(check.probe_called_count, 0)

    async def test_fail_annotates_per_attempt_diff_trajectory(self):
        """FAIL records attempts_used + final_diff + per_attempt_diff[]."""
        check = _ScriptedCheck(
            self.logger,
            result_script=[_fail(), _fail(), _fail()],
            per_attempt_diff_script=[500, 250, 100],
        )
        result = await check.run(
            obj=MagicMock(),
            input=None,
            default_input=None,
            check_params={
                "retry_count": 2,
                "retry_delay_seconds": 0,
                "retry_delay_multiplier": 1.0,
            },
        )
        self.assertEqual(result.status, hc_types.HealthCheckStatus.FAIL)
        self.assertIn("[timing: failed attempts=3", result.message)
        self.assertIn("final_diff=100", result.message)
        self.assertIn("per_attempt_diff=[500,250,100]", result.message)

    async def test_probe_invoked_on_fail_and_annotation_appended(self):
        """Probe fires after FAIL verdict and its annotation is appended."""
        check = _ScriptedCheck(
            self.logger,
            result_script=[_fail("base-msg")],
            probe_annotation="[heal_probe: heal_latency_sec=12.3]",
        )
        result = await check.run(
            obj=MagicMock(), input=None, default_input=None, check_params={}
        )
        self.assertEqual(result.status, hc_types.HealthCheckStatus.FAIL)
        self.assertEqual(check.probe_called_count, 1)
        # Both timing + probe annotations present.
        self.assertIn("[timing: failed", result.message)
        self.assertIn("[heal_probe: heal_latency_sec=12.3]", result.message)
        # Original message preserved.
        self.assertIn("base-msg", result.message)

    async def test_probe_not_invoked_on_pass(self):
        """Probe never fires on PASS — its only purpose is FAIL classification."""
        check = _ScriptedCheck(
            self.logger,
            result_script=[_ok()],
            probe_annotation="[heal_probe: heal_latency_sec=12.3]",
        )
        result = await check.run(
            obj=MagicMock(), input=None, default_input=None, check_params={}
        )
        self.assertEqual(result.status, hc_types.HealthCheckStatus.PASS)
        self.assertEqual(check.probe_called_count, 0)

    async def test_probe_exception_does_not_alter_verdict(self):
        """A probe that raises must not change the FAIL verdict."""
        check = _ScriptedCheck(
            self.logger,
            result_script=[_fail("base-msg")],
            probe_raises=RuntimeError("probe boom"),
        )
        result = await check.run(
            obj=MagicMock(), input=None, default_input=None, check_params={}
        )
        self.assertEqual(result.status, hc_types.HealthCheckStatus.FAIL)
        # No heal_probe annotation appended.
        self.assertNotIn("heal_probe", result.message or "")
        # Original message preserved.
        self.assertIn("base-msg", result.message)


async def _noop_sleep(_seconds):
    return None


async def _identity(msg):
    return msg
