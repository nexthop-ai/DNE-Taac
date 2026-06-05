# (c) Meta Platforms, Inc. and affiliates. Confidential and proprietary.

# pyre-unsafe

import json
import time
import typing as t

from taac.constants import TestDevice
from taac.health_checks.abstract_health_check import (
    AbstractDeviceHealthCheck,
)
from taac.libs.fpf.fpf_collector_registry import (
    DEFAULT_SIGNAL1_E2E_MAX_SEC,
    DEFAULT_SIGNAL2_LOCAL_MAX_SEC,
    DEFAULT_SIGNAL3_STABILITY_DURATION_SEC,
    evaluate_three_signals,
    get_collector,
    get_test_case_start_time,
)
from taac.libs.fpf.fpf_stress_checks import _parse_ts
from taac.health_check.health_check import types as hc_types

JSONL_PATH = "/tmp/fpf_stress_hrt_bulk.jsonl"


class FpfHrtBulkConvergenceHealthCheck(
    AbstractDeviceHealthCheck[hc_types.BaseHealthCheckIn]
):
    """Postcheck: evaluate HRT bulk prefix convergence from collector data.

    When ``use_live_collectors`` is True in check_params, queries the live
    HRT collector via the module-level registry using
    ``window_start``/``window_end`` timestamps for time-windowed assessment.

    Otherwise falls back to reading ``/tmp/fpf_stress_hrt_bulk.jsonl``.
    """

    CHECK_NAME = hc_types.CheckName.FPF_HRT_BULK_CONVERGENCE_CHECK
    CHECK_SCOPE = hc_types.Scope.DEFAULT
    OPERATING_SYSTEMS = ["FBOSS"]

    async def _run(
        self,
        obj: TestDevice,
        input: hc_types.BaseHealthCheckIn,
        check_params: t.Dict[str, t.Any],
    ) -> hc_types.HealthCheckResult:
        lanes: t.List[int] = check_params.get("lanes", [0, 1])
        expected_per_lane: t.Dict[int, int] = {
            int(k): v for k, v in check_params.get("expected_per_lane", {}).items()
        }
        if not expected_per_lane:
            expected_per_lane = {lane: int(20000) for lane in lanes}
        use_live = check_params.get("use_live_collectors", False)

        if use_live:
            return self._evaluate_from_live_collector(
                lanes, expected_per_lane, check_params
            )

        return self._evaluate_from_jsonl(lanes, expected_per_lane, check_params)

    def _evaluate_from_live_collector(
        self,
        lanes: t.List[int],
        expected_per_lane: t.Dict[int, int],
        check_params: t.Dict[str, t.Any],
    ) -> hc_types.HealthCheckResult:
        collector = get_collector("hrt")
        if collector is None:
            return hc_types.HealthCheckResult(
                status=hc_types.HealthCheckStatus.SKIP,
                message="No live HRT collector in registry",
            )

        window_end = check_params.get("window_end", time.time())
        tc_start = get_test_case_start_time()
        lookback_sec = check_params.get("lookback_sec", 900)
        window_start = check_params.get(
            "window_start", tc_start if tc_start else window_end - lookback_sec
        )

        self.logger.info(
            f"  [HRT bulk live] Evaluating window: "
            f"{window_start:.0f} to {window_end:.0f} "
            f"({window_end - window_start:.0f}s span)"
        )

        signal1_max = check_params.get(
            "signal1_e2e_max_sec", DEFAULT_SIGNAL1_E2E_MAX_SEC
        )
        signal2_max = check_params.get(
            "signal2_local_max_sec", DEFAULT_SIGNAL2_LOCAL_MAX_SEC
        )
        signal3_duration = check_params.get(
            "signal3_stability_duration_sec", DEFAULT_SIGNAL3_STABILITY_DURATION_SEC
        )

        per_lane_results = collector.evaluate_per_lane_window(
            window_start=window_start,
            window_end=window_end,
            lanes=lanes,
            expected_per_lane=expected_per_lane,
        )

        for i, r in enumerate(per_lane_results):
            per_lane_results[i] = evaluate_three_signals(
                result=r,
                collector=collector,
                window_start=window_start,
                window_end=window_end,
                expected=expected_per_lane.get(r.lane, 0),
                signal1_e2e_max_sec=signal1_max,
                signal2_local_max_sec=signal2_max,
                signal3_stability_duration_sec=signal3_duration,
                lane_id=r.lane,
            )

        for r in per_lane_results:
            overall = "PASS" if r.passed else "FAIL"
            self.logger.info(
                f"  [HRT bulk live] Lane {r.lane}: [{overall}] — 3-signal evaluation"
            )
            self.logger.info(
                f"    Signal 1 — E2E convergence "
                f"(≤{r.signal1_e2e_threshold_sec:.0f}s from test case start): "
                f"[{'PASS' if r.signal1_e2e_ok else 'FAIL'}] {r.signal1_e2e_detail}"
            )
            self.logger.info(
                f"    Signal 2 — GTSW/GPU propagation "
                f"(≤{r.signal2_local_threshold_sec:.0f}s from first non-zero to threshold): "
                f"[{'PASS' if r.signal2_local_ok else 'FAIL'}] {r.signal2_local_detail}"
            )
            self.logger.info(
                f"    Signal 3 — Post-conv stability "
                f"({r.signal3_stability_duration_sec:.0f}s held at threshold, no drops): "
                f"[{'PASS' if r.signal3_stability_ok else 'FAIL'}] {r.signal3_stability_detail}"
            )

        failures = [r for r in per_lane_results if not r.passed]

        timeout_count = collector.timeout_count_in_window(window_start, window_end)
        if timeout_count > 0:
            return hc_types.HealthCheckResult(
                status=hc_types.HealthCheckStatus.FAIL,
                message=(
                    f"Got null data — {timeout_count} poll timeout(s) in window "
                    f"[{window_start:.0f}, {window_end:.0f}]"
                ),
            )

        if failures:
            fail_summary = "; ".join(f"Lane {r.lane}: {r.detail}" for r in failures)
            return hc_types.HealthCheckResult(
                status=hc_types.HealthCheckStatus.FAIL,
                message=fail_summary,
            )
        pass_summary = " | ".join(
            f"Lane {r.lane}: E2E={r.signal1_e2e_sec}s, "
            f"GTSW-prop={r.signal2_local_sec}s, "
            f"stable={r.signal3_stability_duration_sec:.0f}s"
            for r in per_lane_results
        )
        return hc_types.HealthCheckResult(
            status=hc_types.HealthCheckStatus.PASS,
            message=f"All lanes passed 3-signal evaluation — {pass_summary}",
        )

    def _evaluate_from_jsonl(
        self,
        lanes: t.List[int],
        expected_per_lane: t.Dict[int, int],
        check_params: t.Dict[str, t.Any],
    ) -> hc_types.HealthCheckResult:
        jsonl_path = check_params.get("jsonl_path", JSONL_PATH)
        trigger_delay_sec = check_params.get("trigger_delay_sec", 120)

        try:
            with open(jsonl_path) as f:
                rows = [json.loads(line) for line in f if line.strip()]
        except FileNotFoundError:
            return hc_types.HealthCheckResult(
                status=hc_types.HealthCheckStatus.SKIP,
                message=f"JSONL file not found: {jsonl_path}",
            )

        if not rows:
            return hc_types.HealthCheckResult(
                status=hc_types.HealthCheckStatus.SKIP,
                message="JSONL file is empty",
            )

        first_ts = _parse_ts(rows[0]["timestamp"]).timestamp()
        trigger_ts = first_ts + trigger_delay_sec

        results = [
            self._evaluate_lane(
                lane_id, expected_per_lane.get(lane_id, 0), rows, trigger_ts
            )
            for lane_id in sorted(lanes)
        ]

        failures = [r for r in results if not r[1]]
        for lane_id, passed, _actual, _conv, detail in results:
            status = "PASS" if passed else "FAIL"
            self.logger.info(f"  [HRT bulk] Lane {lane_id}: [{status}] {detail}")

        if failures:
            fail_summary = "; ".join(f"Lane {r[0]}: {r[4]}" for r in failures)
            return hc_types.HealthCheckResult(
                status=hc_types.HealthCheckStatus.FAIL,
                message=fail_summary,
            )
        pass_summary = "; ".join(f"Lane {r[0]}: {r[3]}s" for r in results)
        return hc_types.HealthCheckResult(
            status=hc_types.HealthCheckStatus.PASS,
            message=f"All lanes converged — {pass_summary}",
        )

    def _evaluate_lane(
        self,
        lane_id: int,
        expected: int,
        rows: t.List[t.Dict[str, t.Any]],
        trigger_ts: float,
    ) -> t.Tuple[int, bool, int, t.Optional[float], str]:
        if expected == 0:
            return (lane_id, True, 0, None, "no threshold set")

        convergence_sec = None
        last_actual = 0
        for r in rows:
            lane_counts = r.get("lane_counts", [])
            if lane_id >= len(lane_counts):
                continue
            try:
                row_ts = _parse_ts(r["timestamp"]).timestamp()
            except ValueError:
                continue
            count = lane_counts[lane_id]
            last_actual = count
            if count >= expected and convergence_sec is None:
                convergence_sec = round(row_ts - trigger_ts, 1)

        passed = convergence_sec is not None
        detail = (
            f"reached {expected} in {convergence_sec}s"
            if passed
            else f"only reached {last_actual}/{expected}"
        )
        return (lane_id, passed, last_actual, convergence_sec, detail)
