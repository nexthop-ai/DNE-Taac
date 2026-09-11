# pyre-unsafe
"""Tasks that behave differently under TAAC_OSS=1."""
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

import taac.tasks.all as all_tasks
from taac.tasks.all import AllocateCgroupSliceMemory


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
