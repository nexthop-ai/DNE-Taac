# Copyright (c) Meta Platforms, Inc. and affiliates.

# pyre-unsafe

import json

from taac.testconfigs.configerator.test_config import (
    thrift_to_json,
)
from taac.health_check.health_check import types as hc_thrift
from taac.test_as_a_config import types as taac_thrift


def create_speed_flip_test_cases(
    speed_flip_ports, original_speed, new_speed, neighbor_portmap=None
):
    return [
        taac_thrift.Playbook(
            name=f"test_speed_flip_agent_reload_only_{original_speed}g_to_{new_speed}g",
            stages=[
                taac_thrift.Stage(
                    steps=[
                        taac_thrift.Step(
                            name=taac_thrift.StepName.VERIFY_PORT_SPEED,
                            step_params=taac_thrift.Params(
                                json_params=json.dumps(
                                    {
                                        "neighbor_portmap": neighbor_portmap,
                                        "ports": speed_flip_ports,
                                        "speed_to_verify": original_speed,
                                    }
                                ),
                            ),
                        ),
                        taac_thrift.Step(
                            name=taac_thrift.StepName.REGISTER_SPEED_FLIP_PATCHER,
                            step_params=taac_thrift.Params(
                                json_params=json.dumps(
                                    {
                                        "neighbor_portmap": neighbor_portmap,
                                        "ports": speed_flip_ports,
                                        "apply_patcher_method": taac_thrift.ApplyPatcherMethod.AGENT_RELOAD_AND_WARMBOOT,
                                        "register_patcher": True,
                                        "speed": new_speed,
                                    }
                                ),
                            ),
                        ),
                        taac_thrift.Step(
                            name=taac_thrift.StepName.LONGEVITY_STEP,
                            step_params=taac_thrift.Params(
                                json_params='{"duration": 60}'
                            ),
                        ),
                        taac_thrift.Step(
                            name=taac_thrift.StepName.VERIFY_PORT_SPEED,
                            step_params=taac_thrift.Params(
                                json_params=json.dumps(
                                    {
                                        "neighbor_portmap": neighbor_portmap,
                                        "ports": speed_flip_ports,
                                        "speed_to_verify": new_speed,
                                    }
                                ),
                            ),
                        ),
                        taac_thrift.Step(
                            name=taac_thrift.StepName.REGISTER_SPEED_FLIP_PATCHER,
                            step_params=taac_thrift.Params(
                                json_params=json.dumps(
                                    {
                                        "neighbor_portmap": neighbor_portmap,
                                        "ports": speed_flip_ports,
                                        "apply_patcher_method": taac_thrift.ApplyPatcherMethod.AGENT_RELOAD_AND_WARMBOOT,
                                        "register_patcher": False,
                                    }
                                ),
                            ),
                        ),
                        taac_thrift.Step(
                            name=taac_thrift.StepName.LONGEVITY_STEP,
                            step_params=taac_thrift.Params(
                                json_params='{"duration": 60}'
                            ),
                        ),
                        taac_thrift.Step(
                            name=taac_thrift.StepName.VERIFY_PORT_SPEED,
                            step_params=taac_thrift.Params(
                                json_params=json.dumps(
                                    {
                                        "neighbor_portmap": neighbor_portmap,
                                        "ports": speed_flip_ports,
                                        "speed_to_verify": original_speed,
                                    }
                                ),
                            ),
                        ),
                    ]
                )
            ],
        ),
        taac_thrift.Playbook(
            name=f"test_speed_flip_agent_reload_and_warmboot_{original_speed}g_to_{new_speed}g",
            stages=[
                taac_thrift.Stage(
                    steps=[
                        taac_thrift.Step(
                            name=taac_thrift.StepName.VERIFY_PORT_SPEED,
                            step_params=taac_thrift.Params(
                                json_params=json.dumps(
                                    {
                                        "neighbor_portmap": neighbor_portmap,
                                        "ports": speed_flip_ports,
                                        "speed_to_verify": original_speed,
                                    }
                                ),
                            ),
                        ),
                        taac_thrift.Step(
                            name=taac_thrift.StepName.REGISTER_SPEED_FLIP_PATCHER,
                            step_params=taac_thrift.Params(
                                json_params=json.dumps(
                                    {
                                        "neighbor_portmap": neighbor_portmap,
                                        "ports": speed_flip_ports,
                                        "apply_patcher_method": taac_thrift.ApplyPatcherMethod.AGENT_RELOAD_AND_WARMBOOT,
                                        "register_patcher": True,
                                        "speed": new_speed,
                                    }
                                ),
                            ),
                        ),
                        taac_thrift.Step(
                            name=taac_thrift.StepName.LONGEVITY_STEP,
                            step_params=taac_thrift.Params(
                                json_params='{"duration": 60}'
                            ),
                        ),
                        taac_thrift.Step(
                            name=taac_thrift.StepName.VERIFY_PORT_SPEED,
                            step_params=taac_thrift.Params(
                                json_params=json.dumps(
                                    {
                                        "neighbor_portmap": neighbor_portmap,
                                        "ports": speed_flip_ports,
                                        "speed_to_verify": new_speed,
                                    }
                                ),
                            ),
                        ),
                        taac_thrift.Step(
                            name=taac_thrift.StepName.REGISTER_SPEED_FLIP_PATCHER,
                            step_params=taac_thrift.Params(
                                json_params=json.dumps(
                                    {
                                        "neighbor_portmap": neighbor_portmap,
                                        "ports": speed_flip_ports,
                                        "apply_patcher_method": taac_thrift.ApplyPatcherMethod.AGENT_RELOAD_AND_WARMBOOT,
                                        "register_patcher": False,
                                    }
                                ),
                            ),
                        ),
                        taac_thrift.Step(
                            name=taac_thrift.StepName.LONGEVITY_STEP,
                            step_params=taac_thrift.Params(
                                json_params='{"duration": 60}'
                            ),
                        ),
                        taac_thrift.Step(
                            name=taac_thrift.StepName.VERIFY_PORT_SPEED,
                            step_params=taac_thrift.Params(
                                json_params=json.dumps(
                                    {
                                        "neighbor_portmap": neighbor_portmap,
                                        "ports": speed_flip_ports,
                                        "speed_to_verify": original_speed,
                                    }
                                ),
                            ),
                        ),
                    ]
                )
            ],
        ),
        taac_thrift.Playbook(
            name=f"test_speed_flip_agent_warmboot_{original_speed}g_to_{new_speed}g",
            stages=[
                taac_thrift.Stage(
                    steps=[
                        taac_thrift.Step(
                            name=taac_thrift.StepName.VERIFY_PORT_SPEED,
                            step_params=taac_thrift.Params(
                                json_params=json.dumps(
                                    {
                                        "neighbor_portmap": neighbor_portmap,
                                        "ports": speed_flip_ports,
                                        "speed_to_verify": original_speed,
                                    }
                                ),
                            ),
                        ),
                        taac_thrift.Step(
                            name=taac_thrift.StepName.REGISTER_SPEED_FLIP_PATCHER,
                            step_params=taac_thrift.Params(
                                json_params=json.dumps(
                                    {
                                        "neighbor_portmap": neighbor_portmap,
                                        "ports": speed_flip_ports,
                                        "apply_patcher_method": taac_thrift.ApplyPatcherMethod.AGENT_WARMBOOT,
                                        "register_patcher": True,
                                        "speed": new_speed,
                                    }
                                ),
                            ),
                        ),
                        taac_thrift.Step(
                            name=taac_thrift.StepName.VERIFY_PORT_SPEED,
                            step_params=taac_thrift.Params(
                                json_params=json.dumps(
                                    {
                                        "neighbor_portmap": neighbor_portmap,
                                        "ports": speed_flip_ports,
                                        "speed_to_verify": new_speed,
                                    }
                                ),
                            ),
                        ),
                        taac_thrift.Step(
                            name=taac_thrift.StepName.REGISTER_SPEED_FLIP_PATCHER,
                            step_params=taac_thrift.Params(
                                json_params=json.dumps(
                                    {
                                        "neighbor_portmap": neighbor_portmap,
                                        "ports": speed_flip_ports,
                                        "apply_patcher_method": taac_thrift.ApplyPatcherMethod.AGENT_WARMBOOT,
                                        "register_patcher": False,
                                    }
                                ),
                            ),
                        ),
                        taac_thrift.Step(
                            name=taac_thrift.StepName.VERIFY_PORT_SPEED,
                            step_params=taac_thrift.Params(
                                json_params=json.dumps(
                                    {
                                        "neighbor_portmap": neighbor_portmap,
                                        "ports": speed_flip_ports,
                                        "speed_to_verify": original_speed,
                                    }
                                ),
                            ),
                        ),
                    ]
                )
            ],
        ),
        taac_thrift.Playbook(
            name=f"test_agent_warmboot_before_apply_speed_flip_{original_speed}g_to_{new_speed}g",
            stages=[
                taac_thrift.Stage(
                    steps=[
                        taac_thrift.Step(
                            name=taac_thrift.StepName.VERIFY_PORT_SPEED,
                            step_params=taac_thrift.Params(
                                json_params=json.dumps(
                                    {
                                        "neighbor_portmap": neighbor_portmap,
                                        "ports": speed_flip_ports,
                                        "speed_to_verify": original_speed,
                                    }
                                ),
                            ),
                        ),
                        taac_thrift.Step(
                            name=taac_thrift.StepName.SERVICE_INTERRUPTION_STEP,
                            input_json=thrift_to_json(
                                taac_thrift.ServiceInterruptionInput(
                                    name=taac_thrift.Service.AGENT,
                                    trigger=taac_thrift.ServiceInterruptionTrigger.SYSTEMCTL_RESTART,
                                )
                            ),
                        ),
                        taac_thrift.Step(
                            name=taac_thrift.StepName.REGISTER_SPEED_FLIP_PATCHER,
                            step_params=taac_thrift.Params(
                                json_params=json.dumps(
                                    {
                                        "neighbor_portmap": neighbor_portmap,
                                        "ports": speed_flip_ports,
                                        "apply_patcher_method": taac_thrift.ApplyPatcherMethod.AGENT_RELOAD_AND_WARMBOOT,
                                        "register_patcher": True,
                                        "speed": new_speed,
                                    }
                                ),
                            ),
                        ),
                        taac_thrift.Step(
                            name=taac_thrift.StepName.VERIFY_PORT_SPEED,
                            step_params=taac_thrift.Params(
                                json_params=json.dumps(
                                    {
                                        "neighbor_portmap": neighbor_portmap,
                                        "ports": speed_flip_ports,
                                        "speed_to_verify": new_speed,
                                    }
                                ),
                            ),
                        ),
                        taac_thrift.Step(
                            name=taac_thrift.StepName.REGISTER_SPEED_FLIP_PATCHER,
                            step_params=taac_thrift.Params(
                                json_params=json.dumps(
                                    {
                                        "neighbor_portmap": neighbor_portmap,
                                        "ports": speed_flip_ports,
                                        "apply_patcher_method": taac_thrift.ApplyPatcherMethod.AGENT_WARMBOOT,
                                        "register_patcher": False,
                                    }
                                ),
                            ),
                        ),
                        taac_thrift.Step(
                            name=taac_thrift.StepName.VERIFY_PORT_SPEED,
                            step_params=taac_thrift.Params(
                                json_params=json.dumps(
                                    {
                                        "neighbor_portmap": neighbor_portmap,
                                        "ports": speed_flip_ports,
                                        "speed_to_verify": original_speed,
                                    }
                                ),
                            ),
                        ),
                    ]
                )
            ],
        ),
        taac_thrift.Playbook(
            name=f"test_agent_warmboot_before_delete_speed_flip_{original_speed}g_to_{new_speed}g",
            stages=[
                taac_thrift.Stage(
                    steps=[
                        taac_thrift.Step(
                            name=taac_thrift.StepName.VERIFY_PORT_SPEED,
                            step_params=taac_thrift.Params(
                                json_params=json.dumps(
                                    {
                                        "neighbor_portmap": neighbor_portmap,
                                        "ports": speed_flip_ports,
                                        "speed_to_verify": original_speed,
                                    }
                                ),
                            ),
                        ),
                        taac_thrift.Step(
                            name=taac_thrift.StepName.REGISTER_SPEED_FLIP_PATCHER,
                            step_params=taac_thrift.Params(
                                json_params=json.dumps(
                                    {
                                        "neighbor_portmap": neighbor_portmap,
                                        "ports": speed_flip_ports,
                                        "apply_patcher_method": taac_thrift.ApplyPatcherMethod.AGENT_RELOAD_AND_WARMBOOT,
                                        "register_patcher": True,
                                        "speed": new_speed,
                                    }
                                ),
                            ),
                        ),
                        taac_thrift.Step(
                            name=taac_thrift.StepName.VERIFY_PORT_SPEED,
                            step_params=taac_thrift.Params(
                                json_params=json.dumps(
                                    {
                                        "neighbor_portmap": neighbor_portmap,
                                        "ports": speed_flip_ports,
                                        "speed_to_verify": new_speed,
                                    }
                                ),
                            ),
                        ),
                        taac_thrift.Step(
                            name=taac_thrift.StepName.SERVICE_INTERRUPTION_STEP,
                            input_json=thrift_to_json(
                                taac_thrift.ServiceInterruptionInput(
                                    name=taac_thrift.Service.AGENT,
                                    trigger=taac_thrift.ServiceInterruptionTrigger.SYSTEMCTL_RESTART,
                                )
                            ),
                        ),
                        taac_thrift.Step(
                            name=taac_thrift.StepName.SERVICE_CONVERGENCE_STEP,
                            input_json=thrift_to_json(
                                taac_thrift.ServiceConvergenceInput(
                                    services=[taac_thrift.Service.AGENT],
                                )
                            ),
                        ),
                        taac_thrift.Step(
                            name=taac_thrift.StepName.REGISTER_SPEED_FLIP_PATCHER,
                            step_params=taac_thrift.Params(
                                json_params=json.dumps(
                                    {
                                        "neighbor_portmap": neighbor_portmap,
                                        "ports": speed_flip_ports,
                                        "apply_patcher_method": taac_thrift.ApplyPatcherMethod.AGENT_RELOAD_AND_WARMBOOT,
                                        "register_patcher": False,
                                    }
                                ),
                            ),
                        ),
                        taac_thrift.Step(
                            name=taac_thrift.StepName.VERIFY_PORT_SPEED,
                            step_params=taac_thrift.Params(
                                json_params=json.dumps(
                                    {
                                        "neighbor_portmap": neighbor_portmap,
                                        "ports": speed_flip_ports,
                                        "speed_to_verify": original_speed,
                                    }
                                ),
                            ),
                        ),
                    ]
                )
            ],
        ),
        taac_thrift.Playbook(
            name=f"test_speed_flip_apply_patcher_agent_crash_{original_speed}g_to_{new_speed}g",
            postchecks_to_skip=[hc_thrift.CheckName.UNCLEAN_EXIT_CHECK],
            stages=[
                taac_thrift.Stage(
                    steps=[
                        taac_thrift.Step(
                            name=taac_thrift.StepName.VERIFY_PORT_SPEED,
                            step_params=taac_thrift.Params(
                                json_params=json.dumps(
                                    {
                                        "neighbor_portmap": neighbor_portmap,
                                        "ports": speed_flip_ports,
                                        "speed_to_verify": original_speed,
                                    }
                                ),
                            ),
                        ),
                        taac_thrift.Step(
                            name=taac_thrift.StepName.REGISTER_SPEED_FLIP_PATCHER,
                            step_params=taac_thrift.Params(
                                json_params=json.dumps(
                                    {
                                        "neighbor_portmap": neighbor_portmap,
                                        "ports": speed_flip_ports,
                                        "register_patcher": True,
                                        "speed": new_speed,
                                        "apply_patcher_method": taac_thrift.ApplyPatcherMethod.AGENT_RELOAD,
                                    }
                                ),
                            ),
                        ),
                        taac_thrift.Step(
                            name=taac_thrift.StepName.SERVICE_INTERRUPTION_STEP,
                            input_json=thrift_to_json(
                                taac_thrift.ServiceInterruptionInput(
                                    name=taac_thrift.Service.AGENT,
                                    trigger=taac_thrift.ServiceInterruptionTrigger.CRASH,
                                )
                            ),
                        ),
                        taac_thrift.Step(
                            name=taac_thrift.StepName.SERVICE_CONVERGENCE_STEP,
                            input_json=thrift_to_json(
                                taac_thrift.ServiceConvergenceInput(
                                    services=[taac_thrift.Service.AGENT],
                                )
                            ),
                        ),
                        taac_thrift.Step(
                            name=taac_thrift.StepName.LONGEVITY_STEP,
                            step_params=taac_thrift.Params(
                                json_params='{"duration": 180}'
                            ),
                        ),
                        taac_thrift.Step(
                            name=taac_thrift.StepName.VERIFY_PORT_SPEED,
                            step_params=taac_thrift.Params(
                                json_params=json.dumps(
                                    {
                                        "neighbor_portmap": neighbor_portmap,
                                        "ports": speed_flip_ports,
                                        "speed_to_verify": new_speed,
                                    }
                                ),
                            ),
                        ),
                        taac_thrift.Step(
                            name=taac_thrift.StepName.REGISTER_SPEED_FLIP_PATCHER,
                            step_params=taac_thrift.Params(
                                json_params=json.dumps(
                                    {
                                        "neighbor_portmap": neighbor_portmap,
                                        "ports": speed_flip_ports,
                                        "apply_patcher_method": taac_thrift.ApplyPatcherMethod.AGENT_WARMBOOT,
                                        "register_patcher": False,
                                    }
                                ),
                            ),
                        ),
                        taac_thrift.Step(
                            name=taac_thrift.StepName.VERIFY_PORT_SPEED,
                            step_params=taac_thrift.Params(
                                json_params=json.dumps(
                                    {
                                        "neighbor_portmap": neighbor_portmap,
                                        "ports": speed_flip_ports,
                                        "speed_to_verify": original_speed,
                                    }
                                ),
                            ),
                        ),
                    ]
                )
            ],
        ),
        taac_thrift.Playbook(
            name=f"test_speed_flip_delete_patcher_agent_crash_{original_speed}g_to_{new_speed}g",
            postchecks_to_skip=[hc_thrift.CheckName.UNCLEAN_EXIT_CHECK],
            stages=[
                taac_thrift.Stage(
                    steps=[
                        taac_thrift.Step(
                            name=taac_thrift.StepName.VERIFY_PORT_SPEED,
                            step_params=taac_thrift.Params(
                                json_params=json.dumps(
                                    {
                                        "neighbor_portmap": neighbor_portmap,
                                        "ports": speed_flip_ports,
                                        "speed_to_verify": original_speed,
                                    }
                                ),
                            ),
                        ),
                        taac_thrift.Step(
                            name=taac_thrift.StepName.REGISTER_SPEED_FLIP_PATCHER,
                            step_params=taac_thrift.Params(
                                json_params=json.dumps(
                                    {
                                        "neighbor_portmap": neighbor_portmap,
                                        "ports": speed_flip_ports,
                                        "apply_patcher_method": taac_thrift.ApplyPatcherMethod.AGENT_RELOAD_AND_WARMBOOT,
                                        "register_patcher": True,
                                        "speed": new_speed,
                                    }
                                ),
                            ),
                        ),
                        taac_thrift.Step(
                            name=taac_thrift.StepName.VERIFY_PORT_SPEED,
                            step_params=taac_thrift.Params(
                                json_params=json.dumps(
                                    {
                                        "neighbor_portmap": neighbor_portmap,
                                        "ports": speed_flip_ports,
                                        "speed_to_verify": new_speed,
                                    }
                                ),
                            ),
                        ),
                        taac_thrift.Step(
                            name=taac_thrift.StepName.REGISTER_SPEED_FLIP_PATCHER,
                            step_params=taac_thrift.Params(
                                json_params=json.dumps(
                                    {
                                        "neighbor_portmap": neighbor_portmap,
                                        "ports": speed_flip_ports,
                                        "register_patcher": False,
                                        "apply_patcher_method": taac_thrift.ApplyPatcherMethod.AGENT_RELOAD,
                                    }
                                ),
                            ),
                        ),
                        taac_thrift.Step(
                            name=taac_thrift.StepName.SERVICE_INTERRUPTION_STEP,
                            input_json=thrift_to_json(
                                taac_thrift.ServiceInterruptionInput(
                                    name=taac_thrift.Service.AGENT,
                                    trigger=taac_thrift.ServiceInterruptionTrigger.CRASH,
                                )
                            ),
                        ),
                        taac_thrift.Step(
                            name=taac_thrift.StepName.SERVICE_CONVERGENCE_STEP,
                            input_json=thrift_to_json(
                                taac_thrift.ServiceConvergenceInput(
                                    services=[taac_thrift.Service.AGENT],
                                )
                            ),
                        ),
                        taac_thrift.Step(
                            name=taac_thrift.StepName.LONGEVITY_STEP,
                            step_params=taac_thrift.Params(
                                json_params='{"duration": 180}'
                            ),
                        ),
                        taac_thrift.Step(
                            name=taac_thrift.StepName.VERIFY_PORT_SPEED,
                            step_params=taac_thrift.Params(
                                json_params=json.dumps(
                                    {
                                        "neighbor_portmap": neighbor_portmap,
                                        "ports": speed_flip_ports,
                                        "speed_to_verify": original_speed,
                                    }
                                ),
                            ),
                        ),
                    ]
                )
            ],
        ),
        taac_thrift.Playbook(
            name=f"test_speed_flip_apply_patcher_coop_crash_{original_speed}g_to_{new_speed}g",
            postchecks_to_skip=[hc_thrift.CheckName.UNCLEAN_EXIT_CHECK],
            stages=[
                taac_thrift.Stage(
                    steps=[
                        taac_thrift.Step(
                            name=taac_thrift.StepName.VERIFY_PORT_SPEED,
                            step_params=taac_thrift.Params(
                                json_params=json.dumps(
                                    {
                                        "neighbor_portmap": neighbor_portmap,
                                        "ports": speed_flip_ports,
                                        "speed_to_verify": original_speed,
                                    }
                                ),
                            ),
                        ),
                        taac_thrift.Step(
                            name=taac_thrift.StepName.REGISTER_SPEED_FLIP_PATCHER,
                            step_params=taac_thrift.Params(
                                json_params=json.dumps(
                                    {
                                        "neighbor_portmap": neighbor_portmap,
                                        "ports": speed_flip_ports,
                                        "register_patcher": True,
                                        "speed": new_speed,
                                    }
                                ),
                            ),
                        ),
                        taac_thrift.Step(
                            name=taac_thrift.StepName.SERVICE_INTERRUPTION_STEP,
                            input_json=thrift_to_json(
                                taac_thrift.ServiceInterruptionInput(
                                    name=taac_thrift.Service.COOP,
                                    trigger=taac_thrift.ServiceInterruptionTrigger.CRASH,
                                )
                            ),
                        ),
                        taac_thrift.Step(
                            name=taac_thrift.StepName.SERVICE_CONVERGENCE_STEP,
                            input_json=thrift_to_json(
                                taac_thrift.ServiceConvergenceInput(
                                    services=[taac_thrift.Service.AGENT],
                                )
                            ),
                        ),
                        taac_thrift.Step(
                            name=taac_thrift.StepName.VERIFY_PORT_SPEED,
                            step_params=taac_thrift.Params(
                                json_params=json.dumps(
                                    {
                                        "neighbor_portmap": neighbor_portmap,
                                        "ports": speed_flip_ports,
                                        "speed_to_verify": new_speed,
                                    }
                                ),
                            ),
                        ),
                        taac_thrift.Step(
                            name=taac_thrift.StepName.REGISTER_SPEED_FLIP_PATCHER,
                            step_params=taac_thrift.Params(
                                json_params=json.dumps(
                                    {
                                        "neighbor_portmap": neighbor_portmap,
                                        "ports": speed_flip_ports,
                                        "apply_patcher_method": taac_thrift.ApplyPatcherMethod.AGENT_WARMBOOT,
                                        "register_patcher": False,
                                    }
                                ),
                            ),
                        ),
                        taac_thrift.Step(
                            name=taac_thrift.StepName.VERIFY_PORT_SPEED,
                            step_params=taac_thrift.Params(
                                json_params=json.dumps(
                                    {
                                        "neighbor_portmap": neighbor_portmap,
                                        "ports": speed_flip_ports,
                                        "speed_to_verify": original_speed,
                                    }
                                ),
                            ),
                        ),
                    ]
                )
            ],
        ),
        taac_thrift.Playbook(
            name=f"test_speed_flip_delete_patcher_coop_crash_{original_speed}g_to_{new_speed}g",
            postchecks_to_skip=[hc_thrift.CheckName.UNCLEAN_EXIT_CHECK],
            stages=[
                taac_thrift.Stage(
                    steps=[
                        taac_thrift.Step(
                            name=taac_thrift.StepName.VERIFY_PORT_SPEED,
                            step_params=taac_thrift.Params(
                                json_params=json.dumps(
                                    {
                                        "neighbor_portmap": neighbor_portmap,
                                        "ports": speed_flip_ports,
                                        "speed_to_verify": original_speed,
                                    }
                                ),
                            ),
                        ),
                        taac_thrift.Step(
                            name=taac_thrift.StepName.REGISTER_SPEED_FLIP_PATCHER,
                            step_params=taac_thrift.Params(
                                json_params=json.dumps(
                                    {
                                        "neighbor_portmap": neighbor_portmap,
                                        "ports": speed_flip_ports,
                                        "apply_patcher_method": taac_thrift.ApplyPatcherMethod.AGENT_RELOAD,
                                        "register_patcher": True,
                                        "speed": new_speed,
                                    }
                                ),
                            ),
                        ),
                        taac_thrift.Step(
                            name=taac_thrift.StepName.VERIFY_PORT_SPEED,
                            step_params=taac_thrift.Params(
                                json_params=json.dumps(
                                    {
                                        "neighbor_portmap": neighbor_portmap,
                                        "ports": speed_flip_ports,
                                        "speed_to_verify": new_speed,
                                    }
                                ),
                            ),
                        ),
                        taac_thrift.Step(
                            name=taac_thrift.StepName.REGISTER_SPEED_FLIP_PATCHER,
                            step_params=taac_thrift.Params(
                                json_params=json.dumps(
                                    {
                                        "neighbor_portmap": neighbor_portmap,
                                        "ports": speed_flip_ports,
                                        "register_patcher": False,
                                    }
                                ),
                            ),
                        ),
                        taac_thrift.Step(
                            name=taac_thrift.StepName.SERVICE_INTERRUPTION_STEP,
                            input_json=thrift_to_json(
                                taac_thrift.ServiceInterruptionInput(
                                    name=taac_thrift.Service.COOP,
                                    trigger=taac_thrift.ServiceInterruptionTrigger.CRASH,
                                )
                            ),
                        ),
                        taac_thrift.Step(
                            name=taac_thrift.StepName.SERVICE_CONVERGENCE_STEP,
                            input_json=thrift_to_json(
                                taac_thrift.ServiceConvergenceInput(
                                    services=[
                                        taac_thrift.Service.AGENT,
                                        taac_thrift.Service.COOP,
                                    ],
                                )
                            ),
                        ),
                        taac_thrift.Step(
                            name=taac_thrift.StepName.VERIFY_PORT_SPEED,
                            step_params=taac_thrift.Params(
                                json_params=json.dumps(
                                    {
                                        "neighbor_portmap": neighbor_portmap,
                                        "ports": speed_flip_ports,
                                        "speed_to_verify": original_speed,
                                    }
                                ),
                            ),
                        ),
                    ]
                )
            ],
        ),
    ]
