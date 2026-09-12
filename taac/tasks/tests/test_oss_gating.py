# pyre-unsafe
"""Tasks that behave differently under TAAC_OSS=1."""
import base64
import importlib
import inspect
import os
import typing as t
import unittest
from unittest.mock import AsyncMock, create_autospec, MagicMock, patch

import taac.tasks.all as all_tasks
from taac.driver.driver_constants import FbossSystemctlServiceName
from taac.tasks.all import (
    AllocateCgroupSliceMemory,
    AssertThriftRateLimitEnabledTask,
    CoopApplyPatchersTask,
)

# Same module split as taac/driver/tests/test_fboss_switch_coop_restart.py:
# the driver lives under neteng.* in the Meta tree.
FbossSwitch = importlib.import_module(
    "taac.driver.fboss_switch"
    if os.environ.get("TAAC_OSS", "").lower() in ("1", "true", "yes")
    else "neteng.test_infra.dne.taac.driver.fboss_switch"
).FbossSwitch


class OssGatingTest(unittest.IsolatedAsyncioTestCase):
    async def test_allocate_cgroup_slice_memory_is_a_no_op_under_oss(self) -> None:
        task = AllocateCgroupSliceMemory(hostname="crow242", logger=MagicMock())
        with (
            patch.object(all_tasks, "TAAC_OSS", True),
            patch.object(
                all_tasks, "async_get_device_driver", new_callable=AsyncMock
            ) as get_driver,
        ):
            await task.run({"hostname": "crow242", "slice_name": "workload"})
        get_driver.assert_not_awaited()
        task.logger.warning.assert_called_once()

    def test_thrift_rate_limit_probe_reads_the_oss_agent_config(self) -> None:
        for oss, expected in (
            (True, "/etc/coop/agent.conf"),
            (False, "/etc/coop/agent/current"),
        ):
            with patch.object(all_tasks, "TAAC_OSS", oss):
                self.assertEqual(AssertThriftRateLimitEnabledTask.agent_config_path(), expected)
                b64 = AssertThriftRateLimitEnabledTask._build_probe_cmd().split()[1]
                self.assertIn(expected, base64.b64decode(b64).decode())

    async def _run_oss_apply(
        self, params: dict, pending: list, apply_error: t.Optional[Exception] = None
    ) -> tuple:
        """Run CoopApplyPatchersTask under TAAC_OSS with a mocked driver.

        The driver is one parent mock so ``driver.mock_calls`` records every
        call in order -- the coldboot flag file has to land before the apply,
        which per-child assertions cannot express. It is autospecced against
        the real driver so a method the task calls cannot quietly disappear
        from FbossSwitch and leave these tests green.
        """
        task = CoopApplyPatchersTask(logger=MagicMock())
        driver = create_autospec(FbossSwitch, instance=True)
        if apply_error is not None:
            driver.async_apply_patchers.side_effect = apply_error
        with (
            patch.object(all_tasks, "TAAC_OSS", True),
            patch.object(
                all_tasks, "async_get_device_driver", new_callable=AsyncMock
            ) as get_driver,
            patch(
                "taac.driver.oss_coop_patcher.pending_configs", return_value=pending
            ),
        ):
            get_driver.return_value = driver
            if apply_error is not None:
                with self.assertRaises(type(apply_error)):
                    await task.run(params)
            else:
                await task.run(params)
        return driver, get_driver

    @staticmethod
    def _call_names(driver: AsyncMock) -> list:
        return [c[0] for c in driver.mock_calls if c[0]]

    async def test_coop_apply_patchers_warmboot_with_pending_agent_under_oss(self) -> None:
        driver, get_driver = await self._run_oss_apply(
            {"hostnames": ["crow242"], "do_warmboot": True}, ["agent", "bgpcpp"]
        )

        get_driver.assert_awaited_once_with("crow242")
        driver.async_create_cold_boot_file.assert_not_awaited()
        # The apply restarts the pending agent itself, but must not clear
        # can_warm_boot doing so or the warm boot becomes a cold one.
        driver.async_apply_patchers.assert_awaited_once_with(
            clear_agent_warm_boot=False
        )
        driver.async_restart_service.assert_not_awaited()
        driver.async_wait_for_agent_configured.assert_awaited_once()

    async def test_coop_apply_patchers_warmboot_without_pending_agent_under_oss(self) -> None:
        driver, get_driver = await self._run_oss_apply(
            {"hostnames": ["crow242"], "do_warmboot": True}, ["bgpcpp"]
        )

        get_driver.assert_awaited_once_with("crow242")
        driver.async_create_cold_boot_file.assert_not_awaited()
        driver.async_apply_patchers.assert_awaited_once_with(
            clear_agent_warm_boot=False
        )
        driver.async_restart_service.assert_awaited_once_with(
            FbossSystemctlServiceName.AGENT
        )
        driver.async_wait_for_agent_configured.assert_awaited_once()

    async def test_coop_apply_patchers_coldboot_under_oss(self) -> None:
        driver, get_driver = await self._run_oss_apply(
            {"hostnames": ["crow242"], "do_coldboot": True}, ["agent"]
        )

        get_driver.assert_awaited_once_with("crow242")
        driver.async_apply_patchers.assert_awaited_once_with(
            clear_agent_warm_boot=False
        )
        driver.async_restart_service.assert_not_awaited()
        driver.async_wait_for_agent_configured.assert_awaited_once()
        # The flag file is what makes the apply's restart a cold boot, so it
        # is only a cold boot if it exists before the restart.
        names = self._call_names(driver)
        self.assertLess(
            names.index("async_create_cold_boot_file"),
            names.index("async_apply_patchers"),
        )
        # ...and it must not outlive the boot it was created for.
        driver.async_remove_cold_boot_file.assert_awaited_once()
        self.assertLess(
            names.index("async_wait_for_agent_configured"),
            names.index("async_remove_cold_boot_file"),
        )

    async def test_coop_apply_patchers_coldboot_wins_over_warmboot_under_oss(self) -> None:
        driver, _ = await self._run_oss_apply(
            {"hostnames": ["crow242"], "do_warmboot": True, "do_coldboot": True},
            ["bgpcpp"],
        )

        driver.async_create_cold_boot_file.assert_awaited_once()
        driver.async_restart_service.assert_awaited_once_with(
            FbossSystemctlServiceName.AGENT
        )
        names = self._call_names(driver)
        self.assertLess(
            names.index("async_create_cold_boot_file"),
            names.index("async_restart_service"),
        )

    async def test_coop_apply_patchers_no_boot_flags_under_oss(self) -> None:
        driver, get_driver = await self._run_oss_apply(
            {"hostnames": ["crow242"]}, ["bgpcpp"]
        )

        get_driver.assert_awaited_once_with("crow242")
        driver.async_create_cold_boot_file.assert_not_awaited()
        # No boot requested: the apply keeps its default cold restart.
        driver.async_apply_patchers.assert_awaited_once_with(
            clear_agent_warm_boot=True
        )
        driver.async_restart_service.assert_not_awaited()
        driver.async_wait_for_agent_configured.assert_not_awaited()
        driver.async_remove_cold_boot_file.assert_not_awaited()

    async def test_coop_apply_patchers_covers_every_hostname_under_oss(self) -> None:
        driver, get_driver = await self._run_oss_apply(
            {"hostnames": ["crow242", "crow243"], "do_coldboot": True}, ["bgpcpp"]
        )

        self.assertEqual(
            [c.args[0] for c in get_driver.await_args_list], ["crow242", "crow243"]
        )
        self.assertEqual(driver.async_create_cold_boot_file.await_count, 2)
        self.assertEqual(driver.async_apply_patchers.await_count, 2)
        self.assertEqual(driver.async_restart_service.await_count, 2)
        self.assertEqual(driver.async_wait_for_agent_configured.await_count, 2)

    async def test_coop_apply_patchers_clears_the_cold_boot_flag_on_failure(
        self,
    ) -> None:
        """A flag left behind silently cold boots the next warm boot.

        The agent does not reliably delete it and /dev/shm outlives every
        restart, so the apply failing between create and boot is exactly how a
        later ``do_warmboot`` task stops being warm.
        """
        driver, _ = await self._run_oss_apply(
            {"hostnames": ["crow242"], "do_coldboot": True},
            ["agent"],
            apply_error=RuntimeError("activate failed"),
        )

        driver.async_create_cold_boot_file.assert_awaited_once()
        driver.async_remove_cold_boot_file.assert_awaited_once()
        driver.async_wait_for_agent_configured.assert_not_awaited()

    def test_apply_patchers_boot_kwarg_is_spelled_the_same_on_both_sides(
        self,
    ) -> None:
        """``async_apply_patchers`` absorbs ``**kwargs``, so a rename of this
        parameter would silently fall back to the cold-boot default instead of
        raising. Pin the name the task passes to the one the driver reads."""
        sig = inspect.signature(FbossSwitch.async_apply_patchers)
        self.assertIn("clear_agent_warm_boot", sig.parameters)
        self.assertIs(sig.parameters["clear_agent_warm_boot"].default, True)
