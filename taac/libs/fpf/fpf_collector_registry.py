# (c) Meta Platforms, Inc. and affiliates. Confidential and proprietary.

# pyre-unsafe

"""Module-level registry for long-lived FPF collectors and shared
3-signal convergence evaluation.

Two responsibilities:

1. **Registry** — stores collector instances + test case start time so health
   checks can query time-windowed convergence data without needing access to
   shared_task_data or the TaacRunner. Populated by
   FpfStartCollectorsTask and cleared by FpfStopCollectorsTask.

2. **3-signal evaluation** — ``evaluate_three_signals()`` is a shared function
   used by the FSDB-ribMap, BGP-RIB, and HRT-bulk convergence health checks.
   It decorates a basic ``PerLaneResult`` with three independent signal
   evaluations, and only marks the result as passed when all three pass.

   Signal 1 — End-to-end convergence (default ≤ 180s):
       window_start (≈ test case start) → first sample reaching ``expected``.
       Bounds the total user-visible time for "trigger fires → system done".

   Signal 2 — Local / GTSW-GPU propagation (default ≤ 120s):
       T1 (first non-zero sample) → T2 (first sample reaching ``expected``).
       Excludes the stimulus push duration (e.g., addNetworks() time) so it
       reports how fast the data plane actually catches up once it has work
       to do.

   Signal 3 — Post-convergence stability (default 60s, no drops):
       Beginning at T2, every subsequent sample within
       ``stability_duration_sec`` must show ``>= expected``. Catches churn,
       flap, or premature withdrawal.

   Health check defaults can be overridden per call via ``check_params``.
"""

import typing as t

from taac.libs.fpf.fpf_stress_checks import (
    _parse_ts,
    PerLaneResult,
)


_collectors: t.Dict[str, t.Any] = {}
_test_case_start_time: float = 0.0

# Signal 1: end-to-end convergence ceiling. Includes any stimulus push
# duration. 180s allows ~110s for 10k-prefix injection + ~70s propagation.
DEFAULT_SIGNAL1_E2E_MAX_SEC: float = 180.0

# Signal 2: local propagation ceiling. Measures pure data-plane catch-up.
DEFAULT_SIGNAL2_LOCAL_MAX_SEC: float = 120.0

# Signal 3: required post-convergence stability duration. The signal must
# remain >= expected continuously across this window after first reaching it.
DEFAULT_SIGNAL3_STABILITY_DURATION_SEC: float = 60.0

# Fraction of stability_duration that is acceptable when the window ends
# before the full duration elapses (gives partial credit so tests don't fail
# purely because their soak window is short relative to the stability check).
DEFAULT_STABILITY_PARTIAL_CREDIT_FRACTION: float = 0.8


def set_test_case_start_time(ts: float) -> None:
    global _test_case_start_time
    _test_case_start_time = ts


def get_test_case_start_time() -> float:
    return _test_case_start_time


def register_collector(name: str, collector: t.Any) -> None:
    _collectors[name] = collector


def get_collector(name: str) -> t.Optional[t.Any]:
    return _collectors.get(name)


def get_all_collectors() -> t.Dict[str, t.Any]:
    return dict(_collectors)


def clear_all() -> None:
    global _test_case_start_time
    _collectors.clear()
    _test_case_start_time = 0.0


def _row_matches_device(row: t.Any, device: str) -> bool:
    # Match by `gtsw` for FSDB/BGP rows, by `host` for HRT rows (so per-lane
    # checks don't merge samples across hosts). Fall through to True only if
    # the row carries no device-identifying field.
    if hasattr(row, "gtsw"):
        return row.gtsw == device
    if hasattr(row, "host"):
        return row.host == device
    return True


def _row_value(
    row: t.Any, lane_id: t.Optional[int], match_field: str
) -> t.Optional[int]:
    if lane_id is not None and hasattr(row, "lane_counts"):
        lc = row.lane_counts
        return lc[lane_id] if lane_id < len(lc) else None
    if hasattr(row, "lane_counts") and lane_id is None:
        return None
    return getattr(row, match_field, None)


def _collect_sorted_samples(
    rows: t.Iterable[t.Any],
    device: str,
    lane_id: t.Optional[int],
    match_field: str,
) -> t.List[t.Tuple[float, int]]:
    """Filter rows for device, parse timestamps, sort chronologically."""
    samples: t.List[t.Tuple[float, int]] = []
    for row in rows:
        if not _row_matches_device(row, device):
            continue
        val = _row_value(row, lane_id, match_field)
        if val is None:
            continue
        try:
            row_ts = _parse_ts(row.timestamp).timestamp()
        except (ValueError, AttributeError):
            continue
        samples.append((row_ts, val))
    samples.sort(key=lambda x: x[0])
    return samples


def _find_t1_t2(
    samples: t.List[t.Tuple[float, int]], expected: int
) -> t.Tuple[t.Optional[float], t.Optional[float]]:
    """T1 = first sample > 0. T2 = first sample >= expected."""
    t1: t.Optional[float] = None
    t2: t.Optional[float] = None
    for ts, val in samples:
        if t1 is None and val > 0:
            t1 = ts
        if t2 is None and val >= expected:
            t2 = ts
        if t1 is not None and t2 is not None:
            break
    return t1, t2


def _eval_signal1_e2e(
    result: PerLaneResult,
    t2: t.Optional[float],
    window_start: float,
    expected: int,
    max_sec: float,
) -> None:
    result.signal1_e2e_threshold_sec = max_sec
    if t2 is None:
        result.signal1_e2e_ok = False
        result.signal1_e2e_sec = None
        result.signal1_e2e_detail = (
            f"FAIL — never reached {expected} (last seen: {result.actual})"
        )
        return
    sec = round(t2 - window_start, 1)
    result.signal1_e2e_sec = sec
    result.signal1_e2e_ok = sec <= max_sec
    verb = "reached" if result.signal1_e2e_ok else "took"
    result.signal1_e2e_detail = f"{verb} {expected} in {sec}s (limit: ≤{max_sec:.0f}s)"


def _eval_signal2_local(
    result: PerLaneResult,
    t1: t.Optional[float],
    t2: t.Optional[float],
    window_start: float,
    expected: int,
    max_sec: float,
) -> None:
    result.signal2_local_threshold_sec = max_sec
    if t1 is None:
        result.signal2_local_ok = False
        result.signal2_local_sec = None
        result.signal2_local_detail = (
            "FAIL — no T1 transition observed (signal stayed at 0 throughout window)"
        )
        return
    if t2 is None:
        result.signal2_local_ok = False
        result.signal2_local_sec = None
        result.signal2_t1_sec_from_start = round(t1 - window_start, 1)
        result.signal2_local_detail = (
            f"FAIL — T1 observed at +{result.signal2_t1_sec_from_start}s "
            f"but T2 (>= {expected}) never reached"
        )
        return
    sec = round(t2 - t1, 1)
    result.signal2_local_sec = sec
    result.signal2_t1_sec_from_start = round(t1 - window_start, 1)
    result.signal2_t2_sec_from_start = round(t2 - window_start, 1)
    result.signal2_local_ok = sec <= max_sec
    result.signal2_local_detail = (
        f"T2-T1 = {sec}s "
        f"(T1=+{result.signal2_t1_sec_from_start}s, "
        f"T2=+{result.signal2_t2_sec_from_start}s) "
        f"(limit: ≤{max_sec:.0f}s)"
    )


def _eval_signal3_stability(
    result: PerLaneResult,
    t2: t.Optional[float],
    samples: t.List[t.Tuple[float, int]],
    window_end: float,
    expected: int,
    duration_sec: float,
) -> None:
    result.signal3_stability_duration_sec = duration_sec
    if t2 is None:
        result.signal3_stability_ok = False
        result.signal3_stability_detail = (
            "SKIP — threshold never reached, stability not assessed"
        )
        return
    stability_end = t2 + duration_sec
    post_t2 = [(ts, v) for ts, v in samples if t2 <= ts <= stability_end]
    drops = [(ts, v) for ts, v in post_t2 if v < expected]
    available = min(window_end, stability_end) - t2
    partial_min = duration_sec * DEFAULT_STABILITY_PARTIAL_CREDIT_FRACTION
    if drops:
        first_drop_offset = round(drops[0][0] - t2, 1)
        result.signal3_stability_ok = False
        result.signal3_stability_detail = (
            f"FAIL — {len(drops)} drop(s) below {expected} within "
            f"{duration_sec:.0f}s of T2 "
            f"(first drop: {drops[0][1]} at T2+{first_drop_offset}s)"
        )
        return
    if available >= duration_sec:
        result.signal3_stability_ok = True
        result.signal3_stability_detail = (
            f"held at >= {expected} for {duration_sec:.0f}s "
            f"after T2 (no drops, {len(post_t2)} samples)"
        )
        return
    if available >= partial_min:
        result.signal3_stability_ok = True
        result.signal3_stability_detail = (
            f"held at >= {expected} for {available:.1f}s after T2 "
            f"(partial credit: window ended before full "
            f"{duration_sec:.0f}s, {len(post_t2)} samples)"
        )
        return
    result.signal3_stability_ok = False
    result.signal3_stability_detail = (
        f"FAIL — only {available:.1f}s of post-T2 data "
        f"(need >= {partial_min:.1f}s; "
        f"required {duration_sec:.0f}s with "
        f"{DEFAULT_STABILITY_PARTIAL_CREDIT_FRACTION:.0%} partial credit)"
    )


def evaluate_three_signals(
    result: PerLaneResult,
    collector: t.Any,
    window_start: float,
    window_end: float,
    expected: int,
    signal1_e2e_max_sec: float = DEFAULT_SIGNAL1_E2E_MAX_SEC,
    signal2_local_max_sec: float = DEFAULT_SIGNAL2_LOCAL_MAX_SEC,
    signal3_stability_duration_sec: float = DEFAULT_SIGNAL3_STABILITY_DURATION_SEC,
    match_field: str = "matched",
    lane_id: t.Optional[int] = None,
) -> PerLaneResult:
    """Decorate ``result`` with three independent signal evaluations.

    Signal 1 — End-to-end convergence (window_start → T2):
        T2 - window_start must be <= ``signal1_e2e_max_sec``.

    Signal 2 — Local propagation (T1 → T2):
        T2 - T1 must be <= ``signal2_local_max_sec``.
        T1 = first sample where value > 0.
        T2 = first sample where value >= ``expected``.

    Signal 3 — Post-convergence stability (T2 → T2 + duration):
        Every sample in that window must show value >= ``expected``.
        If the data window ends before the full duration elapses, accept if
        at least ``DEFAULT_STABILITY_PARTIAL_CREDIT_FRACTION`` of the
        required duration was observed without drops.

    Mutates and returns ``result`` with its ``signal*`` fields populated,
    ``passed`` set to (signal1_ok AND signal2_ok AND signal3_ok), and
    ``detail`` rewritten as a human-readable 3-line summary.
    """
    rows = collector.get_rows_in_window(window_start, window_end)
    samples = _collect_sorted_samples(rows, result.device, lane_id, match_field)
    t1, t2 = _find_t1_t2(samples, expected)
    _eval_signal1_e2e(result, t2, window_start, expected, signal1_e2e_max_sec)
    _eval_signal2_local(result, t1, t2, window_start, expected, signal2_local_max_sec)
    _eval_signal3_stability(
        result, t2, samples, window_end, expected, signal3_stability_duration_sec
    )
    all_ok = (
        result.signal1_e2e_ok is True
        and result.signal2_local_ok is True
        and result.signal3_stability_ok is True
    )
    result.passed = all_ok
    result.detail = (
        f"Signal 1 (E2E ≤{signal1_e2e_max_sec:.0f}s): "
        f"{'PASS' if result.signal1_e2e_ok else 'FAIL'} — {result.signal1_e2e_detail} | "
        f"Signal 2 (GTSW ≤{signal2_local_max_sec:.0f}s): "
        f"{'PASS' if result.signal2_local_ok else 'FAIL'} — {result.signal2_local_detail} | "
        f"Signal 3 (Stable {signal3_stability_duration_sec:.0f}s): "
        f"{'PASS' if result.signal3_stability_ok else 'FAIL'} — {result.signal3_stability_detail}"
    )
    return result
