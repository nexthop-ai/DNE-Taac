# Copyright (c) Meta Platforms, Inc. and affiliates.

# pyre-unsafe

"""TAAC teardown/setup task that restarts a systemd service (default bgpd) on a
list of FBOSS devices, in parallel, via the same proven driver path the FPF
service-restart playbook uses (``async_restart_service``).

Primary use: clear the runtime BGP-injected prefixes (added via ``addNetworks``)
off the STSWs at teardown by restarting ``bgpd`` — a restart reloads persistent
config, which does NOT contain the injected networks, so they are dropped. This
is more robust than a per-prefix ``delNetworks`` withdrawal because it also
clears any leftover/unknown injected state on the device (e.g. from a previously
interrupted run), keeping the testbed clean run-to-run.

Params (via json_params):
    devices: list[str]                hostnames to restart the service on
    service: str                      FbossSystemctlServiceName member name
                                      (default "BGP" -> bgpd). e.g. "AGENT" for
                                      wedge_agent.
    wait_for_convergence: bool        for BGP, wait for BGP convergence after the
                                      restart (default False — teardown does not
                                      need to block on reconvergence).

Best-effort: a restart error is logged but never raised, so a teardown never
masks the real test result.

NOTE on device eligibility: ``async_restart_service`` enforces a device-safety
guard — it refuses to restart services on devices not in the DNE test SMC tier
(dne.test / dne.standalone / dne.regression) or the preprod hostname allowlist
(c087.mwg2, c085.ash6, .qzk1, .qzd1). The MWG2 spine STSWs (``stsw*.l202.mwg2``)
are NOT in that allowlist (they are treated as production/shared), so a bgpd
restart on the STSWs is blocked at the driver level. This task therefore works
on allowlisted devices (e.g. the c087.mwg2 GTSWs) but is NOT currently usable to
clear injected prefixes off the l202 STSWs — use the thrift delNetworks
withdrawal (``create_fpf_withdraw_vf_groups_task``) for STSW cleanup until the
STSWs are added to a test tier / preprod allowlist.
"""

import asyncio
import typing as t

from taac.driver.driver_constants import FbossSystemctlServiceName
from taac.internal.driver.fboss_switch_internal import (
    FbossSwitchInternal,
)
from taac.tasks.base_task import BaseTask


class FpfRestartServiceTask(BaseTask):
    """Restart a systemd service (default bgpd) on one or more FBOSS devices."""

    NAME = "fpf_restart_service"

    async def run(self, params: t.Dict[str, t.Any]) -> None:
        devices: t.List[str] = params["devices"]
        service_name: str = params.get("service", "BGP")
        wait_for_convergence: bool = params.get("wait_for_convergence", False)

        try:
            service = FbossSystemctlServiceName[service_name]
        except KeyError:
            valid = [m.name for m in FbossSystemctlServiceName]
            raise ValueError(f"Unknown service '{service_name}'. Valid: {valid}")

        self.logger.info(
            f"[FpfRestartService] restarting {service.value} on {len(devices)} "
            f"device(s): {', '.join(devices)}"
        )

        async def _restart(device: str) -> None:
            driver = FbossSwitchInternal(hostname=device, logger=self.logger)
            await driver.async_restart_service(service)
            if wait_for_convergence and service == FbossSystemctlServiceName.BGP:
                await driver.async_wait_for_bgp_convergence()

        results = await asyncio.gather(
            *(_restart(d) for d in devices), return_exceptions=True
        )
        for device, res in zip(devices, results):
            if isinstance(res, Exception):
                self.logger.error(
                    f"[FpfRestartService] restart of {service.value} on {device} "
                    f"best-effort failed: {res}"
                )
            else:
                self.logger.info(
                    f"[FpfRestartService] restarted {service.value} on {device}"
                )
