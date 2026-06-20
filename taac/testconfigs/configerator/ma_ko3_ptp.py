# Copyright (c) Meta Platforms, Inc. and affiliates.

# pyre-unsafe

import json

from ixia.ixia import types as ixia_thrift
from taac.testconfigs.configerator.ptp_playbooks.common_playbooks import (
    get_port_flap_playbook,
    get_ptp_agent_warmboot_playbook,
    get_ptp_bgp_restart_playbook,
    get_ptp_continuous_agent_warmboot_playbook,
    get_ptp_continuous_interface_flap_playbook,
    get_ptp_device_reboot_playbook,
    get_ptp_longevity_playbook,
)
from taac.testconfigs.configerator.test_config import (
    thrift_to_json,
)
from taac.health_check.health_check import types as hc_thrift
from taac.test_as_a_config.types import (
    BasicPortConfig,
    BasicTrafficItemConfig,
    DeviceGroupConfig,
    Endpoint,
    Params,
    PointInTimeHealthCheck,
    SnapshotHealthCheck,
    Task,
    TestConfig,
    TrafficEndpoint,
)

DEVICE_HOSTNAME = "ma01-03.qzr1"
IXIA_PORT_1 = "eth1/63/1"
IXIA_PORT_2 = "eth1/64/1"
IXIA_PORTS = [IXIA_PORT_1, IXIA_PORT_2]

test_config = TestConfig(
    name="MA_KO3_PTP",
    basset_pool="dne.test",
    ignore_circuit_fbnet_status=True,
    skip_ixia_protocol_verification=True,
    endpoints=[
        Endpoint(
            name=DEVICE_HOSTNAME,
            dut=True,
            ixia_ports=IXIA_PORTS,
        ),
    ],
    ptp_configs=[
        ixia_thrift.PTPConfig(
            server_endpoint=ixia_thrift.PTPEndpoint(
                name=f"{DEVICE_HOSTNAME}:{IXIA_PORT_1}",
            ),
            client_endpoints=[
                ixia_thrift.PTPEndpoint(
                    name=f"{DEVICE_HOSTNAME}:{IXIA_PORT_2}",
                ),
            ],
        )
    ],
    setup_tasks=[
        Task(
            task_name="coop_unregister_patchers",
            params=Params(
                json_params=json.dumps(
                    {
                        "hostname": DEVICE_HOSTNAME,
                    }
                ),
            ),
        ),
        # Patcher to update default arguments for the agent (MA only). Remove all FBOSS features is committed
        Task(
            task_name="coop_register_patcher",
            params=Params(
                json_params=json.dumps(
                    {
                        "hostname": DEVICE_HOSTNAME,
                        "config_name": "agent",
                        "patcher_name": "agent_override_warm_boot_argument",
                        "py_func_name": "agent_add_update_default_arguments",
                        "patcher_args": json.dumps({"can_warm_boot": "true"}),
                    }
                ),
            ),
        ),
    ],
    basic_port_configs=[
        BasicPortConfig(
            device_group_configs=[
                DeviceGroupConfig(
                    multiplier=50,
                    device_group_index=0,
                )
            ],
            endpoint=f"{DEVICE_HOSTNAME}:{IXIA_PORT_2}",
        ),
        BasicPortConfig(
            device_group_configs=[
                DeviceGroupConfig(
                    multiplier=50,
                    device_group_index=0,
                )
            ],
            endpoint=f"{DEVICE_HOSTNAME}:{IXIA_PORT_1}",
        ),
    ],
    basic_traffic_item_configs=[
        BasicTrafficItemConfig(
            bidirectional=True,
            merge_destinations=True,
            line_rate=10,
            src_dest_mesh=ixia_thrift.SrcDestMeshType.MANY_TO_MANY,
            src_endpoints=[
                TrafficEndpoint(
                    name=f"{DEVICE_HOSTNAME}:{IXIA_PORT_2}",
                    device_group_index=0,
                )
            ],
            dest_endpoints=[
                TrafficEndpoint(
                    name=f"{DEVICE_HOSTNAME}:{IXIA_PORT_1}",
                    device_group_index=0,
                )
            ],
            traffic_type=ixia_thrift.TrafficType.IPV6,
            frame_size_settings=ixia_thrift.FrameSize(
                type=ixia_thrift.FrameSizeType.CUSTOM_IMIX
            ),
        ),
    ],
    postchecks=[
        PointInTimeHealthCheck(
            name=hc_thrift.CheckName.LLDP_CHECK,
        ),
        PointInTimeHealthCheck(
            name=hc_thrift.CheckName.PORT_STATE_CHECK,
        ),
        PointInTimeHealthCheck(
            name=hc_thrift.CheckName.IXIA_PACKET_LOSS_CHECK,
            input_json=thrift_to_json(
                hc_thrift.IxiaPacketLossHealthCheckIn(
                    thresholds=[hc_thrift.PacketLossThreshold(str_value="0.1")]
                )
            ),
        ),
        PointInTimeHealthCheck(
            name=hc_thrift.CheckName.IXIA_PTP_CHECK,
        ),
    ],
    prechecks=[
        PointInTimeHealthCheck(
            name=hc_thrift.CheckName.LLDP_CHECK,
        ),
        PointInTimeHealthCheck(
            name=hc_thrift.CheckName.PORT_STATE_CHECK,
        ),
        PointInTimeHealthCheck(
            name=hc_thrift.CheckName.UNCLEAN_EXIT_CHECK,
            check_params=Params(
                jq_params={
                    "start_time": ".test_case_start_time",
                }
            ),
        ),
        PointInTimeHealthCheck(
            name=hc_thrift.CheckName.IXIA_PACKET_LOSS_CHECK,
            input_json=thrift_to_json(
                hc_thrift.IxiaPacketLossHealthCheckIn(
                    thresholds=[hc_thrift.PacketLossThreshold(str_value="0.1")]
                )
            ),
        ),
        PointInTimeHealthCheck(
            name=hc_thrift.CheckName.IXIA_PTP_CHECK,
        ),
    ],
    snapshot_checks=[
        SnapshotHealthCheck(name=hc_thrift.CheckName.CORE_DUMPS_CHECK),
    ],
    playbooks=[
        get_ptp_longevity_playbook(),
        get_ptp_agent_warmboot_playbook(DEVICE_HOSTNAME),
        get_ptp_bgp_restart_playbook(DEVICE_HOSTNAME),
        get_port_flap_playbook(
            device_hostname=DEVICE_HOSTNAME,
            interface_to_flap=IXIA_PORTS,
            iteration=5,
        ),
        get_ptp_device_reboot_playbook(DEVICE_HOSTNAME),
        get_ptp_continuous_agent_warmboot_playbook(DEVICE_HOSTNAME),
    ],
)

TEST_CONFIG = test_config
