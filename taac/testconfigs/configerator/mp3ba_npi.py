# Copyright (c) Meta Platforms, Inc. and affiliates.

# pyre-unsafe

import json

from ixia.ixia import types as ixia_thrift
from taac.testconfigs.configerator.test_config import (
    thrift_to_json,
)
from taac.health_check.health_check import types as hc_thrift
from taac.test_as_a_config import types as taac_thrift

test_config = taac_thrift.TestConfig(
    name="MP3BA_NPI",
    basset_pool="dne.test",
    ignore_circuit_fbnet_status=True,
    endpoints=[
        taac_thrift.Endpoint(
            name="fsw003.p005.f01.qza1", dut=True, ixia_ports=["eth1/64/1", "eth1/64/5"]
        ),
    ],
    postchecks=[
        taac_thrift.PointInTimeHealthCheck(
            name=hc_thrift.CheckName.LLDP_CHECK,
        ),
        taac_thrift.PointInTimeHealthCheck(
            name=hc_thrift.CheckName.PORT_STATE_CHECK,
        ),
        taac_thrift.PointInTimeHealthCheck(
            name=hc_thrift.CheckName.IXIA_PACKET_LOSS_CHECK,
        ),
    ],
    prechecks=[
        taac_thrift.PointInTimeHealthCheck(
            name=hc_thrift.CheckName.LLDP_CHECK,
        ),
        taac_thrift.PointInTimeHealthCheck(
            name=hc_thrift.CheckName.PORT_STATE_CHECK,
        ),
        taac_thrift.PointInTimeHealthCheck(
            name=hc_thrift.CheckName.IXIA_PACKET_LOSS_CHECK,
        ),
    ],
    snapshot_checks=[
        taac_thrift.SnapshotHealthCheck(name=hc_thrift.CheckName.CORE_DUMPS_CHECK)
    ],
    basic_traffic_item_configs=[
        taac_thrift.BasicTrafficItemConfig(
            bidirectional=True,
            merge_destinations=True,
            line_rate=2,
            src_dest_mesh=ixia_thrift.SrcDestMeshType.MANY_TO_MANY,
            src_endpoints=[
                taac_thrift.TrafficEndpoint(
                    name="fsw003.p005.f01.qza1:eth1/64/1",
                    device_group_index=0,
                    network_group_index=0,
                )
            ],
            dest_endpoints=[
                taac_thrift.TrafficEndpoint(
                    name="fsw003.p005.f01.qza1:eth1/64/5",
                    device_group_index=0,
                    network_group_index=0,
                )
            ],
            traffic_type=ixia_thrift.TrafficType.IPV6,
            frame_size_settings=ixia_thrift.FrameSize(
                type=ixia_thrift.FrameSizeType.CUSTOM_IMIX
            ),
        ),
    ],
    basic_port_configs=[
        taac_thrift.BasicPortConfig(
            device_group_configs=[
                taac_thrift.DeviceGroupConfig(
                    multiplier=10,
                    device_group_index=0,
                    v6_bgp_config=taac_thrift.BgpConfig(
                        route_scales=[
                            taac_thrift.RouteScaleSpec(
                                network_group_index=0,
                                v6_route_scale=taac_thrift.RouteScale(
                                    multiplier=10,
                                    prefix_count=1500,
                                    prefix_length=64,
                                    starting_prefixes="2001:db8:1::",
                                    bgp_communities=[
                                        "65441:194",
                                        "65441:9001",
                                        "65441:9002",
                                        "65441:9003",
                                        "65441:9004",
                                        "65441:9005",
                                    ],
                                    prefix_step="0:0:0:1::",
                                    ip_address_family=ixia_thrift.IpAddressFamily.IPV6,
                                ),
                            ),
                        ],
                        enable_4_byte_local_as=True,
                        local_as_4_bytes=2025,
                        is_confed=True,
                    ),
                )
            ],
            endpoint="fsw003.p005.f01.qza1:eth1/64/1",
        ),
        taac_thrift.BasicPortConfig(
            device_group_configs=[
                taac_thrift.DeviceGroupConfig(
                    device_group_index=0,
                    multiplier=10,
                    v6_bgp_config=taac_thrift.BgpConfig(
                        route_scales=[
                            taac_thrift.RouteScaleSpec(
                                network_group_index=0,
                                v6_route_scale=taac_thrift.RouteScale(
                                    multiplier=10,
                                    prefix_count=1500,
                                    prefix_length=64,
                                    starting_prefixes="2001:db8:2::",
                                    bgp_communities=[
                                        "65441:194",
                                        "65441:9001",
                                        "65441:9002",
                                        "65441:9003",
                                        "65441:9004",
                                        "65441:9005",
                                    ],
                                    prefix_step="0:0:0:1::",
                                    ip_address_family=ixia_thrift.IpAddressFamily.IPV6,
                                ),
                            ),
                        ],
                        enable_4_byte_local_as=True,
                        local_as_4_bytes=2026,
                        is_confed=True,
                    ),
                )
            ],
            endpoint="fsw003.p005.f01.qza1:eth1/64/5",
        ),
    ],
    playbooks=[
        # taac_thrift.Playbook(
        #     name="test_bgpd_restart",
        #     iteration=10,
        #     device_regexes=["fsw003.p005.f01.qza1"],
        #     stages=[
        #         taac_thrift.Stage(
        #             steps=[
        #                 taac_thrift.Step(
        #                     name=taac_thrift.StepName.SERVICE_INTERRUPTION_STEP,
        #                     input_json=thrift_to_json(
        #                         taac_thrift.ServiceInterruptionInput(
        #                             name=taac_thrift.Service.BGP,
        #                             trigger=taac_thrift.ServiceInterruptionTrigger.SYSTEMCTL_RESTART,
        #                         )
        #                     ),
        #                 ),
        #                 taac_thrift.Step(
        #                     name=taac_thrift.StepName.SERVICE_CONVERGENCE_STEP,
        #                 ),
        #             ]
        #         )
        #     ],
        # ),
        # taac_thrift.Playbook(
        #     name="test_agent_warmboot",
        #     iteration=10,
        #     device_regexes=["fsw003.p005.f01.qza1"],
        #     stages=[
        #         taac_thrift.Stage(
        #             steps=[
        #                 taac_thrift.Step(
        #                     name=taac_thrift.StepName.SERVICE_INTERRUPTION_STEP,
        #                     input_json=thrift_to_json(
        #                         taac_thrift.ServiceInterruptionInput(
        #                             name=taac_thrift.Service.AGENT,
        #                             trigger=taac_thrift.ServiceInterruptionTrigger.SYSTEMCTL_RESTART,
        #                         )
        #                     ),
        #                 ),
        #                 taac_thrift.Step(
        #                     name=taac_thrift.StepName.SERVICE_CONVERGENCE_STEP,
        #                 ),
        #             ]
        #         )
        #     ],
        # ),
        taac_thrift.Playbook(
            name="test_agent_coldboot",
            iteration=10,
            device_regexes=["fsw003.p005.f01.qza1"],
            postchecks=[
                taac_thrift.PointInTimeHealthCheck(
                    name=hc_thrift.CheckName.IXIA_PACKET_LOSS_CHECK,
                    input_json=thrift_to_json(
                        hc_thrift.IxiaPacketLossHealthCheckIn(
                            clear_traffic_stats=True,
                        )
                    ),
                )
            ],
            stages=[
                taac_thrift.Stage(
                    steps=[
                        taac_thrift.Step(
                            name=taac_thrift.StepName.SERVICE_INTERRUPTION_STEP,
                            input_json=thrift_to_json(
                                taac_thrift.ServiceInterruptionInput(
                                    name=taac_thrift.Service.AGENT,
                                    trigger=taac_thrift.ServiceInterruptionTrigger.SYSTEMCTL_RESTART,
                                    create_cold_boot_file=True,
                                )
                            ),
                        ),
                        taac_thrift.Step(
                            name=taac_thrift.StepName.SERVICE_CONVERGENCE_STEP,
                        ),
                    ]
                )
            ],
        ),
        taac_thrift.Playbook(
            name="test_fsdb_restart",
            iteration=10,
            device_regexes=["fsw003.p005.f01.qza1"],
            stages=[
                taac_thrift.Stage(
                    steps=[
                        taac_thrift.Step(
                            name=taac_thrift.StepName.SERVICE_INTERRUPTION_STEP,
                            input_json=thrift_to_json(
                                taac_thrift.ServiceInterruptionInput(
                                    name=taac_thrift.Service.FSDB,
                                    trigger=taac_thrift.ServiceInterruptionTrigger.SYSTEMCTL_RESTART,
                                    create_cold_boot_file=True,
                                )
                            ),
                        ),
                        taac_thrift.Step(
                            name=taac_thrift.StepName.SERVICE_CONVERGENCE_STEP,
                        ),
                    ]
                )
            ],
        ),
        taac_thrift.Playbook(
            name="test_qsfp_restart",
            iteration=10,
            device_regexes=["fsw003.p005.f01.qza1"],
            stages=[
                taac_thrift.Stage(
                    steps=[
                        taac_thrift.Step(
                            name=taac_thrift.StepName.SERVICE_INTERRUPTION_STEP,
                            input_json=thrift_to_json(
                                taac_thrift.ServiceInterruptionInput(
                                    name=taac_thrift.Service.QSFP_SERVICE,
                                    trigger=taac_thrift.ServiceInterruptionTrigger.SYSTEMCTL_RESTART,
                                )
                            ),
                        ),
                        taac_thrift.Step(
                            name=taac_thrift.StepName.SERVICE_CONVERGENCE_STEP,
                        ),
                    ]
                )
            ],
        ),
        taac_thrift.Playbook(
            name="test_bgpd_crash",
            iteration=10,
            device_regexes=["fsw003.p005.f01.qza1"],
            stages=[
                taac_thrift.Stage(
                    steps=[
                        taac_thrift.Step(
                            name=taac_thrift.StepName.SERVICE_INTERRUPTION_STEP,
                            input_json=thrift_to_json(
                                taac_thrift.ServiceInterruptionInput(
                                    name=taac_thrift.Service.BGP,
                                    trigger=taac_thrift.ServiceInterruptionTrigger.CRASH,
                                )
                            ),
                        ),
                        taac_thrift.Step(
                            name=taac_thrift.StepName.SERVICE_CONVERGENCE_STEP,
                        ),
                    ]
                )
            ],
        ),
        taac_thrift.Playbook(
            name="test_agent_crash",
            iteration=10,
            device_regexes=["fsw003.p005.f01.qza1"],
            stages=[
                taac_thrift.Stage(
                    steps=[
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
                        ),
                    ]
                )
            ],
        ),
        taac_thrift.Playbook(
            name="test_device_drain",
            iteration=10,
            device_regexes=["fsw003.p005.f01.qza1"],
            stages=[
                taac_thrift.Stage(
                    steps=[
                        taac_thrift.Step(
                            name=taac_thrift.StepName.DRAIN_UNDRAIN_STEP,
                            input_json=thrift_to_json(
                                taac_thrift.DrainUndrainInput(
                                    drain=True,
                                )
                            ),
                        ),
                        taac_thrift.Step(
                            name=taac_thrift.StepName.DRAIN_UNDRAIN_STEP,
                            input_json=thrift_to_json(
                                taac_thrift.DrainUndrainInput(
                                    drain=False,
                                )
                            ),
                        ),
                    ]
                )
            ],
        ),
        taac_thrift.Playbook(
            name="test_device_reboot",
            iteration=10,
            device_regexes=["fsw003.p005.f01.qza1"],
            stages=[
                taac_thrift.Stage(
                    steps=[
                        taac_thrift.Step(
                            name=taac_thrift.StepName.SYSTEM_REBOOT_STEP,
                            input_json=thrift_to_json(
                                taac_thrift.SystemRebootInput(
                                    trigger=taac_thrift.SystemRebootTrigger.FULL_SYSTEM_REBOOT,
                                )
                            ),
                        ),
                        taac_thrift.Step(
                            name=taac_thrift.StepName.SERVICE_CONVERGENCE_STEP,
                        ),
                    ]
                )
            ],
        ),
        # taac_thrift.Playbook(
        #     name="test_interface_flap",
        #     device_regexes=["fsw003.p005.f01.qza1"],
        #     stages=[
        #         taac_thrift.Stage(
        #             steps=[
        #                 taac_thrift.Step(
        #                     name=taac_thrift.StepName.INTERFACE_FLAP_STEP,
        #                     step_params=taac_thrift.Params(
        #                         json_params=json.dumps(
        #                             {
        #                                 "enable": False,
        #                                 "interface_flap_method": 4,
        #                                 "delay": 30,
        #                             }
        #                         ),
        #                         jq_params={"interfaces": '."{dut}".interfaces'},
        #                         transform_params={
        #                             "interfaces": [
        #                                 taac_thrift.TransformFunction(
        #                                     name="SELECT_SAMPLE",
        #                                     json_params=json.dumps({"sample_size": 1}),
        #                                 )
        #                             ]
        #                         },
        #                         cache_params={
        #                             "interfaces": "random_interface",
        #                         },
        #                     ),
        #                 ),
        #                 taac_thrift.Step(
        #                     name=taac_thrift.StepName.INTERFACE_FLAP_STEP,
        #                     step_params=taac_thrift.Params(
        #                         json_params=json.dumps(
        #                             {
        #                                 "enable": True,
        #                                 "interface_flap_method": 4,
        #                                 "delay": 30,
        #                             }
        #                         ),
        #                         jq_params={"interfaces": ".cached.random_interface"},
        #                     ),
        #                 ),
        #             ],
        #         )
        #     ],
        # ),
        # taac_thrift.Playbook(
        #     name="test_simultaneous_interface_flap",
        #     device_regexes=["fsw003.p005.f01.qza1"],
        #     stages=[
        #         taac_thrift.Stage(
        #             steps=[
        #                 taac_thrift.Step(
        #                     name=taac_thrift.StepName.INTERFACE_FLAP_STEP,
        #                     step_params=taac_thrift.Params(
        #                         json_params=json.dumps(
        #                             {
        #                                 "enable": False,
        #                                 "interface_flap_method": 4,
        #                                 "delay": 30,
        #                             }
        #                         ),
        #                         jq_params={"interfaces": '."{dut}".interfaces'},
        #                         transform_params={
        #                             "interfaces": [
        #                                 taac_thrift.TransformFunction(
        #                                     name="SELECT_INTERFACES_BY_NEIGHBORS",
        #                                     json_params=json.dumps(
        #                                         {
        #                                             "neighbors": [
        #                                                 "fsw001.p001.m001.qzr1",
        #                                                 "fsw002.p001.m001.qzr1",
        #                                             ]
        #                                         }
        #                                     ),
        #                                 )
        #                             ]
        #                         },
        #                         cache_params={
        #                             "interfaces": "interfaces_to_fsw1_fsw2",
        #                         },
        #                     ),
        #                 ),
        #                 taac_thrift.Step(
        #                     name=taac_thrift.StepName.VALIDATION_STEP,
        #                     input_json=thrift_to_json(
        #                         taac_thrift.ValidationInput(
        #                             point_in_time_checks=[
        #                                 taac_thrift.PointInTimeHealthCheck(
        #                                     name=hc_thrift.CheckName.IXIA_PACKET_LOSS_CHECK,
        #                                     input_json=thrift_to_json(
        #                                         hc_thrift.IxiaPacketLossHealthCheckIn(
        #                                             thresholds=[
        #                                                 hc_thrift.PacketLossThreshold(
        #                                                     str_value="2"
        #                                                 )
        #                                             ]
        #                                         )
        #                                     ),
        #                                 ),
        #                             ],
        #                             stage=taac_thrift.ValidationStage.MID_TEST,
        #                         )
        #                     ),
        #                 ),
        #                 taac_thrift.Step(
        #                     name=taac_thrift.StepName.INTERFACE_FLAP_STEP,
        #                     step_params=taac_thrift.Params(
        #                         json_params=json.dumps(
        #                             {
        #                                 "enable": True,
        #                                 "interface_flap_method": 4,
        #                                 "delay": 30,
        #                             }
        #                         ),
        #                         jq_params={
        #                             "interfaces": ".cached.interfaces_to_fsw1_fsw2"
        #                         },
        #                     ),
        #                 ),
        #             ],
        #         )
        #     ],
        # ),
    ],
)

TEST_CONFIG = test_config
