#!/usr/bin/env python3
# (c) Meta Platforms, Inc. and affiliates. Confidential and proprietary.

# pyre-unsafe

"""
Continuous-polling health check collectors for FPF stress tests.

Three collector classes that run as background asyncio tasks, writing
timestamped rows to both an in-memory list (for post-processing) and
a tmp file (for human readability). After the trigger + wait period,
each collector's evaluate() method assesses pass/fail against thresholds.

Collectors:
  FsdbRibmapCollector  — polls FSDB ribMap prefix counts per GTSW
  HrtBulkCollector     — polls HRT getPrefixTable per-lane counts per host
  BgpRibCollector      — polls BGP RIB prefix counts per GTSW
"""

import asyncio
import atexit
import ipaddress
import json
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from neteng.netcastle.logger import get_root_logger
from taac.internal.driver.fboss_switch_internal import (
    FbossSwitchInternal,
)
from neteng.test_infra.dne.taac.libs.fpf.fpf_bgp_rib import _count_matching, get_bgp_rib
from taac.libs.fpf.fpf_fsdb_ribmap import get_fsdb_rib_map
from taac.libs.fpf.fpf_hrt_bulk_tracker import (
    count_failed_per_lane,
    count_per_lane,
    NUM_LANES,
)
from taac.libs.fpf.fpf_hrt_polling import get_hrt_client


logger = get_root_logger()


def _now_str() -> str:
    return datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M:%S.%f")[
        :-3
    ] + datetime.now(timezone.utc).astimezone().strftime("%z")


def _parse_ts(ts_str: str) -> datetime:
    """Parse a timestamp string like '2026-05-19 22:36:32.560-0700'."""
    for fmt in ["%Y-%m-%d %H:%M:%S.%f%z", "%Y-%m-%d %H:%M:%S%z"]:
        try:
            return datetime.strptime(ts_str, fmt)
        except ValueError:
            continue
    raise ValueError(f"Cannot parse timestamp: {ts_str}")


# ---------------------------------------------------------------------------
# Lane mapping: lane N → STSW stsw001.s00{N+1}, GTSW gtsw00{N+1}.l1002
# ---------------------------------------------------------------------------

STSW_TEMPLATE = "stsw001.s{plane:03d}.l202.mwg2"
GTSW_TEMPLATE = "gtsw{plane:03d}.l1002.c087.mwg2"


def lanes_to_stsws(lanes: List[int]) -> List[str]:
    return [STSW_TEMPLATE.format(plane=lane + 1) for lane in lanes]


def lanes_to_gtsws(lanes: List[int]) -> List[str]:
    return [GTSW_TEMPLATE.format(plane=lane + 1) for lane in lanes]


# ---------------------------------------------------------------------------
# Precheck: verify no test prefixes already exist
# ---------------------------------------------------------------------------


@dataclass
class PrecheckResult:
    device: str
    source: str
    matched: int
    total: int
    passed: bool
    error: str = ""


async def run_stress_precheck(
    trigger_devices: List[str],
    observer_gtsws: List[str],
    subnet_prefix: str,
) -> Tuple[bool, List[PrecheckResult]]:
    """Verify that no prefixes matching the test subnet already exist
    on the trigger (STSW) or observer (GTSW) devices. Returns (all_passed, results).

    Checks BGP RIB on trigger devices and FSDB ribMap on observer GTSWs.
    Any matched > 0 means stale test prefixes from a prior run — fail the precheck.
    Connection errors are treated as warnings (passed=True) since they indicate
    the service is down, not that stale prefixes exist.
    """
    subnet = ipaddress.IPv6Network(subnet_prefix, strict=False)

    async def _check_bgp_rib(device: str) -> PrecheckResult:
        try:
            rib_entries = await get_bgp_rib(device)
            total = len(rib_entries)
            matched = _count_matching(rib_entries, subnet, None)
            return PrecheckResult(
                device=device,
                source="BGP RIB",
                matched=matched,
                total=total,
                passed=matched == 0,
            )
        except Exception as e:
            return PrecheckResult(
                device=device,
                source="BGP RIB",
                matched=0,
                total=0,
                passed=True,
                error=str(e),
            )

    async def _check_fsdb_ribmap(gtsw: str) -> PrecheckResult:
        try:
            driver = FbossSwitchInternal(gtsw, logger)
            rib_map = await get_fsdb_rib_map(driver)
            total = len(rib_map) if isinstance(rib_map, dict) else 0
            matched = 0
            if isinstance(rib_map, dict):
                for prefix_str in rib_map:
                    try:
                        net = ipaddress.ip_network(prefix_str, strict=False)
                        if isinstance(net, ipaddress.IPv6Network) and net.subnet_of(
                            subnet
                        ):
                            matched += 1
                    except (ValueError, TypeError):
                        continue
            return PrecheckResult(
                device=gtsw,
                source="FSDB ribMap",
                matched=matched,
                total=total,
                passed=matched == 0,
            )
        except Exception as e:
            return PrecheckResult(
                device=gtsw,
                source="FSDB ribMap",
                matched=0,
                total=0,
                passed=True,
                error=str(e),
            )

    tasks = []
    for dev in trigger_devices:
        tasks.append(_check_bgp_rib(dev))
    for gtsw in observer_gtsws:
        tasks.append(_check_fsdb_ribmap(gtsw))
        tasks.append(_check_bgp_rib(gtsw))

    results = await asyncio.gather(*tasks)
    all_passed = all(r.passed for r in results)
    return all_passed, list(results)


# ---------------------------------------------------------------------------
# Data rows stored per collector
# ---------------------------------------------------------------------------


@dataclass
class RibmapRow:
    timestamp: str
    gtsw: str
    matched: int
    total: int
    notes: str = ""


@dataclass
class HrtBulkRow:
    timestamp: str
    host: str
    device_id: int
    lane_counts: List[int] = field(default_factory=lambda: [0] * NUM_LANES)
    unique: int = 0


@dataclass
class HrtRemoteFailureRow:
    timestamp: str
    host: str
    device_id: int
    lane_counts: List[int] = field(default_factory=lambda: [0] * NUM_LANES)
    unique: int = 0


@dataclass
class BgpRibRow:
    timestamp: str
    gtsw: str
    matched: int
    total: int
    notes: str = ""


@dataclass
class PerLaneResult:
    """Result of a per-lane/per-device evaluation.

    The base fields (lane, device, passed, expected, actual, convergence_sec,
    detail) capture the simple "did the threshold get reached" outcome.

    The ``signal*`` fields below capture the three-signal evaluation performed
    by ``evaluate_three_signals()`` in ``fpf_collector_registry``. Each signal
    is independent; the overall ``passed`` requires all three to pass.
    """

    lane: int
    device: str
    check_type: str
    passed: bool
    expected: int
    actual: int
    convergence_sec: Optional[float] = None
    detail: str = ""
    # Legacy fields (unused by current logic; kept for forward compat).
    sla_ok: Optional[bool] = None
    stability_ok: Optional[bool] = None
    stability_detail: str = ""
    # --- Three-signal evaluation outputs -----------------------------------
    # Signal 1: end-to-end convergence (window_start → first row at threshold)
    signal1_e2e_ok: Optional[bool] = None
    signal1_e2e_sec: Optional[float] = None
    signal1_e2e_threshold_sec: Optional[float] = None
    signal1_e2e_detail: str = ""
    # Signal 2: local propagation (T1 first-nonzero → T2 first-at-threshold)
    signal2_local_ok: Optional[bool] = None
    signal2_local_sec: Optional[float] = None
    signal2_local_threshold_sec: Optional[float] = None
    signal2_t1_sec_from_start: Optional[float] = None
    signal2_t2_sec_from_start: Optional[float] = None
    signal2_local_detail: str = ""
    # Signal 3: post-convergence stability (≥ threshold for stability_duration)
    signal3_stability_ok: Optional[bool] = None
    signal3_stability_duration_sec: Optional[float] = None
    signal3_stability_detail: str = ""


# ---------------------------------------------------------------------------
# Base collector
# ---------------------------------------------------------------------------


class BaseCollector:
    """Base for continuous-polling collectors.

    Subclasses implement _poll_once() to do one data collection cycle.
    The collector runs in a background daemon thread with its own event
    loop, so it survives across asyncio.run() boundaries (e.g. between
    setup tasks and playbook execution in the TAAC framework).
    """

    POLL_TIMEOUT_SEC: float = 120.0

    def __init__(self, tmp_path: str, interval_sec: float = 2.0) -> None:
        self.tmp_path = tmp_path
        self.json_path = tmp_path.replace(".log", ".jsonl")
        self.interval_sec = interval_sec
        self._task: Optional[asyncio.Task] = None
        self._stop_flag = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._thread_loop: Optional[asyncio.AbstractEventLoop] = None
        self.rows: List = []
        self.timeout_timestamps: List[float] = []
        self._file: Any = None
        self._json_file: Any = None
        self._append_mode: bool = False

    def set_append_mode(self, enabled: bool = True) -> None:
        self._append_mode = enabled

    def _write_header(self, f) -> None:
        pass

    def _write_json_row(self, row_dict: Dict) -> None:
        self._json_file.write(json.dumps(row_dict) + "\n")
        self._json_file.flush()

    async def _poll_once(self) -> None:
        raise NotImplementedError

    async def _run_loop(self) -> None:
        mode = "a" if self._append_mode else "w"
        poll_timeout = self.POLL_TIMEOUT_SEC
        with open(self.tmp_path, mode) as f, open(self.json_path, mode) as jf:
            self._file = f
            self._json_file = jf
            if not self._append_mode or f.tell() == 0:
                f.write("=" * 100 + "\n")
                self._write_header(f)
                f.write("-" * 100 + "\n")
                f.flush()
            try:
                while not self._stop_flag.is_set():
                    try:
                        await asyncio.wait_for(self._poll_once(), timeout=poll_timeout)
                    except asyncio.TimeoutError:
                        self._record_null_poll(poll_timeout)
                    except asyncio.CancelledError:
                        break
                    except Exception as e:
                        logger.error(f"[{self.__class__.__name__}] poll error: {e}")
                    try:
                        await asyncio.sleep(self.interval_sec)
                    except asyncio.CancelledError:
                        break
            except asyncio.CancelledError:
                pass

    def _record_null_poll(self, poll_timeout: float) -> None:
        ts_str = _now_str()
        epoch = datetime.now(timezone.utc).timestamp()
        self.timeout_timestamps.append(epoch)
        logger.warning(
            f"[{self.__class__.__name__}] poll exceeded {poll_timeout:.0f}s — "
            f"recording NULL data point (input=null, output=null)"
        )
        if self._file is not None:
            try:
                self._file.write(
                    f"{ts_str:<34}  *** NULL DATA — poll timeout "
                    f"({poll_timeout:.0f}s) ***\n"
                )
                self._file.flush()
            except Exception:
                pass
        if self._json_file is not None:
            try:
                self._write_json_row(
                    {
                        "collector": self.__class__.__name__,
                        "timestamp": ts_str,
                        "input": None,
                        "output": None,
                        "notes": f"error: poll timeout ({poll_timeout:.0f}s) — null data",
                    }
                )
            except Exception:
                pass

    def had_timeout_in_window(self, window_start: float, window_end: float) -> bool:
        return any(window_start <= ts <= window_end for ts in self.timeout_timestamps)

    def timeout_count_in_window(self, window_start: float, window_end: float) -> int:
        return sum(
            1 for ts in self.timeout_timestamps if window_start <= ts <= window_end
        )

    def _thread_target(self) -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        self._thread_loop = loop
        try:
            loop.run_until_complete(self._run_loop())
        finally:
            loop.close()

    def start(self) -> None:
        self._stop_flag.clear()
        self._thread = threading.Thread(
            target=self._thread_target,
            daemon=True,
            name=f"{self.__class__.__name__}-collector",
        )
        self._thread.start()
        atexit.register(self._atexit_stop)
        logger.info(f"[{self.__class__.__name__}] started, writing to {self.tmp_path}")

    def _cancel_thread_tasks(self) -> None:
        loop = self._thread_loop
        if loop is None or loop.is_closed():
            return

        def _cancel_all() -> None:
            for task in asyncio.all_tasks(loop):
                task.cancel()

        try:
            loop.call_soon_threadsafe(_cancel_all)
        except RuntimeError:
            pass

    def _atexit_stop(self) -> None:
        if self._stop_flag.is_set() and not (self._thread and self._thread.is_alive()):
            return
        self._stop_flag.set()
        self._cancel_thread_tasks()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)

    async def stop(self) -> None:
        self._stop_flag.set()
        self._cancel_thread_tasks()
        # Cache to a local so Pyre narrows the Optional[Thread] across
        # the join + post-join is_alive re-check.
        thread = self._thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=10)
            if thread.is_alive():
                logger.error(
                    f"[{self.__class__.__name__}] FAILED to stop within 10s — "
                    f"thread still alive (likely blocked in a network call). "
                    f"Daemon thread will die when the parent process exits."
                )
                return
        logger.info(f"[{self.__class__.__name__}] stopped")

    def get_rows_in_window(self, window_start: float, window_end: float) -> List:
        windowed = []
        for row in self.rows:
            try:
                row_ts = _parse_ts(row.timestamp).timestamp()
            except (ValueError, AttributeError):
                continue
            if window_start <= row_ts <= window_end:
                windowed.append(row)
        return windowed


# ---------------------------------------------------------------------------
# FSDB RibMap Collector
# ---------------------------------------------------------------------------


class FsdbRibmapCollector(BaseCollector):
    """Polls FSDB ribMap prefix counts matching a subnet filter per GTSW."""

    def __init__(
        self,
        gtsws: List[str],
        subnet_prefix: str,
        tmp_path: str = "/tmp/fpf_stress_fsdb_ribmap.log",
        interval_sec: float = 2.0,
        fsdb_mode: str = "canonical",
    ) -> None:
        super().__init__(tmp_path, interval_sec)
        self.gtsws = gtsws
        self.subnet = ipaddress.IPv6Network(subnet_prefix, strict=False)
        self.fsdb_mode = fsdb_mode
        self.rows: List[RibmapRow] = []

    def _write_header(self, f) -> None:
        f.write(
            f"{'timestamp':<34}  {'gtsw':<34}  {'matched':>8}  {'total':>8}  notes\n"
        )

    async def _poll_once(self) -> None:
        async def _one_gtsw(gtsw: str) -> RibmapRow:
            notes = ""
            try:
                driver = FbossSwitchInternal(gtsw, logger)
                rib_map = await get_fsdb_rib_map(driver, mode=self.fsdb_mode)
                total = len(rib_map) if isinstance(rib_map, dict) else 0
                matched = 0
                if isinstance(rib_map, dict):
                    for prefix_str in rib_map:
                        try:
                            net = ipaddress.ip_network(prefix_str, strict=False)
                            if isinstance(net, ipaddress.IPv6Network) and net.subnet_of(
                                self.subnet
                            ):
                                matched += 1
                        except (ValueError, TypeError):
                            continue
            except Exception as e:
                notes = f"error: {e}"
                matched = 0
                total = 0
            return RibmapRow(
                timestamp=_now_str(),
                gtsw=gtsw,
                matched=matched,
                total=total,
                notes=notes,
            )

        results = await asyncio.gather(*[_one_gtsw(g) for g in self.gtsws])
        for row in results:
            self.rows.append(row)
            line = f"{row.timestamp:<34}  {row.gtsw:<34}  {row.matched:>8}  {row.total:>8}  {row.notes}\n"
            self._file.write(line)
            self._write_json_row(
                {
                    "collector": "fsdb_ribmap",
                    "timestamp": row.timestamp,
                    "gtsw": row.gtsw,
                    "matched": row.matched,
                    "total": row.total,
                    "notes": row.notes,
                }
            )
        self._file.flush()

    def evaluate_per_device(
        self,
        trigger_time: datetime,
        lane_map: Dict[int, str],
        deadline_sec: int = 300,
        expected_matched: int = 20000,
    ) -> List[PerLaneResult]:
        """Per-GTSW evaluation. lane_map maps lane_id -> gtsw hostname.
        Connection errors (all rows for a GTSW have notes containing 'error')
        are treated as FAIL since the service is unresponsive.
        """
        trigger_ts = trigger_time.timestamp()
        results = []
        for lane_id, gtsw in sorted(lane_map.items()):
            device_rows = [r for r in self.rows if r.gtsw == gtsw]
            if not device_rows:
                results.append(
                    PerLaneResult(
                        lane=lane_id,
                        device=gtsw,
                        check_type="FSDB ribMap",
                        passed=False,
                        expected=expected_matched,
                        actual=0,
                        detail="no data collected",
                    )
                )
                continue

            all_errors = all(r.notes.startswith("error:") for r in device_rows)
            if all_errors:
                results.append(
                    PerLaneResult(
                        lane=lane_id,
                        device=gtsw,
                        check_type="FSDB ribMap",
                        passed=False,
                        expected=expected_matched,
                        actual=0,
                        detail=f"FSDB unresponsive (all {len(device_rows)} polls failed)",
                    )
                )
                continue

            convergence_sec = None
            first_met_ts = None
            last_matched = 0
            for row in device_rows:
                try:
                    row_ts = _parse_ts(row.timestamp).timestamp()
                except ValueError:
                    continue
                if (
                    not row.notes
                    and row.matched >= expected_matched
                    and first_met_ts is None
                ):
                    first_met_ts = row_ts
                    convergence_sec = round(row_ts - trigger_ts, 1)
                last_matched = row.matched

            passed = first_met_ts is not None
            results.append(
                PerLaneResult(
                    lane=lane_id,
                    device=gtsw,
                    check_type="FSDB ribMap",
                    passed=passed,
                    expected=expected_matched,
                    actual=last_matched,
                    convergence_sec=convergence_sec,
                    detail=(
                        f"reached {last_matched} in {convergence_sec}s"
                        if passed
                        else f"only reached {last_matched}/{expected_matched}"
                    ),
                )
            )
        return results

    def evaluate_per_device_window(
        self,
        window_start: float,
        window_end: float,
        lane_map: Dict[int, str],
        expected_matched: int = 70000,
    ) -> List[PerLaneResult]:
        """Time-windowed variant of evaluate_per_device.

        Filters rows to [window_start, window_end] then evaluates convergence
        using window_start as the trigger reference. Used by long-lived
        collectors where each test case queries its own time window.
        """
        trigger_time = datetime.fromtimestamp(window_start, tz=timezone.utc)
        windowed = self.get_rows_in_window(window_start, window_end)
        saved_rows = self.rows
        try:
            self.rows = windowed
            return self.evaluate_per_device(
                trigger_time=trigger_time,
                lane_map=lane_map,
                expected_matched=expected_matched,
            )
        finally:
            self.rows = saved_rows


# ---------------------------------------------------------------------------
# HRT Bulk Prefix Collector
# ---------------------------------------------------------------------------


class HrtBulkCollector(BaseCollector):
    """Polls HRT getPrefixTable per-lane counts for a supernet filter."""

    def __init__(
        self,
        hosts: List[str],
        device_ids: Optional[List[int]] = None,
        supernet: str = "5000:dd::/32",
        tmp_path: str = "/tmp/fpf_stress_hrt_bulk.log",
        interval_sec: float = 2.0,
    ) -> None:
        super().__init__(tmp_path, interval_sec)
        self.hosts = hosts
        self.device_ids = device_ids or [0]
        self.supernet = ipaddress.IPv6Network(supernet, strict=False)
        self.rows: List[HrtBulkRow] = []

    def _write_header(self, f) -> None:
        lane_hdr = "  ".join(f"L{i}" for i in range(NUM_LANES))
        f.write(
            f"{'timestamp':<28}  {'host':<24}  {'dev':>3}  {lane_hdr}    [unique]\n"
        )

    async def _poll_once(self) -> None:
        for host in self.hosts:
            for dev_id in self.device_ids:
                try:
                    client_ctx = await get_hrt_client(host)
                    async with client_ctx as client:
                        prefix_table = await client.getPrefixTable()
                    counts, total_unique = count_per_lane(
                        prefix_table, dev_id, self.supernet
                    )
                except Exception as e:
                    logger.error(f"[HrtBulkCollector] {host} dev{dev_id}: {e}")
                    counts = [0] * NUM_LANES
                    total_unique = 0

                row = HrtBulkRow(
                    timestamp=_now_str(),
                    host=host,
                    device_id=dev_id,
                    lane_counts=counts,
                    unique=total_unique,
                )
                self.rows.append(row)
                lane_str = "  ".join(f"{c:>5}" for c in counts)
                line = (
                    f"{row.timestamp:<28}  {row.host:<24}  {row.device_id:>3}  "
                    f"{lane_str}    [unique={row.unique}]\n"
                )
                self._file.write(line)
                self._write_json_row(
                    {
                        "collector": "hrt_bulk",
                        "timestamp": row.timestamp,
                        "host": row.host,
                        "device_id": row.device_id,
                        "lane_counts": row.lane_counts,
                        "unique": row.unique,
                    }
                )
        self._file.flush()

    def evaluate_per_lane(
        self,
        trigger_time: datetime,
        lanes: List[int],
        deadline_sec: int = 300,
        expected_per_lane: Optional[Dict[int, int]] = None,
    ) -> List[PerLaneResult]:
        """Per-lane evaluation with convergence timing."""
        if expected_per_lane is None:
            expected_per_lane = {lane: int(20000) for lane in lanes}
        trigger_ts = trigger_time.timestamp()
        results = []
        for lane_id in sorted(lanes):
            expected = expected_per_lane.get(lane_id, 0)
            if expected == 0:
                results.append(
                    PerLaneResult(
                        lane=lane_id,
                        device=f"HRT L{lane_id}",
                        check_type="HRT bulk",
                        passed=True,
                        expected=0,
                        actual=0,
                        detail="no threshold set",
                    )
                )
                continue

            convergence_sec = None
            last_actual = 0
            for row in self.rows:
                if lane_id >= len(row.lane_counts):
                    continue
                try:
                    row_ts = _parse_ts(row.timestamp).timestamp()
                except ValueError:
                    continue
                count = row.lane_counts[lane_id]
                last_actual = count
                if count >= expected and convergence_sec is None:
                    convergence_sec = round(row_ts - trigger_ts, 1)

            passed = convergence_sec is not None
            results.append(
                PerLaneResult(
                    lane=lane_id,
                    device=f"HRT L{lane_id}",
                    check_type="HRT bulk",
                    passed=passed,
                    expected=expected,
                    actual=last_actual,
                    convergence_sec=convergence_sec,
                    detail=(
                        f"reached {expected} in {convergence_sec}s"
                        if passed
                        else f"only reached {last_actual}/{expected}"
                    ),
                )
            )
        return results

    def evaluate_per_lane_window(
        self,
        window_start: float,
        window_end: float,
        lanes: List[int],
        expected_per_lane: Optional[Dict[int, int]] = None,
    ) -> List[PerLaneResult]:
        """Time-windowed variant of evaluate_per_lane."""
        trigger_time = datetime.fromtimestamp(window_start, tz=timezone.utc)
        windowed = self.get_rows_in_window(window_start, window_end)
        saved_rows = self.rows
        try:
            self.rows = windowed
            return self.evaluate_per_lane(
                trigger_time=trigger_time,
                lanes=lanes,
                expected_per_lane=expected_per_lane,
            )
        finally:
            self.rows = saved_rows


# ---------------------------------------------------------------------------
# BGP RIB Collector
# ---------------------------------------------------------------------------


class BgpRibCollector(BaseCollector):
    """Polls BGP RIB prefix counts matching a subnet filter per GTSW."""

    def __init__(
        self,
        gtsws: List[str],
        subnet_prefix: str,
        tmp_path: str = "/tmp/fpf_stress_bgp_rib.log",
        interval_sec: float = 2.0,
    ) -> None:
        super().__init__(tmp_path, interval_sec)
        self.gtsws = gtsws
        self.subnet = ipaddress.IPv6Network(subnet_prefix, strict=False)
        self.rows: List[BgpRibRow] = []

    def _write_header(self, f) -> None:
        f.write(
            f"{'timestamp':<34}  {'gtsw':<34}  {'matched':>8}  {'total':>8}  notes\n"
        )

    async def _poll_once(self) -> None:
        async def _one_gtsw(gtsw: str) -> BgpRibRow:
            notes = ""
            try:
                rib_entries = await get_bgp_rib(gtsw)
                total = len(rib_entries)
                matched = _count_matching(rib_entries, self.subnet, None)
            except Exception as e:
                notes = f"error: {e}"
                matched = 0
                total = 0
            return BgpRibRow(
                timestamp=_now_str(),
                gtsw=gtsw,
                matched=matched,
                total=total,
                notes=notes,
            )

        results = await asyncio.gather(*[_one_gtsw(g) for g in self.gtsws])
        for row in results:
            self.rows.append(row)
            line = f"{row.timestamp:<34}  {row.gtsw:<34}  {row.matched:>8}  {row.total:>8}  {row.notes}\n"
            self._file.write(line)
            self._write_json_row(
                {
                    "collector": "bgp_rib",
                    "timestamp": row.timestamp,
                    "gtsw": row.gtsw,
                    "matched": row.matched,
                    "total": row.total,
                    "notes": row.notes,
                }
            )
        self._file.flush()

    def evaluate_per_device(
        self,
        trigger_time: datetime,
        lane_map: Dict[int, str],
        deadline_sec: int = 300,
        expected_matched: int = 20000,
    ) -> List[PerLaneResult]:
        """Per-GTSW evaluation with convergence timing. Same pattern as
        FsdbRibmapCollector but queries BGP RIB (upstream of FSDB)."""
        trigger_ts = trigger_time.timestamp()
        results = []
        for lane_id, gtsw in sorted(lane_map.items()):
            device_rows = [r for r in self.rows if r.gtsw == gtsw]
            if not device_rows:
                results.append(
                    PerLaneResult(
                        lane=lane_id,
                        device=gtsw,
                        check_type="BGP RIB",
                        passed=False,
                        expected=expected_matched,
                        actual=0,
                        detail="no data collected",
                    )
                )
                continue

            all_errors = all(r.notes.startswith("error:") for r in device_rows)
            if all_errors:
                results.append(
                    PerLaneResult(
                        lane=lane_id,
                        device=gtsw,
                        check_type="BGP RIB",
                        passed=False,
                        expected=expected_matched,
                        actual=0,
                        detail=f"BGP unresponsive (all {len(device_rows)} polls failed)",
                    )
                )
                continue

            convergence_sec = None
            last_matched = 0
            for row in device_rows:
                try:
                    row_ts = _parse_ts(row.timestamp).timestamp()
                except ValueError:
                    continue
                if (
                    not row.notes
                    and row.matched >= expected_matched
                    and convergence_sec is None
                ):
                    convergence_sec = round(row_ts - trigger_ts, 1)
                last_matched = row.matched

            passed = convergence_sec is not None
            results.append(
                PerLaneResult(
                    lane=lane_id,
                    device=gtsw,
                    check_type="BGP RIB",
                    passed=passed,
                    expected=expected_matched,
                    actual=last_matched,
                    convergence_sec=convergence_sec,
                    detail=(
                        f"reached {last_matched} in {convergence_sec}s"
                        if passed
                        else f"only reached {last_matched}/{expected_matched}"
                    ),
                )
            )
        return results

    def evaluate_per_device_window(
        self,
        window_start: float,
        window_end: float,
        lane_map: Dict[int, str],
        expected_matched: int = 70000,
    ) -> List[PerLaneResult]:
        """Time-windowed variant of evaluate_per_device."""
        trigger_time = datetime.fromtimestamp(window_start, tz=timezone.utc)
        windowed = self.get_rows_in_window(window_start, window_end)
        saved_rows = self.rows
        try:
            self.rows = windowed
            return self.evaluate_per_device(
                trigger_time=trigger_time,
                lane_map=lane_map,
                expected_matched=expected_matched,
            )
        finally:
            self.rows = saved_rows


# ---------------------------------------------------------------------------
# HRT Remote Failure Collector
# ---------------------------------------------------------------------------


class HrtRemoteFailureCollector(BaseCollector):
    """Polls HRT getRemoteFailures() per-lane counts for a supernet filter.

    Measures negative-route (remote-failure) prefix counts per lane.
    In stable state all lanes read 0. After a drain, the drained lane's
    count rises to the injected prefix count.
    """

    def __init__(
        self,
        hosts: List[str],
        device_ids: Optional[List[int]] = None,
        supernet: str = "5000:dd::/32",
        tmp_path: str = "/tmp/fpf_stress_hrt_remote_failure.log",
        interval_sec: float = 2.0,
    ) -> None:
        super().__init__(tmp_path, interval_sec)
        self.hosts = hosts
        self.device_ids = device_ids or [0]
        self.supernet = ipaddress.IPv6Network(supernet, strict=False)
        self.rows: List[HrtRemoteFailureRow] = []

    def _write_header(self, f) -> None:
        lane_hdr = "  ".join(f"L{i}" for i in range(NUM_LANES))
        f.write(
            f"{'timestamp':<28}  {'host':<24}  {'dev':>3}  {lane_hdr}    [unique]\n"
        )

    async def _poll_once(self) -> None:
        for host in self.hosts:
            for dev_id in self.device_ids:
                try:
                    client_ctx = await get_hrt_client(host)
                    async with client_ctx as client:
                        remote_failures = await client.getRemoteFailures()
                    counts, total_unique = count_failed_per_lane(
                        remote_failures, dev_id, self.supernet
                    )
                except Exception as e:
                    logger.error(f"[HrtRemoteFailureCollector] {host} dev{dev_id}: {e}")
                    counts = [0] * NUM_LANES
                    total_unique = 0

                row = HrtRemoteFailureRow(
                    timestamp=_now_str(),
                    host=host,
                    device_id=dev_id,
                    lane_counts=counts,
                    unique=total_unique,
                )
                self.rows.append(row)
                lane_str = "  ".join(f"{c:>5}" for c in counts)
                line = (
                    f"{row.timestamp:<28}  {row.host:<24}  {row.device_id:>3}  "
                    f"{lane_str}    [unique={row.unique}]\n"
                )
                self._file.write(line)
                self._write_json_row(
                    {
                        "collector": "hrt_remote_failure",
                        "timestamp": row.timestamp,
                        "host": row.host,
                        "device_id": row.device_id,
                        "lane_counts": row.lane_counts,
                        "unique": row.unique,
                    }
                )
        self._file.flush()

    def evaluate_per_lane_drain(
        self,
        trigger_time: datetime,
        lanes: List[int],
        expected_per_lane: Optional[Dict[int, int]] = None,
        max_convergence_sec: int = 120,
    ) -> List[PerLaneResult]:
        """Drain direction: find 0->N transition per lane."""
        if expected_per_lane is None:
            expected_per_lane = {}
        results = []
        for lane_id in sorted(lanes):
            expected = expected_per_lane.get(lane_id, 0)
            if expected == 0:
                results.append(
                    PerLaneResult(
                        lane=lane_id,
                        device=f"HRT neg L{lane_id}",
                        check_type="HRT remote_failure drain",
                        passed=True,
                        expected=0,
                        actual=0,
                        detail="no threshold set",
                    )
                )
                continue

            t_last_zero: Optional[float] = None
            t_converge: Optional[float] = None
            last_actual = 0
            for row in self.rows:
                if lane_id >= len(row.lane_counts):
                    continue
                try:
                    row_ts = _parse_ts(row.timestamp).timestamp()
                except ValueError:
                    continue
                count = row.lane_counts[lane_id]
                last_actual = count
                # Only update t_last_zero before convergence — otherwise a later
                # recovery (count back to 0) would push t_last_zero past
                # t_converge and yield a negative convergence_sec.
                if count == 0 and t_converge is None:
                    t_last_zero = row_ts
                if count >= expected and t_converge is None and t_last_zero is not None:
                    t_converge = row_ts

            if t_converge is not None and t_last_zero is not None:
                convergence_sec = round(t_converge - t_last_zero, 1)
                passed = convergence_sec <= max_convergence_sec
                results.append(
                    PerLaneResult(
                        lane=lane_id,
                        device=f"HRT neg L{lane_id}",
                        check_type="HRT remote_failure drain",
                        passed=passed,
                        expected=expected,
                        actual=last_actual,
                        convergence_sec=convergence_sec,
                        detail=(
                            f"0->{expected} in {convergence_sec}s "
                            f"(SLA {max_convergence_sec}s)"
                        ),
                    )
                )
            else:
                results.append(
                    PerLaneResult(
                        lane=lane_id,
                        device=f"HRT neg L{lane_id}",
                        check_type="HRT remote_failure drain",
                        passed=False,
                        expected=expected,
                        actual=last_actual,
                        detail=f"never reached {expected} (last={last_actual})",
                    )
                )
        return results

    def evaluate_per_lane_recovery(
        self,
        trigger_time: datetime,
        lanes: List[int],
        expected_per_lane: Optional[Dict[int, int]] = None,
        max_convergence_sec: int = 120,
    ) -> List[PerLaneResult]:
        """Recovery direction: find N->0 transition per lane."""
        if expected_per_lane is None:
            expected_per_lane = {}
        results = []
        for lane_id in sorted(lanes):
            peak_expected = expected_per_lane.get(lane_id, 0)
            if peak_expected == 0:
                results.append(
                    PerLaneResult(
                        lane=lane_id,
                        device=f"HRT neg L{lane_id}",
                        check_type="HRT remote_failure recovery",
                        passed=True,
                        expected=0,
                        actual=0,
                        detail="no threshold set",
                    )
                )
                continue

            t_peak: Optional[float] = None
            t_recovered: Optional[float] = None
            last_actual = 0
            for row in self.rows:
                if lane_id >= len(row.lane_counts):
                    continue
                try:
                    row_ts = _parse_ts(row.timestamp).timestamp()
                except ValueError:
                    continue
                count = row.lane_counts[lane_id]
                last_actual = count
                if count >= peak_expected:
                    t_peak = row_ts
                    t_recovered = None
                if count == 0 and t_peak is not None and t_recovered is None:
                    t_recovered = row_ts

            if t_recovered is not None and t_peak is not None:
                convergence_sec = round(t_recovered - t_peak, 1)
                passed = convergence_sec <= max_convergence_sec
                results.append(
                    PerLaneResult(
                        lane=lane_id,
                        device=f"HRT neg L{lane_id}",
                        check_type="HRT remote_failure recovery",
                        passed=passed,
                        expected=0,
                        actual=last_actual,
                        convergence_sec=convergence_sec,
                        detail=(
                            f"{peak_expected}->0 in {convergence_sec}s "
                            f"(SLA {max_convergence_sec}s)"
                        ),
                    )
                )
            else:
                results.append(
                    PerLaneResult(
                        lane=lane_id,
                        device=f"HRT neg L{lane_id}",
                        check_type="HRT remote_failure recovery",
                        passed=False,
                        expected=0,
                        actual=last_actual,
                        detail=f"never recovered to 0 (last={last_actual})",
                    )
                )
        return results

    def evaluate_per_lane_stable(
        self,
        lanes: List[int],
    ) -> List[PerLaneResult]:
        """Stable-state: assert count stays 0 for every row in the window."""
        results = []
        for lane_id in sorted(lanes):
            max_seen = 0
            nonzero_count = 0
            total_rows = 0
            for row in self.rows:
                if lane_id >= len(row.lane_counts):
                    continue
                total_rows += 1
                count = row.lane_counts[lane_id]
                if count > max_seen:
                    max_seen = count
                if count != 0:
                    nonzero_count += 1

            passed = nonzero_count == 0
            results.append(
                PerLaneResult(
                    lane=lane_id,
                    device=f"HRT neg L{lane_id}",
                    check_type="HRT remote_failure stable",
                    passed=passed,
                    expected=0,
                    actual=max_seen,
                    convergence_sec=None,
                    detail=(
                        f"stable at 0 across {total_rows} samples"
                        if passed
                        else f"saw nonzero in {nonzero_count}/{total_rows} "
                        f"samples (max={max_seen})"
                    ),
                )
            )
        return results

    def evaluate_per_lane_window(
        self,
        window_start: float,
        window_end: float,
        lanes: List[int],
        expected_per_lane: Optional[Dict[int, int]] = None,
        direction: str = "drain",
        max_convergence_sec: int = 120,
    ) -> List[PerLaneResult]:
        """Time-windowed variant for use by health checks."""
        trigger_time = datetime.fromtimestamp(window_start, tz=timezone.utc)
        windowed = self.get_rows_in_window(window_start, window_end)
        saved_rows = self.rows
        try:
            self.rows = windowed
            if direction == "stable":
                return self.evaluate_per_lane_stable(lanes=lanes)
            if direction == "recovery":
                return self.evaluate_per_lane_recovery(
                    trigger_time=trigger_time,
                    lanes=lanes,
                    expected_per_lane=expected_per_lane,
                    max_convergence_sec=max_convergence_sec,
                )
            return self.evaluate_per_lane_drain(
                trigger_time=trigger_time,
                lanes=lanes,
                expected_per_lane=expected_per_lane,
                max_convergence_sec=max_convergence_sec,
            )
        finally:
            self.rows = saved_rows
