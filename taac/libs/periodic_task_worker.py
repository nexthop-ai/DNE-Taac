# Copyright (c) Meta Platforms, Inc. and affiliates.
# pyre-unsafe
import asyncio
import logging
import multiprocessing
import sys
import time
import typing as t

from taac.constants import PeriodicCheckResult
from taac.ixia.taac_ixia import (  # oss-rewrite (force ShipIt re-export to taac.* root)
    TaacIxia as Ixia,
)
from taac.libs.parameter_evaluator import ParameterEvaluator
from taac.tasks.utils import get_task_obj
from taac.utils.common import async_everpaste_file
from taac.utils.oss_taac_lib_utils import ConsoleFileLogger
from taac.test_as_a_config import types as taac_types


# Per-test conveyor cadence can accumulate SyncManager server processes if
# they're not explicitly torn down between playbooks; the spawn handshake
# then races (EOFError at connection.recv) under FD/process-table pressure.
# Bounded retry is a cheap safety net on top of the explicit shutdown.
_MANAGER_INIT_RETRY_COUNT: int = 3
_MANAGER_INIT_RETRY_BACKOFF_S: float = 2.0


def _make_sync_manager(logger: ConsoleFileLogger) -> t.Any:
    """Construct multiprocessing.Manager() with bounded retry.

    Retries on EOFError / BrokenPipeError / ConnectionResetError / OSError
    raised by the SyncManager handshake when the server process dies before
    responding (typically under accumulated FD or process-table pressure).
    """
    last_exc: t.Optional[BaseException] = None
    for attempt in range(1, _MANAGER_INIT_RETRY_COUNT + 1):
        try:
            return multiprocessing.Manager()
        except (
            EOFError,
            OSError,
        ) as e:  # OSError covers BrokenPipeError + ConnectionResetError
            last_exc = e
            if attempt < _MANAGER_INIT_RETRY_COUNT:
                logger.warning(
                    f"multiprocessing.Manager() init failed "
                    f"(attempt {attempt}/{_MANAGER_INIT_RETRY_COUNT}): {e!r}; "
                    f"sleeping {_MANAGER_INIT_RETRY_BACKOFF_S}s before retry"
                )
                time.sleep(_MANAGER_INIT_RETRY_BACKOFF_S)
    assert last_exc is not None
    raise last_exc


class PeriodicTaskWorker:
    def __init__(
        self,
        periodic_task: taac_types.PeriodicTask,
        terminate_callback: t.Callable,
        main_logger: logging.Logger,
        ixia: t.Optional[Ixia] = None,
    ):
        self.logger = ConsoleFileLogger(multiprocessing.current_process().name)
        # pyre-fixme[16]: `ConsoleFileLogger` has no attribute `set_console_log_level`.
        self.logger.set_console_log_level(logging.CRITICAL + 1)
        self.periodic_task = periodic_task
        self.main_logger = main_logger
        self.terminate_callback = terminate_callback
        self.has_error = multiprocessing.Value("b", False)
        self._stop_requested = False
        self._log_everpaste_url: t.Optional[str] = None
        # Hold the SyncManager as an attribute so it can be explicitly shut
        # down by the executor between playbooks (see shutdown_manager).
        self._manager: t.Any = _make_sync_manager(self.logger)
        self.shared_data = self._manager.dict()
        self.shared_params = self._manager.dict()
        self.task_obj = get_task_obj(
            self.periodic_task.task,
            logger=self.logger,
            ixia=ixia,
            # pyrefly: ignore [bad-argument-type]
            shared_data=self.shared_data,
            # pyrefly: ignore [bad-argument-type]
            shared_params=self.shared_params,
        )

    def run(self) -> None:
        max_runtime = self.periodic_task.max_runtime or sys.maxsize
        start_time = time.time()
        success_count = 0

        while not self._stop_requested:
            if time.time() - start_time > max_runtime:
                break
            try:
                dict_params = ParameterEvaluator().evaluate(
                    self.periodic_task.params_list[
                        success_count % len(self.periodic_task.params_list)
                    ]
                    if self.periodic_task.params_list
                    else self.periodic_task.task.params
                )
                self.logger.info(
                    f"Running periodic task {self.periodic_task.name} with params {dict_params}"
                )
                asyncio.run(self.task_obj._run(dict_params))
                time.sleep(self.periodic_task.interval)
                success_count += 1
            except Exception as ex:
                self.logger.exception(f"Exception occurred in periodic task: {ex}")
                if self.periodic_task.retryable:
                    self.logger.info("Sleeping 60s before retrying periodic task")
                    time.sleep(self.periodic_task.exception_sleep_time)
                    continue
                elif self.periodic_task.terminate_on_error:
                    self.terminate_callback()
                self.has_error.value = True
                break

    async def run_final_check(self) -> PeriodicCheckResult:
        task_key = f"__{self.task_obj.__class__.NAME}__"
        prefix = f"{task_key}:"
        entry_count = sum(1 for k in self.shared_data.keys() if k.startswith(prefix))
        self.main_logger.debug(
            f"Periodic task '{task_key}': shared_data entries={entry_count}, "
            f"task_obj._data entries={len(self.task_obj._data)}"
        )
        return await self.task_obj.run_final_check()

    async def teardown(self) -> str:
        """
        Uploads the periodic task log to everpaste.

        Returns:
            The everpaste URL for the log file
        """
        # pyre-fixme[16]: `ConsoleFileLogger` has no attribute `get_log_file`.
        log_file = self.logger.get_log_file()
        everpaste_url = await async_everpaste_file(log_file)
        self.main_logger.info(
            f"Log for periodic task {self.periodic_task.name} has been everpasted to: {everpaste_url}"
        )
        # Store for access in run_final_check
        self._log_everpaste_url = everpaste_url
        return everpaste_url

    def stop(self) -> None:
        """Signal the worker to stop."""
        self._stop_requested = True

    def shutdown_manager(self) -> None:
        """Tear down the SyncManager server process. Idempotent.

        Must be called between playbooks. Otherwise each PeriodicTaskWorker
        leaks a SyncManager server process; after a few playbooks the
        accumulated FD/process pressure races the next Manager() spawn
        handshake (EOFError on connection.recv at __init__).
        """
        mgr = getattr(self, "_manager", None)
        if mgr is None:
            return
        try:
            mgr.shutdown()
        except Exception as e:
            # An already-dead manager raises on shutdown — that's fine, the
            # goal (no live server process) is already met.
            self.main_logger.debug(f"PeriodicTaskWorker.shutdown_manager: {e!r}")
        finally:
            self._manager = None
