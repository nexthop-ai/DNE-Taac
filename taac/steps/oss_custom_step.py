# Copyright (c) Meta Platforms, Inc. and affiliates.
# pyre-unsafe

"""OSS implementation of ``StepName.CUSTOM_STEP``.

The Meta build takes ``CustomStep`` from ``taac.internal.steps.custom_step``,
which is not part of the OSS slice. Without a replacement ``NAME_TO_STEP`` has
no CUSTOM_STEP entry at all, so ``TaacRunner._initialize_step`` dies on
``NAME_TO_STEP[step.name]`` with a bare ``KeyError(StepName.CUSTOM_STEP)``:
the stage ends in 0.0s before its first step runs and the playbook reports
``<StepName.CUSTOM_STEP: 1001>`` as its whole error. Observed on hardware for
npi_cpu_036/037/038 (unresolved next hop) and npi_cpu_039 (MTU exceed) --
NOS-16136.

Only the handlers OSS playbooks actually reach are ported. An unported
``custom_step_name`` raises and names what is supported, the same contract
``taac/driver/oss_coop_patcher.py`` applies to ``py_func_name``: a playbook
that needs a new handler gets it added here rather than silently running
against an unconfigured DUT.
"""

import json
import typing as t

from taac.steps.step import Step as StepBase
from taac.test_as_a_config import types as taac_types


class OssCustomStep(StepBase[taac_types.CustomStepInput]):
    STEP_NAME = taac_types.StepName.CUSTOM_STEP

    async def run(
        self,
        input: taac_types.CustomStepInput,
        params: t.Dict[str, t.Any],
    ) -> None:
        name = params.get("custom_step_name")
        if not name:
            raise ValueError(
                "oss-custom-step: step_params carry no 'custom_step_name' "
                f"(params: {sorted(params)}); create_custom_step() requires it."
            )
        handler = _HANDLERS.get(name)
        if handler is None:
            raise NotImplementedError(
                f"oss-custom-step: custom_step_name {name!r} is not ported to "
                f"OSS (supported: {sorted(_HANDLERS)}). Port it in "
                f"taac/steps/oss_custom_step.py rather than letting the "
                f"playbook fail with a bare KeyError."
            )
        await handler(self, params)

    def _vport_entry(self, egress_port: str) -> t.Any:
        """The IXIA vport entry for ``<this DUT>:<egress_port>``.

        ``vport_indices`` is keyed by the identifier IXIA composed at
        assign_ports() time. Two things go wrong in practice and both need to
        be legible from the exception rather than from a bare KeyError:

        * a topology-cache HIT skips assign_ports(), so the dict is empty;
        * the key can carry a different host spelling (FQDN vs UQDN) than the
          TestDevice name, so the strict key misses a port that is present.

        The suffix fallback covers the second case but refuses to guess when
        more than one host offers the same port.
        """
        ixia = self.ixia
        if ixia is None:
            raise ValueError(
                "oss-custom-step: no IXIA on the step; "
                "register_cpu_queue_static_route_patcher needs the "
                "traffic-generator topology to resolve its next hop."
            )
        # Via __class__ because get_port_identifier is a staticmethod on the
        # IXIA class, matching how the internal step composes the key.
        key = ixia.__class__.get_port_identifier(f"{self.hostname}:{egress_port}")
        vport_indices = ixia.vport_indices
        if key in vport_indices:
            return vport_indices[key]

        suffix = f":{key.split(':', 1)[1]}" if ":" in key else key
        candidates = [k for k in vport_indices if k.endswith(suffix)]
        if len(candidates) == 1:
            self.logger.warning(
                f"oss-custom-step: no IXIA vport under {key!r}; falling back "
                f"to {candidates[0]!r}, which matches on {suffix!r}. The DUT "
                f"name and the IXIA topology disagree on host spelling."
            )
            return vport_indices[candidates[0]]
        raise KeyError(
            f"oss-custom-step: no IXIA vport for {key!r}. "
            f"Available keys: {sorted(vport_indices)}. "
            f"Suffix-match candidates: {sorted(candidates)}. "
            "An empty list means the IXIA topology cache HIT and "
            "assign_ports() never populated vport_indices."
        )

    async def register_cpu_queue_static_route_patcher(
        self, params: t.Dict[str, t.Any]
    ) -> None:
        """Route the traffic destination at the IXIA port about to be shut.

        The UNH playbooks (npi_cpu_036/037/038) point a static route at the
        IXIA-side device-group mimic IP on ``next_hop_egress_port``, restart
        the agent so the route is programmed, then disable that port. The next
        hop becomes unresolved, and traffic for the prefix is punted to the
        low CPU queue -- which is what their CPU_QUEUE_CHECK measures.
        """
        egress_port = params["next_hop_egress_port"]
        mask = params["static_route_mask"]
        patcher_name = params.get("patcher_name", "cpu_queue_static_route_patcher")
        device_group_index = params.get("device_group_index", 0)

        entry = self._vport_entry(egress_port)
        device_group = entry.device_group_indices[device_group_index]
        if device_group.ipv6 is None:
            raise ValueError(
                f"oss-custom-step: device group {device_group_index} on "
                f"{egress_port} has no IPv6 stack, so it exposes no next hop."
            )
        next_hop = device_group.ipv6.Address.Values[0]

        # ``VportIndex.device_group_indices`` and
        # ``DeviceGroupIndex.network_group_indices`` are BOTH
        # ``Dict[int, ...]`` (taac/ixia/ixia.py:706-727), so the network
        # groups have to be walked with .values() -- iterating the mapping
        # yields its integer keys and every attribute access then fails with
        # "'int' object has no attribute 'network_group'". Seen for real on
        # hardware; the internal step's test mock models these as
        # lists of objects, which hides it.
        patcher_args = {}
        for network_group_index in device_group.network_group_indices.values():
            pools = network_group_index.network_group.Ipv6PrefixPools.find()
            for pool in pools:
                for prefix in pool.NetworkAddress.Values:
                    patcher_args[f"{prefix}/{mask}"] = json.dumps([next_hop])
        if not patcher_args:
            raise ValueError(
                f"oss-custom-step: device group {device_group_index} on "
                f"{egress_port} exposes no IPv6 prefix pool, so there is no "
                "prefix to point at the next hop."
            )

        self.logger.info(
            f"{self.hostname}: static route(s) {sorted(patcher_args)} via "
            f"{next_hop} ({egress_port}), patcher {patcher_name}"
        )
        # pyre-fixme[16]
        await self.driver.async_register_python_patcher(
            patcher_name=patcher_name,
            patcher_args=patcher_args,
            config_name="agent",
            py_func_name="add_static_routes",
            patcher_desc="",
        )
        # Registering is COOP's materialise step internally -- the config lands
        # on the box and the playbook's next AGENT restart picks it up. OSS
        # registration only fills an in-process registry, so without this the
        # route would never reach the DUT and the punt would never happen.
        #
        # ponytail: async_apply_patchers restarts the agent itself, so the
        # playbook's own service-interruption step is a second restart (~2 min).
        # Split the write/activate out of the driver if that wall-clock starts
        # to matter.
        # pyre-fixme[16]
        await self.driver.async_apply_patchers()


_HANDLERS: t.Dict[str, t.Callable[..., t.Awaitable[None]]] = {
    "register_cpu_queue_static_route_patcher": (
        OssCustomStep.register_cpu_queue_static_route_patcher
    ),
}
