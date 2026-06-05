# (c) Meta Platforms, Inc. and affiliates. Confidential and proprietary.

# pyre-unsafe

"""Setup/teardown tasks for long-lived FPF hardening collectors.

FpfStartCollectorsTask: Starts 3 collectors (FSDB ribMap, HRT bulk, BGP RIB),
    waits 2 min for baseline data collection, then registers collectors in the
    module-level registry so health checks can query them.

FpfStopCollectorsTask: Stops all collectors, withdraws prefixes, and clears
    the registry.

Prefix injection is NOT part of the setup task — it is done as a stage step
in the playbook so that the test case start time coincides with injection.

Usage in TestConfig:
    setup_tasks=[create_fpf_start_collectors_task(...)],
    teardown_tasks=[create_fpf_stop_collectors_task(...)],
"""

import asyncio
import typing as t

from taac.internal.driver.fboss_switch_internal import (
    FbossSwitchInternal,
)
from taac.libs.fpf.fpf_collector_registry import (
    clear_all,
    get_all_collectors,
    register_collector,
)
from taac.libs.fpf.fpf_stress_checks import (
    BgpRibCollector,
    FsdbRibmapCollector,
    HrtBulkCollector,
    HrtRemoteFailureCollector,
)
from taac.libs.fpf.inject_bgp_prefixes import (
    build_tip_prefix,
    expand_prefix_range,
    withdraw_prefixes,
)
from taac.tasks.base_task import BaseTask
from taac.utils.oss_taac_lib_utils import get_root_logger

logger = get_root_logger()

BASELINE_COLLECTION_SEC = 120


class FpfStartCollectorsTask(BaseTask):
    NAME = "fpf_start_collectors"

    async def run(self, params: t.Dict[str, t.Any]) -> None:
        gtsws: t.List[str] = params["gtsws"]
        hosts: t.List[str] = params["hosts"]
        subnet_prefix: str = params.get("subnet_prefix", "5000:dd::/32")
        poll_interval_sec: float = params.get("poll_interval_sec", 5.0)
        baseline_collection_sec: int = params.get(
            "baseline_collection_sec", BASELINE_COLLECTION_SEC
        )

        logger.info(
            f"[FpfStartCollectors] Starting collectors for {len(gtsws)} GTSWs, "
            f"{len(hosts)} hosts"
        )

        fsdb_collector = FsdbRibmapCollector(
            gtsws=gtsws,
            subnet_prefix=subnet_prefix,
            interval_sec=poll_interval_sec,
        )
        fsdb_collector.set_append_mode(True)

        hrt_collector = HrtBulkCollector(
            hosts=hosts,
            supernet=subnet_prefix,
            interval_sec=poll_interval_sec,
        )
        hrt_collector.set_append_mode(True)

        bgp_collector = BgpRibCollector(
            gtsws=gtsws,
            subnet_prefix=subnet_prefix,
            interval_sec=poll_interval_sec,
        )
        bgp_collector.set_append_mode(True)

        fsdb_collector.start()
        hrt_collector.start()
        hrt_remote_failure_collector = HrtRemoteFailureCollector(
            hosts=hosts,
            supernet=subnet_prefix,
            interval_sec=poll_interval_sec,
        )
        hrt_remote_failure_collector.set_append_mode(True)

        bgp_collector.start()
        hrt_remote_failure_collector.start()

        register_collector("fsdb", fsdb_collector)
        register_collector("hrt", hrt_collector)
        register_collector("bgp", bgp_collector)
        register_collector("hrt_remote_failure", hrt_remote_failure_collector)

        logger.info(
            f"[FpfStartCollectors] Collectors started. Waiting "
            f"{baseline_collection_sec}s for baseline data collection"
        )
        await asyncio.sleep(baseline_collection_sec)
        logger.info(
            "[FpfStartCollectors] Baseline collection complete, ready for test cases"
        )


class FpfStopCollectorsTask(BaseTask):
    NAME = "fpf_stop_collectors"

    async def run(self, params: t.Dict[str, t.Any]) -> None:
        trigger_stsws: t.List[str] = params["trigger_stsws"]
        prefix_count: int = params.get("prefix_count", 70000)
        prefix_base: str = params.get("prefix_base", "5000:dd::/64")
        increment_step: str = params.get("increment_step", "0:0:1::")
        # community_list is currently unused — withdraw_prefixes() doesn't
        # take it. Keep params.get() so callers can still pass it without
        # KeyError, but discard the value.
        _ = params.get("community_list", "stsw")

        collectors = get_all_collectors()

        try:
            for name, collector in collectors.items():
                logger.info(f"[FpfStopCollectors] Stopping {name} collector")
                try:
                    await asyncio.wait_for(collector.stop(), timeout=15)
                except asyncio.TimeoutError:
                    logger.error(
                        f"[FpfStopCollectors] {name}.stop() exceeded 15s — "
                        f"moving on; daemon thread will die with parent process"
                    )

            prefix_strs = expand_prefix_range(prefix_base, prefix_count, increment_step)
            tip_prefixes = [build_tip_prefix(p) for p in prefix_strs]

            logger.info(
                f"[FpfStopCollectors] Withdrawing {prefix_count} prefixes "
                f"from {len(trigger_stsws)} STSW devices"
            )

            async def _withdraw_on_device(device: str) -> None:
                driver = FbossSwitchInternal(hostname=device, logger=self.logger)
                await withdraw_prefixes(driver, tip_prefixes)

            await asyncio.gather(*[_withdraw_on_device(d) for d in trigger_stsws])
        finally:
            clear_all()
        logger.info("[FpfStopCollectors] All collectors stopped, prefixes withdrawn")
