# (c) Meta Platforms, Inc. and affiliates. Confidential and proprietary.

# pyre-unsafe
import asyncio
import time
import typing as t

from taac.constants import TestDevice
from taac.health_checks.abstract_health_check import (
    AbstractDeviceHealthCheck,
)
from taac.health_checks.constants import (
    DAILY_TABLE_TRANSFORM_DESC,
)
from taac.internal.ods_utils import (
    async_generate_ods_url,
    async_query_ods,
)
from taac.libs.fpf.fpf_collector_registry import (
    get_test_case_start_time,
)
from neteng.test_infra.dne.taac.utils.common import async_get_fburl, eval_jq
from pyre_extensions import JSON
from taac.health_check.health_check import types as hc_types


def dict(ods_data) -> JSON:
    dict_data = {}
    for hostname, time_series in ods_data.items():
        dict_data[hostname] = {}
        for timestamp, value in time_series.items():
            dict_data[hostname][str(timestamp)] = value
    # pyrefly: ignore [bad-return]
    return dict_data


class GenericOdsHealthCheck(AbstractDeviceHealthCheck[hc_types.BaseHealthCheckIn]):
    CHECK_NAME = hc_types.CheckName.GENERIC_ODS_CHECK
    LOG_TO_SCUBA = True

    async def _run(  # noqa: C901
        self,
        obj: TestDevice,
        input: hc_types.BaseHealthCheckIn,
        check_params: t.Dict[str, t.Any],
    ) -> hc_types.HealthCheckResult:
        key_desc = check_params["key_desc"]
        entity_desc = check_params.get("entity_desc", obj.name)
        min_ods_query_duration = int(check_params.get("min_ods_query_duration", 120))
        use_tc_start = check_params.get("use_test_case_start_time", False)
        if use_tc_start:
            tc_start = get_test_case_start_time()
            start_time = int(tc_start) if tc_start else int(time.time())
        else:
            start_time = int(check_params.get("start_time", time.time()))
        # wait x seconds before checking ods data
        sleep_timer = check_params.get("sleep_timer", 120)
        if sleep_timer > 0:
            await asyncio.sleep(sleep_timer)
        end_time = int(time.time())
        if end_time - start_time < min_ods_query_duration:
            start_time = end_time - min_ods_query_duration
        transform_desc = check_params.get("transform_desc", DAILY_TABLE_TRANSFORM_DESC)
        reduce_desc = check_params.get("reduce_desc", "")
        validation_expr = check_params.get("validation_expr")
        custom_jq_expr = check_params.get("custom_jq_expr")
        assert validation_expr or custom_jq_expr
        ods_data = await async_query_ods(
            entity_desc=entity_desc,
            key_desc=key_desc,
            reduce_desc=reduce_desc,
            transform_desc=transform_desc,
            start_time=int(start_time),
            end_time=int(end_time),
        )
        if not ods_data:
            ods_query_url_raw = await async_generate_ods_url(
                entity_desc=entity_desc,
                key_desc=key_desc,
                reduce_desc=reduce_desc,
                transform_desc=transform_desc,
                start_time=int(start_time),
                end_time=int(end_time),
            )
            # A SKIP (no data) is not a failure and does not need a short link;
            # keep the raw ODS URL inline and skip the throttled fburl tier.
            ods_query_url = ods_query_url_raw
            msg = f"ODS query returned no data: {ods_query_url}"
            self.logger.debug(msg)
            return hc_types.HealthCheckResult(
                status=hc_types.HealthCheckStatus.SKIP,
                message=msg,
            )
        is_multi_entity = "," in entity_desc
        counter_name = check_params.get("counter_name", key_desc)
        violations = []
        entity_max_map: t.Dict[str, t.Tuple[float, str]] = {}

        if is_multi_entity:
            entities_to_check = ods_data
        else:
            entities_to_check = {
                entity_desc: ods_data.get(entity_desc, ods_data.get(obj.name, {}))
            }
        for entity_name, entity_data in entities_to_check.items():
            ods_data_dict = dict(entity_data)
            all_values = {}
            for _key_name, ts_data in entity_data.items():
                for ts, val in ts_data.items():
                    all_values[ts] = val
            if all_values:
                # pyrefly: ignore [no-matching-overload]
                max_ts = max(all_values, key=all_values.get)
                max_val = all_values[max_ts]
                max_time_str = time.strftime(
                    "%Y-%m-%d %H:%M:%S", time.localtime(int(max_ts))
                )
                entity_max_map[entity_name] = (max_val, max_time_str)
            else:
                entity_max_map[entity_name] = (0.0, "no data")

            if validation_expr:
                jq_expr = f". | .[] | to_entries | map(select(.value {validation_expr} | not)) | from_entries"
                violation_data = eval_jq(jq_expr, ods_data_dict)  # pyre-ignore
                if violation_data:
                    for timestamp, value in violation_data.items():
                        entity_label = entity_name if is_multi_entity else ""
                        log_message = (
                            f"Validation Error: {entity_label} {key_desc} at "
                            f"{time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(int(timestamp)))} "
                            f"failed validation check '{validation_expr}' with value: {value}"
                        )
                        self.logger.debug(log_message)
                        violations.append(log_message)
            elif custom_jq_expr:
                violation_data = eval_jq(custom_jq_expr, ods_data_dict)  # pyre-ignore
                if violation_data:
                    entity_label = entity_name if is_multi_entity else ""
                    log_message = (
                        f"Custom Validation Error: {entity_label} Data "
                        f"'{violation_data}' failed custom JQ expression "
                        f"'{custom_jq_expr}'"
                    )
                    self.logger.debug(log_message)
                    violations.append(log_message)

        ods_url_raw = await async_generate_ods_url(
            entity_desc=entity_desc,
            key_desc=key_desc,
            reduce_desc=reduce_desc,
            transform_desc=transform_desc,
            start_time=int(start_time),
            end_time=int(end_time),
        )
        self.logger.info(f"  [{counter_name}] Per-entity max values:")
        for entity, (max_val, max_ts) in sorted(entity_max_map.items()):
            threshold_status = (
                "OK"
                if not validation_expr or eval(f"{max_val} {validation_expr}")
                else "EXCEEDED"
            )
            self.logger.info(
                f"    {entity}: max={max_val:.0f} at {max_ts} [{threshold_status}]"
            )
        self.logger.info(f"  [{counter_name}] ODS: {ods_url_raw}")

        max_summary = ", ".join(
            f"{e}: {v:.0f}" for e, (v, _) in sorted(entity_max_map.items())
        )

        if violations:
            failed_entities = [
                f"{e}: max={v:.0f} at {ts}"
                for e, (v, ts) in sorted(entity_max_map.items())
                if validation_expr and not eval(f"{v} {validation_expr}")
            ]
            fail_summary = (
                "; ".join(failed_entities) if failed_entities else max_summary
            )
            # Only shorten through the throttled fburl tier on failure. This
            # check is parameterized and reused many times per device per
            # iteration, so shortening on the (dominant) passing path was
            # avoidable fburl QPS.
            try:
                ods_url = await async_get_fburl(ods_url_raw)
            except Exception:
                ods_url = ods_url_raw
            return hc_types.HealthCheckResult(
                status=hc_types.HealthCheckStatus.FAIL,
                message=(
                    f"{counter_name} threshold exceeded — {fail_summary} | "
                    f"ODS: {ods_url}"
                ),
            )
        return hc_types.HealthCheckResult(
            status=hc_types.HealthCheckStatus.PASS,
            message=(
                f"{counter_name} within threshold — {max_summary} | ODS: {ods_url_raw}"
            ),
        )
