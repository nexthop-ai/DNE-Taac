# (c) Meta Platforms, Inc. and affiliates. Confidential and proprietary.

# pyre-unsafe
"""Unit tests for PeriodicTaskWorker manager lifecycle + retry helpers.

The PB3 EOFError in BAG010_Run_Time R117.10/R122.2/R139.2 traced to
SyncManager processes leaking across playbooks. These tests lock down the
two-layer fix:
  1. shutdown_manager() is idempotent and tears down the manager.
  2. _make_sync_manager() retries on transient connection/EOF errors.
"""

import multiprocessing
import unittest
from unittest.mock import MagicMock, patch

from taac.libs.periodic_task_worker import (
    _make_sync_manager,
    _MANAGER_INIT_RETRY_COUNT,
)


class MakeSyncManagerTest(unittest.TestCase):
    def test_returns_real_manager_in_happy_path(self):
        """No injection — the real spawn must succeed in a healthy harness."""
        logger = MagicMock()
        manager = _make_sync_manager(logger)
        try:
            d = manager.dict()
            d["k"] = "v"
            self.assertEqual(d["k"], "v")
        finally:
            manager.shutdown()
        logger.warning.assert_not_called()

    def test_retries_then_succeeds(self):
        """First call raises EOFError; second returns a real manager."""
        logger = MagicMock()
        real_manager = multiprocessing.Manager()
        call_count = {"n": 0}

        def fake_manager_factory():
            call_count["n"] += 1
            if call_count["n"] == 1:
                raise EOFError("simulated handshake EOF")
            return real_manager

        with (
            patch(
                "neteng.test_infra.dne.taac.libs.periodic_task_worker"
                ".multiprocessing.Manager",
                side_effect=fake_manager_factory,
            ),
            patch(
                "neteng.test_infra.dne.taac.libs.periodic_task_worker.time.sleep"
            ) as mock_sleep,
        ):
            result = _make_sync_manager(logger)

        try:
            self.assertIs(result, real_manager)
            self.assertEqual(call_count["n"], 2)
            logger.warning.assert_called_once()
            self.assertIn("attempt 1/", logger.warning.call_args[0][0])
            mock_sleep.assert_called_once()
        finally:
            real_manager.shutdown()

    def test_exhausts_retries_and_reraises(self):
        """All N attempts raise EOFError → final EOFError propagates."""
        logger = MagicMock()

        with (
            patch(
                "neteng.test_infra.dne.taac.libs.periodic_task_worker"
                ".multiprocessing.Manager",
                side_effect=EOFError("persistent failure"),
            ),
            patch("neteng.test_infra.dne.taac.libs.periodic_task_worker.time.sleep"),
        ):
            with self.assertRaises(EOFError):
                _make_sync_manager(logger)

        # N-1 retry warnings (the final attempt does not log a retry message
        # because it re-raises instead of backing off).
        self.assertEqual(logger.warning.call_count, _MANAGER_INIT_RETRY_COUNT - 1)

    def test_retries_on_broken_pipe_and_connection_reset(self):
        """Broken pipe and connection reset are treated the same as EOFError."""
        for exc_cls in (BrokenPipeError, ConnectionResetError, OSError):
            with self.subTest(exc_cls=exc_cls.__name__):
                self._assert_retry_recovers_from(exc_cls)

    def _assert_retry_recovers_from(self, exc_cls):
        logger = MagicMock()
        real_manager = multiprocessing.Manager()
        call_count = {"n": 0}

        def factory(cls=exc_cls, count=call_count, mgr=real_manager):
            count["n"] += 1
            if count["n"] == 1:
                raise cls("transient")
            return mgr

        with (
            patch(
                "neteng.test_infra.dne.taac.libs.periodic_task_worker"
                ".multiprocessing.Manager",
                side_effect=factory,
            ),
            patch("neteng.test_infra.dne.taac.libs.periodic_task_worker.time.sleep"),
        ):
            result = _make_sync_manager(logger)

        try:
            self.assertIs(result, real_manager)
            self.assertEqual(call_count["n"], 2)
        finally:
            real_manager.shutdown()


class PeriodicTaskWorkerShutdownManagerTest(unittest.TestCase):
    """Tests shutdown_manager idempotency without bringing up a real worker.

    PeriodicTaskWorker.__init__ requires a real PeriodicTask + Ixia surface
    that's painful to mock. The shutdown method is small and reads only
    `self._manager` + `self.main_logger`, so we exercise it on a bare
    instance built via __new__.
    """

    def _make_worker(self, manager):
        from taac.libs.periodic_task_worker import (
            PeriodicTaskWorker,
        )

        worker = PeriodicTaskWorker.__new__(PeriodicTaskWorker)
        worker._manager = manager
        worker.main_logger = MagicMock()
        return worker

    def test_shutdown_calls_manager_shutdown_then_clears_attr(self):
        manager = MagicMock()
        worker = self._make_worker(manager)

        worker.shutdown_manager()

        manager.shutdown.assert_called_once()
        self.assertIsNone(worker._manager)

    def test_shutdown_is_idempotent(self):
        manager = MagicMock()
        worker = self._make_worker(manager)

        worker.shutdown_manager()
        worker.shutdown_manager()  # second call: no-op

        manager.shutdown.assert_called_once()
        self.assertIsNone(worker._manager)

    def test_shutdown_swallows_exceptions_from_dead_manager(self):
        """Already-dead manager raises on shutdown — must not propagate."""
        manager = MagicMock()
        manager.shutdown.side_effect = RuntimeError("manager already dead")
        worker = self._make_worker(manager)

        # Should not raise.
        worker.shutdown_manager()

        self.assertIsNone(worker._manager)
        worker.main_logger.debug.assert_called_once()

    def test_shutdown_with_no_manager_attribute_is_noop(self):
        """Worker constructed without _manager (defensive): noop, no raise."""
        from taac.libs.periodic_task_worker import (
            PeriodicTaskWorker,
        )

        worker = PeriodicTaskWorker.__new__(PeriodicTaskWorker)
        worker.main_logger = MagicMock()

        worker.shutdown_manager()  # should not raise
