# Copyright (c) Meta Platforms, Inc. and affiliates.
# pyre-unsafe

"""Tests for the OSS ``CUSTOM_STEP`` implementation.

The dispatch guard and the vport lookup are the two things that decide whether
a UNH playbook configures its next hop or fails opaquely, so both are covered
here. Mirrors the contract locked by the internal
``TestRegisterCpuQueueStaticRoutePatcher`` in ``test_custom_step.py``: same
patcher kwargs, same suffix fallback, same descriptive errors.
"""

import json
import time
import typing as t
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from taac.constants import TestDevice, TestTopology
from taac.libs.parameter_evaluator import ParameterEvaluator
from taac.steps.all_steps import NAME_TO_STEP
from taac.steps.oss_custom_step import OssCustomStep
from taac.test_as_a_config import types as taac_types


class _FakeIxiaClass:
    """Scoped stand-in for the IXIA class's ``get_port_identifier``.

    Assigned to a mock's ``__class__`` so the override does not leak into the
    global ``MagicMock`` class the rest of the suite shares.
    """

    @staticmethod
    def get_port_identifier(port_name: str) -> str:
        return port_name.upper()


HOSTNAME = "dut"
PORT = "eth1/13/1"
STRICT_KEY = "DUT:ETH1/13/1"
DG0_IPV6 = "2001:db8:0:1801::10"
DG1_IPV6 = "2001:db8:0:1801::20"


def _vport_entry(dg_to_ipv6_and_prefixes):
    """A vport entry shaped like what ``assign_ports()`` leaves behind.

    Both index collections are ``Dict[int, ...]`` per the real dataclasses in
    ``taac/ixia/ixia.py`` (VportIndex.device_group_indices,
    DeviceGroupIndex.network_group_indices) -- NOT lists. Modelling them as
    lists is what let an "'int' object has no attribute 'network_group'"
    crash reach hardware with the unit tests green.
    """
    device_groups = {}
    for dg_index, (ipv6, prefixes) in enumerate(dg_to_ipv6_and_prefixes):
        pool = SimpleNamespace(NetworkAddress=SimpleNamespace(Values=prefixes))
        network_group = SimpleNamespace(
            Ipv6PrefixPools=SimpleNamespace(find=lambda pool=pool: [pool])
        )
        device_groups[dg_index] = SimpleNamespace(
            ipv6=SimpleNamespace(Address=SimpleNamespace(Values=[ipv6])),
            network_group_indices={0: SimpleNamespace(network_group=network_group)},
        )
    return SimpleNamespace(device_group_indices=device_groups)


def _make_step(vport_indices: t.Optional[t.Dict[str, t.Any]] = None):
    device = MagicMock(spec=TestDevice)
    device.name = HOSTNAME
    step = OssCustomStep(
        name="step",
        device=device,
        topology=MagicMock(spec=TestTopology),
        test_case_results=[],
        test_config=MagicMock(spec=taac_types.TestConfig),
        test_case_name="case",
        test_case_start_time=time.time(),
        parameter_evaluator=MagicMock(spec=ParameterEvaluator),
        step=MagicMock(spec=taac_types.Step),
        logger=MagicMock(),
    )
    step.driver = AsyncMock()
    if vport_indices is not None:
        ixia = MagicMock()
        ixia.__class__ = _FakeIxiaClass
        ixia.vport_indices = vport_indices
        step.ixia = ixia
    return step


class TestCustomStepIsSelectable(unittest.TestCase):
    def test_custom_step_is_in_the_step_table(self):
        """The whole bug: no CUSTOM_STEP entry meant TaacRunner raised
        KeyError(StepName.CUSTOM_STEP) before the stage ran a single step."""
        self.assertIn(taac_types.StepName.CUSTOM_STEP, NAME_TO_STEP)


class TestDispatch(unittest.IsolatedAsyncioTestCase):
    async def test_unported_name_names_what_is_supported(self):
        step = _make_step({})
        with self.assertRaises(NotImplementedError) as ctx:
            await step.run(MagicMock(), {"custom_step_name": "test_ndp_clear"})
        msg = str(ctx.exception)
        self.assertIn("test_ndp_clear", msg)
        self.assertIn("register_cpu_queue_static_route_patcher", msg)

    async def test_missing_name_is_rejected(self):
        step = _make_step({})
        with self.assertRaises(ValueError):
            await step.run(MagicMock(), {"static_route_mask": 64})

    async def test_dispatch_reaches_the_handler(self):
        step = _make_step({STRICT_KEY: _vport_entry([(DG0_IPV6, ["9000:1::"])])})
        await step.run(
            MagicMock(),
            {
                "custom_step_name": "register_cpu_queue_static_route_patcher",
                "next_hop_egress_port": PORT,
                "static_route_mask": 64,
            },
        )
        step.driver.async_register_python_patcher.assert_awaited_once()


class TestRegisterCpuQueueStaticRoutePatcher(unittest.IsolatedAsyncioTestCase):
    async def test_happy_path_installs_patcher(self):
        step = _make_step(
            {STRICT_KEY: _vport_entry([(DG0_IPV6, ["9000:1::"])])}
        )
        await step.register_cpu_queue_static_route_patcher(
            {
                "next_hop_egress_port": PORT,
                "static_route_mask": 64,
                "patcher_name": "my_patcher",
            }
        )
        step.driver.async_register_python_patcher.assert_awaited_once_with(
            patcher_name="my_patcher",
            patcher_args={"9000:1::/64": f'["{DG0_IPV6}"]'},
            config_name="agent",
            py_func_name="add_static_routes",
            patcher_desc="",
        )
        step.logger.warning.assert_not_called()

    async def test_default_patcher_name_matches_the_unregister_step(self):
        """The playbooks unregister by the literal
        `cpu_queue_static_route_patcher`, so the default must be that."""
        step = _make_step({STRICT_KEY: _vport_entry([(DG0_IPV6, ["9000:1::"])])})
        await step.register_cpu_queue_static_route_patcher(
            {"next_hop_egress_port": PORT, "static_route_mask": 128}
        )
        kwargs = step.driver.async_register_python_patcher.await_args.kwargs
        self.assertEqual(kwargs["patcher_name"], "cpu_queue_static_route_patcher")
        self.assertEqual(kwargs["patcher_args"], {"9000:1::/128": f'["{DG0_IPV6}"]'})

    async def test_suffix_fallback_warns_and_names_both_keys(self):
        fqdn_key = "DUT.EXAMPLE.COM:ETH1/13/1"
        step = _make_step({fqdn_key: _vport_entry([(DG0_IPV6, ["9000:2::"])])})
        await step.register_cpu_queue_static_route_patcher(
            {"next_hop_egress_port": PORT, "static_route_mask": 64}
        )
        step.driver.async_register_python_patcher.assert_awaited_once()
        step.logger.warning.assert_called_once()
        warned = step.logger.warning.call_args[0][0]
        self.assertIn(STRICT_KEY, warned)
        self.assertIn(fqdn_key, warned)

    async def test_empty_vport_indices_raises_descriptive_keyerror(self):
        """The IXIA topology-cache HIT shape: assign_ports() never ran."""
        step = _make_step({})
        with self.assertRaises(KeyError) as ctx:
            await step.register_cpu_queue_static_route_patcher(
                {"next_hop_egress_port": PORT, "static_route_mask": 64}
            )
        msg = str(ctx.exception)
        self.assertIn(STRICT_KEY, msg)
        self.assertIn("Available keys: []", msg)
        self.assertIn("Suffix-match candidates: []", msg)
        step.driver.async_register_python_patcher.assert_not_awaited()

    async def test_ambiguous_suffix_refuses_to_guess(self):
        a = "OTHERHOST:ETH1/13/1"
        b = "YETANOTHER:ETH1/13/1"
        step = _make_step(
            {
                a: _vport_entry([(DG0_IPV6, ["9000:3::"])]),
                b: _vport_entry([(DG1_IPV6, ["9000:4::"])]),
            }
        )
        with self.assertRaises(KeyError) as ctx:
            await step.register_cpu_queue_static_route_patcher(
                {"next_hop_egress_port": PORT, "static_route_mask": 64}
            )
        msg = str(ctx.exception)
        self.assertIn(a, msg)
        self.assertIn(b, msg)
        step.driver.async_register_python_patcher.assert_not_awaited()

    async def test_device_group_index_selects_that_group(self):
        step = _make_step(
            {
                STRICT_KEY: _vport_entry(
                    [(DG0_IPV6, ["9000:dg0::"]), (DG1_IPV6, ["9000:dg1::"])]
                )
            }
        )
        await step.register_cpu_queue_static_route_patcher(
            {
                "next_hop_egress_port": PORT,
                "static_route_mask": 64,
                "device_group_index": 1,
            }
        )
        step.driver.async_register_python_patcher.assert_awaited_once_with(
            patcher_name="cpu_queue_static_route_patcher",
            patcher_args={"9000:dg1::/64": f'["{DG1_IPV6}"]'},
            config_name="agent",
            py_func_name="add_static_routes",
            patcher_desc="",
        )

    async def test_prefixless_device_group_raises(self):
        step = _make_step({STRICT_KEY: _vport_entry([(DG0_IPV6, [])])})
        with self.assertRaises(ValueError):
            await step.register_cpu_queue_static_route_patcher(
                {"next_hop_egress_port": PORT, "static_route_mask": 64}
            )

    async def test_network_groups_are_walked_as_a_mapping(self):
        """Regression: both index collections are Dict[int, ...]; iterating
        the mapping itself yields ints and every attribute access fails."""
        step = _make_step({STRICT_KEY: _vport_entry([(DG0_IPV6, ["9000:1::"])])})
        entry = step.ixia.vport_indices[STRICT_KEY]
        self.assertIsInstance(entry.device_group_indices, dict)
        self.assertIsInstance(entry.device_group_indices[0].network_group_indices, dict)
        await step.register_cpu_queue_static_route_patcher(
            {"next_hop_egress_port": PORT, "static_route_mask": 64}
        )
        step.driver.async_register_python_patcher.assert_awaited_once()

    async def test_device_group_without_ipv6_raises(self):
        step = _make_step({STRICT_KEY: _vport_entry([(DG0_IPV6, ["9000:1::"])])})
        step.ixia.vport_indices[STRICT_KEY].device_group_indices[0].ipv6 = None
        with self.assertRaises(ValueError):
            await step.register_cpu_queue_static_route_patcher(
                {"next_hop_egress_port": PORT, "static_route_mask": 64}
            )

    async def test_no_ixia_raises(self):
        step = _make_step()
        with self.assertRaises(ValueError):
            await step.register_cpu_queue_static_route_patcher(
                {"next_hop_egress_port": PORT, "static_route_mask": 64}
            )

    async def test_patcher_is_materialised_on_the_dut(self):
        """Registration alone only fills the in-process registry, so the route
        reaches the DUT only if the step applies it."""
        step = _make_step({STRICT_KEY: _vport_entry([(DG0_IPV6, ["9000:1::"])])})
        await step.register_cpu_queue_static_route_patcher(
            {"next_hop_egress_port": PORT, "static_route_mask": 64}
        )
        step.driver.async_apply_patchers.assert_awaited_once()

    async def test_nothing_is_applied_when_the_lookup_fails(self):
        step = _make_step({})
        with self.assertRaises(KeyError):
            await step.register_cpu_queue_static_route_patcher(
                {"next_hop_egress_port": PORT, "static_route_mask": 64}
            )
        step.driver.async_apply_patchers.assert_not_awaited()

    async def test_next_hop_is_json_encoded_for_the_patcher(self):
        """`add_static_routes` json.loads() the value, so it must be a JSON
        string and not a bare list."""
        step = _make_step({STRICT_KEY: _vport_entry([(DG0_IPV6, ["9000:1::"])])})
        await step.register_cpu_queue_static_route_patcher(
            {"next_hop_egress_port": PORT, "static_route_mask": 64}
        )
        args = step.driver.async_register_python_patcher.await_args.kwargs[
            "patcher_args"
        ]
        (value,) = args.values()
        self.assertEqual(json.loads(value), [DG0_IPV6])
