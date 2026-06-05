# (c) Meta Platforms, Inc. and affiliates. Confidential and proprietary.

# pyre-unsafe

import typing as t

from taac.constants import TestDevice
from taac.health_checks.abstract_health_check import (
    AbstractDeviceHealthCheck,
)
from taac.libs.fpf.fpf_hrt_polling import get_hrt_client
from taac.health_check.health_check import types as hc_types

EXPECTED_FSDB_SESSION_COUNT = 32


class FpfHrtFsdbSessionHealthCheck(
    AbstractDeviceHealthCheck[hc_types.BaseHealthCheckIn]
):
    """Health check verifying HRT FSDB sessions are CONNECTED on GPU hosts.

    HRT runs on rtptest GPU hosts, not on GTSW/STSW switches. Pass the
    GPU hostnames via ``check_params["hosts"]``. The check iterates over
    each host, connects to HRT (port 5909), and verifies all expected
    FSDB sessions are CONNECTED.
    """

    CHECK_NAME = hc_types.CheckName.FPF_HRT_FSDB_SESSION_CHECK
    CHECK_SCOPE = hc_types.Scope.DEFAULT
    OPERATING_SYSTEMS = ["FBOSS"]

    async def _run(
        self,
        obj: TestDevice,
        input: hc_types.BaseHealthCheckIn,
        check_params: t.Dict[str, t.Any],
    ) -> hc_types.HealthCheckResult:
        hosts = check_params.get("hosts", [])
        if not hosts:
            return hc_types.HealthCheckResult(
                status=hc_types.HealthCheckStatus.SKIP,
                message="No GPU hosts specified in check_params['hosts']",
            )

        gpu_hosts = []
        for host in hosts:
            if not host.startswith("rtptest"):
                self.logger.warning(
                    f"Host {host} is not a GPU host (expected 'rtptest' prefix), "
                    f"skipping HRT check — HRT only runs on rtptest hosts"
                )
                continue
            gpu_hosts.append(host)

        if not gpu_hosts:
            return hc_types.HealthCheckResult(
                status=hc_types.HealthCheckStatus.SKIP,
                message="No valid rtptest GPU hosts after filtering",
            )

        expected_count = check_params.get(
            "expected_session_count", EXPECTED_FSDB_SESSION_COUNT
        )

        all_results = []
        any_fail = False

        for host in gpu_hosts:
            result = await self._check_host(host, expected_count)
            all_results.append(result)
            if result.status == hc_types.HealthCheckStatus.FAIL:
                any_fail = True

        messages = [r.message for r in all_results]
        # pyrefly: ignore [no-matching-overload]
        combined = "; ".join(messages)

        if any_fail:
            return hc_types.HealthCheckResult(
                status=hc_types.HealthCheckStatus.FAIL,
                message=combined,
            )

        has_skip = any(r.status == hc_types.HealthCheckStatus.SKIP for r in all_results)
        if has_skip:
            return hc_types.HealthCheckResult(
                status=hc_types.HealthCheckStatus.SKIP,
                message=combined,
            )

        return hc_types.HealthCheckResult(
            status=hc_types.HealthCheckStatus.PASS,
            message=combined,
        )

    async def _check_host(
        self, hostname: str, expected_count: int
    ) -> hc_types.HealthCheckResult:
        self.logger.info(
            f"Running FPF HRT FSDB session check on {hostname}, "
            f"expecting {expected_count} CONNECTED sessions"
        )

        try:
            client = await get_hrt_client(hostname)
        except Exception as e:
            self.logger.warning(f"Failed to connect to HRT on {hostname}: {e}")
            return hc_types.HealthCheckResult(
                status=hc_types.HealthCheckStatus.SKIP,
                message=f"Failed to connect to HRT on {hostname}: {e}",
            )

        try:
            async with client:
                sessions = await client.getFsdbSessions()
        except Exception as e:
            self.logger.warning(
                f"Failed to get FSDB sessions from HRT on {hostname}: {e}"
            )
            return hc_types.HealthCheckResult(
                status=hc_types.HealthCheckStatus.SKIP,
                message=f"Failed to get FSDB sessions from HRT on {hostname}: {e}",
            )

        connected_count = 0
        disconnected_sessions = []

        for session in sessions:
            state = getattr(session, "state", None)
            session_name = getattr(session, "name", "unknown")
            if state is not None and str(state) == "CONNECTED":
                connected_count += 1
            else:
                disconnected_sessions.append(f"{session_name} (state={state})")

        total_sessions = len(sessions)
        self.logger.info(
            f"HRT FSDB sessions on {hostname}: "
            f"{connected_count}/{total_sessions} CONNECTED "
            f"(expected {expected_count})"
        )

        if connected_count == expected_count and not disconnected_sessions:
            return hc_types.HealthCheckResult(
                status=hc_types.HealthCheckStatus.PASS,
                message=f"All {expected_count} HRT FSDB sessions CONNECTED on {hostname}",
            )

        detail = (
            f"HRT FSDB session check failed on {hostname}: "
            f"{connected_count}/{expected_count} sessions CONNECTED "
            f"(total: {total_sessions})"
        )
        if disconnected_sessions:
            detail += f". Disconnected: {', '.join(disconnected_sessions[:10])}"
            if len(disconnected_sessions) > 10:
                detail += f" (and {len(disconnected_sessions) - 10} more)"

        self.logger.error(detail)
        return hc_types.HealthCheckResult(
            status=hc_types.HealthCheckStatus.FAIL,
            message=detail,
        )
