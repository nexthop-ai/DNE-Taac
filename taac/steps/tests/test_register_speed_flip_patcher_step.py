# Copyright (c) Meta Platforms, Inc. and affiliates.
# pyre-unsafe
"""The speed flip goes through the generic config-patcher contract.

No speed-flip-specific driver API: a py_func name plus args, the same shape the
BGP patchers register with.
"""

import json
import time
import unittest
from unittest.mock import AsyncMock, MagicMock

from neteng.fboss.switch_config.thrift_mutable_types import PortProfileID, PortSpeed

from taac.constants import (  # oss-rewrite (force ShipIt re-export to taac.* root)
    TestDevice,
    TestTopology,
)
from taac.libs.parameter_evaluator import ParameterEvaluator
from taac.steps.speed_flip_profiles import (
    default_profile_id,
    PLATFORM_SPEED_PROFILE_MAPPING,
)
from taac.steps.step_definitions import (
    _SpeedFlipDeviceInfo,
    _SPEED_FLIP_PY_FUNC_NAME,
    AGENT_CONFIG,
    create_register_speed_flip_patcher_step,
    RegisterSpeedFlipPatcherStep,
)
from taac.test_as_a_config.thrift_types import Step


class RegisterSpeedFlipPatcherStepTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.device = MagicMock(spec=TestDevice)
        self.device.name = "test_device"
        attributes_mock = MagicMock()
        attributes_mock.operating_system = "FBOSS"
        attributes_mock.role = ""
        attributes_mock.device_name = "test_device"
        attributes_mock.hardware = "WEDGE800BNHP"
        attributes_mock.ai_zone = ""
        self.device.attributes = attributes_mock

        self.step = RegisterSpeedFlipPatcherStep(
            name="test_register_speed_flip_patcher",
            device=self.device,
            topology=MagicMock(spec=TestTopology),
            test_case_results=[],
            test_config=MagicMock(),
            test_case_name="test_case",
            test_case_start_time=time.time(),
            parameter_evaluator=MagicMock(spec=ParameterEvaluator),
            step=MagicMock(spec=Step),
        )
        self.driver_mock = AsyncMock()
        self.device_info = _SpeedFlipDeviceInfo(
            ports=["eth1/17/1", "eth1/21/1"],
            driver=self.driver_mock,
            hostname="test_device",
            hardware_type="WEDGE800BNHP",
        )

    async def test_registers_through_the_generic_patcher_contract(self):
        await self.step._register_speed_flip_patchers(
            device_infos=[self.device_info],
            speed_in_gbps=800,
            patcher_name="speed_flip",
        )
        self.driver_mock.async_register_python_patcher.assert_awaited_once()
        call = self.driver_mock.async_register_python_patcher.await_args
        self.assertEqual(call.kwargs["config_name"], AGENT_CONFIG)
        self.assertEqual(call.kwargs["patcher_name"], "speed_flip")
        self.assertEqual(call.kwargs["py_func_name"], _SPEED_FLIP_PY_FUNC_NAME)
        # Numeric config values, so the on-DUT py_func stays enum-free.
        self.assertEqual(
            call.kwargs["patcher_args"],
            {
                "ports": json.dumps(["eth1/17/1", "eth1/21/1"]),
                "speed": str(PortSpeed.EIGHTHUNDREDG.value),
                "profile_id": str(
                    PortProfileID[default_profile_id("WEDGE800BNHP", 800000)].value
                ),
            },
        )

    async def test_config_supplied_profile_wins_over_the_platform_default(self):
        requested = "PROFILE_400G_8_PAM4_RS544X2N_OPTICAL"
        await self.step._register_speed_flip_patchers(
            device_infos=[self.device_info],
            speed_in_gbps=400,
            patcher_name="speed_flip",
            profile_id=requested,
        )
        args = self.driver_mock.async_register_python_patcher.await_args.kwargs
        self.assertEqual(
            args["patcher_args"]["profile_id"], str(PortProfileID[requested].value)
        )
        self.assertNotEqual(requested, default_profile_id("WEDGE800BNHP", 400000))

    def test_the_table_needs_a_portspeed_not_raw_mbps(self):
        """Raw Mbps must not reach the table: PortSpeed is an Enum, not an int.

        The pre-refactor lookup indexed this table with ``speed_in_mbps``
        directly (hence its ``pyrefly: ignore [bad-index]``), which never
        matched. ``default_profile_id`` converts first.
        """
        by_speed = PLATFORM_SPEED_PROFILE_MAPPING["WEDGE800BNHP"]
        self.assertIsNone(by_speed.get(800000))
        self.assertEqual(
            default_profile_id("WEDGE800BNHP", 800000),
            by_speed[PortSpeed.EIGHTHUNDREDG],
        )

    async def test_a_platform_without_a_profile_table_raises(self):
        device_info = _SpeedFlipDeviceInfo(
            ports=["eth1/17/1"],
            driver=self.driver_mock,
            hostname="test_device",
            hardware_type="NOT_A_PLATFORM",
        )
        with self.assertRaises(KeyError) as ctx:
            await self.step._register_speed_flip_patchers(
                device_infos=[device_info],
                speed_in_gbps=800,
                patcher_name="speed_flip",
            )
        self.assertIn("NOT_A_PLATFORM", str(ctx.exception))
        self.driver_mock.async_register_python_patcher.assert_not_awaited()

    async def test_a_speed_the_platform_has_no_profile_for_raises(self):
        with self.assertRaises(KeyError) as ctx:
            await self.step._register_speed_flip_patchers(
                device_infos=[
                    _SpeedFlipDeviceInfo(
                        ports=["eth1/17/1"],
                        driver=self.driver_mock,
                        hostname="test_device",
                        hardware_type="MINIPACK",
                    )
                ],
                speed_in_gbps=800,
                patcher_name="speed_flip",
            )
        self.assertIn("EIGHTHUNDREDG", str(ctx.exception))

    def test_step_params_are_unchanged_for_callers_that_pass_neither(self):
        step = create_register_speed_flip_patcher_step(
            register_patcher=True,
            port_state_change=False,
            patcher_name="speed_flip",
            endpoints={"test_device": ["eth1/17/1"]},
            speed_in_gbps=800,
        )
        params = json.loads(step.step_params.json_params)
        self.assertEqual(
            params,
            {
                "register_patcher": True,
                "port_state_change": False,
                "patcher_name": "speed_flip",
                "endpoints": {"test_device": ["eth1/17/1"]},
                "speed_in_gbps": 800,
                "target_port_cage_count": 4,
            },
        )

    def test_step_params_carry_the_config_supplied_profile(self):
        step = create_register_speed_flip_patcher_step(
            register_patcher=True,
            port_state_change=False,
            patcher_name="speed_flip",
            endpoints={"test_device": ["eth1/17/1"]},
            speed_in_gbps=100,
            profile_id="PROFILE_100G_4_NRZ_RS528_COPPER",
        )
        params = json.loads(step.step_params.json_params)
        self.assertEqual(params["profile_id"], "PROFILE_100G_4_NRZ_RS528_COPPER")
