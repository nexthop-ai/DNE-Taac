# Copyright (c) Meta Platforms, Inc. and affiliates.

# pyre-unsafe

import json

from taac.testconfigs.configerator.test_config import (
    thrift_to_json,
)
from taac.health_check.health_check import types as hc_thrift
from taac.test_as_a_config.types import (
    DrainUndrainInput,
    Params,
    Playbook,
    PointInTimeHealthCheck,
    Service,
    ServiceConvergenceInput,
    ServiceInterruptionInput,
    ServiceInterruptionTrigger,
    Stage,
    Step,
    StepName,
    SystemRebootInput,
    SystemRebootTrigger,
    TransformFunction,
    ValidationInput,
    ValidationStage,
)


def get_ptp_longevity_playbook():
    """Basic longevity test playbook for PTP configurations."""
    return Playbook(
        name="test_longevity",
        stages=[
            Stage(
                steps=[
                    Step(
                        name=StepName.LONGEVITY_STEP,
                        step_params=Params(
                            json_params=json.dumps(
                                {
                                    "duration": 120,
                                }
                            ),
                        ),
                    ),
                ],
            )
        ],
    )


def get_ptp_xcvr_restart_playbook(device_hostname: str):
    """XCVR agent restart playbook for PTP configurations."""
    return Playbook(
        name="test_xcvr_restart",
        device_regexes=[device_hostname],
        stages=[
            Stage(
                steps=[
                    Step(
                        name=StepName.SERVICE_INTERRUPTION_STEP,
                        input_json=thrift_to_json(
                            ServiceInterruptionInput(
                                name=Service.ARISTA_XCVR_AGENT,
                                trigger=ServiceInterruptionTrigger.SYSTEMCTL_RESTART,
                            )
                        ),
                    ),
                ]
            )
        ],
    )


def get_ptp_xcvr_ungraceful_restart_playbook(device_hostname: str):
    """XCVR agent ungraceful restart playbook for PTP configurations."""
    return Playbook(
        name="test_xcvr_ungraceful_restart",
        device_regexes=[device_hostname],
        stages=[
            Stage(
                steps=[
                    Step(
                        name=StepName.SERVICE_INTERRUPTION_STEP,
                        input_json=thrift_to_json(
                            ServiceInterruptionInput(
                                name=Service.ARISTA_XCVR_AGENT,
                                trigger=ServiceInterruptionTrigger.CRASH,
                            )
                        ),
                    ),
                ]
            )
        ],
    )


def get_ptp_l3_forwarding_agent_restart_playbook(device_hostname: str):
    """L3 forwarding agent restart playbook for PTP configurations."""
    return Playbook(
        name="test_l3_forwarding_agent_restart",
        device_regexes=[device_hostname],
        stages=[
            Stage(
                steps=[
                    Step(
                        name=StepName.SERVICE_INTERRUPTION_STEP,
                        input_json=thrift_to_json(
                            ServiceInterruptionInput(
                                name=Service.ARISTA_L3_FORWARDING_AGENT,
                                trigger=ServiceInterruptionTrigger.SYSTEMCTL_RESTART,
                            )
                        ),
                    ),
                ]
            )
        ],
    )


def get_port_flap_playbook(
    device_hostname: str,
    interface_to_flap: list,
    iteration: int = 1,
):
    """
    Create a playbook for port flap testing with PTP configurations.

    Args:
        device_hostname: Hostname of the device to run the test on
        interface_to_flap: List of interfaces to flap
        iteration: Number of iterations (default: 1)

    Returns:
        Playbook: A configured port flap playbook for PTP
    """
    return Playbook(
        name="test_port_flap_ptp",
        device_regexes=[device_hostname],
        prechecks=[
            PointInTimeHealthCheck(
                name=hc_thrift.CheckName.PORT_STATE_CHECK,
            ),
        ],
        stages=[
            Stage(
                steps=[
                    Step(
                        name=StepName.INTERFACE_FLAP_STEP,
                        step_params=Params(
                            json_params=json.dumps(
                                {
                                    "interfaces": interface_to_flap,
                                    "interface_flap_method": 4,  # SSH_PORT_STATE_CHANGE
                                    "enable": False,
                                    "delay": 30,
                                }
                            )
                        ),
                    ),
                    Step(
                        name=StepName.INTERFACE_FLAP_STEP,
                        step_params=Params(
                            json_params=json.dumps(
                                {
                                    "interfaces": interface_to_flap,
                                    "interface_flap_method": 4,  # SSH_PORT_STATE_CHANGE
                                    "enable": True,
                                    "delay": 30,
                                }
                            )
                        ),
                    ),
                ]
            )
        ],
        postchecks=[
            PointInTimeHealthCheck(
                name=hc_thrift.CheckName.IXIA_PACKET_LOSS_CHECK,
                input_json=thrift_to_json(
                    hc_thrift.IxiaPacketLossHealthCheckIn(
                        clear_traffic_stats=True,
                        thresholds=[hc_thrift.PacketLossThreshold(str_value="0.1")],
                    )
                ),
            ),
            PointInTimeHealthCheck(
                name=hc_thrift.CheckName.IXIA_PTP_CHECK,
                check_params=Params(json_params=json.dumps({"clear_ptp_stats": True})),
            ),
            PointInTimeHealthCheck(
                name=hc_thrift.CheckName.PORT_STATE_CHECK,
            ),
        ],
        iteration=iteration,
    )


def get_ptp_interface_flap_playbook(device_hostnames: list):
    """Interface flap playbook for PTP configurations with multiple devices."""
    return Playbook(
        name="test_interface_flap",
        device_regexes=device_hostnames,
        stages=[
            Stage(
                steps=[
                    Step(
                        name=StepName.INTERFACE_FLAP_STEP,
                        step_params=Params(
                            json_params=json.dumps(
                                {
                                    "enable": False,
                                    "interface_flap_method": 4,
                                    "delay": 30,
                                }
                            ),
                            jq_params={"interfaces": '."{dut}".interfaces'},
                            transform_params={
                                "interfaces": [
                                    TransformFunction(
                                        name="SELECT_SAMPLE",
                                        json_params=json.dumps({"sample_size": 1}),
                                    )
                                ]
                            },
                            cache_params={
                                "interfaces": "random_interface",
                            },
                        ),
                    ),
                    Step(
                        name=StepName.VALIDATION_STEP,
                        input_json=thrift_to_json(
                            ValidationInput(
                                point_in_time_checks=[
                                    PointInTimeHealthCheck(
                                        name=hc_thrift.CheckName.IXIA_PACKET_LOSS_CHECK,
                                        input_json=thrift_to_json(
                                            hc_thrift.IxiaPacketLossHealthCheckIn(
                                                clear_traffic_stats=True,
                                                thresholds=[
                                                    hc_thrift.PacketLossThreshold(
                                                        str_value="0.1"
                                                    )
                                                ],
                                            )
                                        ),
                                    ),
                                ],
                                stage=ValidationStage.MID_TEST,
                            )
                        ),
                    ),
                    Step(
                        name=StepName.INTERFACE_FLAP_STEP,
                        step_params=Params(
                            json_params=json.dumps(
                                {
                                    "enable": True,
                                    "interface_flap_method": 4,
                                    "delay": 30,
                                }
                            ),
                            jq_params={"interfaces": ".cached.random_interface"},
                        ),
                    ),
                ],
            )
        ],
    )


def get_ptp_continuous_interface_flap_playbook(device_hostnames: list):
    """Continuous interface flap playbook for PTP configurations with multiple devices."""
    return Playbook(
        name="test_continuous_interface_flap",
        device_regexes=device_hostnames,
        postchecks=[
            PointInTimeHealthCheck(
                name=hc_thrift.CheckName.IXIA_PACKET_LOSS_CHECK,
                input_json=thrift_to_json(
                    hc_thrift.IxiaPacketLossHealthCheckIn(
                        thresholds=[hc_thrift.PacketLossThreshold(str_value="0.1")],
                        clear_traffic_stats=True,
                    )
                ),
            ),
            PointInTimeHealthCheck(
                name=hc_thrift.CheckName.IXIA_PTP_CHECK,
                check_params=Params(json_params=json.dumps({"clear_ptp_stats": True})),
            ),
        ],
        stages=[
            Stage(
                iteration=10,
                steps=[
                    Step(
                        name=StepName.INTERFACE_FLAP_STEP,
                        step_params=Params(
                            json_params=json.dumps(
                                {
                                    "enable": False,
                                    "interface_flap_method": 4,
                                    "delay": 30,
                                }
                            ),
                            jq_params={"interfaces": '."{dut}".interfaces'},
                            transform_params={
                                "interfaces": [
                                    TransformFunction(
                                        name="SELECT_SAMPLE",
                                        json_params=json.dumps({"sample_size": 1}),
                                    )
                                ]
                            },
                            cache_params={
                                "interfaces": "random_interface",
                            },
                        ),
                    ),
                    Step(
                        name=StepName.INTERFACE_FLAP_STEP,
                        step_params=Params(
                            json_params=json.dumps(
                                {
                                    "enable": True,
                                    "interface_flap_method": 4,
                                    "delay": 30,
                                }
                            ),
                            jq_params={"interfaces": ".cached.random_interface"},
                        ),
                    ),
                ],
            )
        ],
    )


def get_ptp_agent_warmboot_playbook(device_hostname: str):
    """Agent warmboot playbook for PTP configurations."""
    return Playbook(
        name="test_agent_warmboot",
        device_regexes=[device_hostname],
        stages=[
            Stage(
                steps=[
                    Step(
                        name=StepName.SERVICE_INTERRUPTION_STEP,
                        input_json=thrift_to_json(
                            ServiceInterruptionInput(
                                name=Service.AGENT,
                                trigger=ServiceInterruptionTrigger.SYSTEMCTL_RESTART,
                            )
                        ),
                    ),
                    Step(
                        name=StepName.SERVICE_CONVERGENCE_STEP,
                    ),
                ]
            )
        ],
    )


def get_ptp_continuous_agent_warmboot_playbook(device_hostname: str):
    """Continuous agent warmboot playbook for PTP configurations."""
    return Playbook(
        name="test_continuous_agent_warmboot",
        stages=[
            Stage(
                steps=[
                    Step(
                        name=StepName.SERVICE_INTERRUPTION_STEP,
                        input_json=thrift_to_json(
                            ServiceInterruptionInput(
                                name=Service.AGENT,
                                trigger=ServiceInterruptionTrigger.SYSTEMCTL_RESTART,
                            )
                        ),
                    ),
                    Step(
                        name=StepName.SERVICE_CONVERGENCE_STEP,
                        input_json=thrift_to_json(
                            ServiceConvergenceInput(
                                services=[Service.AGENT],
                            )
                        ),
                    ),
                ],
            ),
            Stage(
                steps=[
                    Step(
                        name=StepName.LONGEVITY_STEP,
                        step_params=Params(json_params='{"duration": 120}'),
                    ),
                ]
            ),
        ],
        iteration=5,
    )


def get_ptp_bgp_restart_playbook(device_hostname: str):
    """BGP restart playbook for PTP configurations."""
    return Playbook(
        name="test_bgp_restart",
        device_regexes=[device_hostname],
        stages=[
            Stage(
                steps=[
                    Step(
                        name=StepName.SERVICE_INTERRUPTION_STEP,
                        input_json=thrift_to_json(
                            ServiceInterruptionInput(
                                name=Service.BGP,
                                trigger=ServiceInterruptionTrigger.SYSTEMCTL_RESTART,
                            )
                        ),
                    ),
                    Step(
                        name=StepName.SERVICE_CONVERGENCE_STEP,
                    ),
                ]
            )
        ],
    )


def get_ptp_interface_drain_playbook(device_hostname: str):
    """Interface drain playbook for PTP configurations."""
    return Playbook(
        name="test_interface_drain",
        device_regexes=[device_hostname],
        stages=[
            Stage(
                steps=[
                    Step(
                        name=StepName.DRAIN_UNDRAIN_STEP,
                        input_json=thrift_to_json(
                            DrainUndrainInput(
                                drain=True,
                            )
                        ),
                        step_params=Params(
                            jq_params={"interfaces": '."{dut}".interfaces'},
                            transform_params={
                                "interfaces": [
                                    TransformFunction(
                                        name="SELECT_SAMPLE",
                                        json_params=json.dumps({"sample_size": 1}),
                                    )
                                ]
                            },
                            cache_params={
                                "interfaces": "random_interface",
                            },
                        ),
                    ),
                    Step(
                        name=StepName.DRAIN_UNDRAIN_STEP,
                        input_json=thrift_to_json(
                            DrainUndrainInput(
                                drain=False,
                            )
                        ),
                        step_params=Params(
                            jq_params={"interfaces": ".cached.random_interface"},
                        ),
                    ),
                ]
            )
        ],
    )


def get_ptp_device_drain_playbook(device_hostname: str):
    """Device drain playbook for PTP configurations."""
    return Playbook(
        name="test_device_drain",
        device_regexes=[device_hostname],
        stages=[
            Stage(
                steps=[
                    Step(
                        name=StepName.DRAIN_UNDRAIN_STEP,
                        input_json=thrift_to_json(
                            DrainUndrainInput(
                                drain=True,
                            )
                        ),
                    ),
                    Step(
                        name=StepName.DRAIN_UNDRAIN_STEP,
                        input_json=thrift_to_json(
                            DrainUndrainInput(
                                drain=False,
                            )
                        ),
                    ),
                ]
            )
        ],
    )


def get_ptp_device_reboot_playbook(device_hostname: str):
    """Device reboot playbook for PTP configurations."""
    return Playbook(
        name="test_device_reboot",
        device_regexes=[device_hostname],
        postchecks=[
            PointInTimeHealthCheck(
                name=hc_thrift.CheckName.IXIA_PACKET_LOSS_CHECK,
                input_json=thrift_to_json(
                    hc_thrift.IxiaPacketLossHealthCheckIn(
                        clear_traffic_stats=True,
                    )
                ),
            ),
            PointInTimeHealthCheck(
                name=hc_thrift.CheckName.IXIA_PTP_CHECK,
                check_params=Params(json_params=json.dumps({"clear_ptp_stats": True})),
            ),
        ],
        stages=[
            Stage(
                steps=[
                    Step(
                        name=StepName.SYSTEM_REBOOT_STEP,
                        input_json=thrift_to_json(
                            SystemRebootInput(
                                trigger=SystemRebootTrigger.FULL_SYSTEM_REBOOT,
                            )
                        ),
                    ),
                    Step(
                        name=StepName.SERVICE_CONVERGENCE_STEP,
                        input_json=thrift_to_json(
                            ServiceConvergenceInput(
                                services=[
                                    Service.AGENT,
                                ],
                            )
                        ),
                    ),
                    Step(
                        name=StepName.LONGEVITY_STEP,
                        step_params=Params(
                            json_params=json.dumps(
                                {
                                    "duration": 1800,  # 30 minutes
                                }
                            ),
                        ),
                    ),
                ]
            )
        ],
    )
