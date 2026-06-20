# Copyright (c) Meta Platforms, Inc. and affiliates.

# pyre-unsafe

from ixia.ixia import types as ixia_thrift
from taac.testconfigs.configerator.ptp_playbooks.common_playbooks import (
    get_ptp_agent_warmboot_playbook as get_ptp_remote_device_agent_warmboot_playbook,
    get_ptp_bgp_restart_playbook as get_ptp_remote_device_bgp_restart_playbook,
    get_ptp_continuous_interface_flap_playbook,
    get_ptp_device_drain_playbook,
    get_ptp_device_reboot_playbook,
    get_ptp_interface_drain_playbook,
    get_ptp_interface_flap_playbook,
    get_ptp_l3_forwarding_agent_restart_playbook,
    get_ptp_xcvr_restart_playbook,
    get_ptp_xcvr_ungraceful_restart_playbook,
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
    PointInTimeHealthCheck,
    TestConfig,
    TrafficEndpoint,
)

RSW_HOSTNAME = "rsw001.p001.m001.snc1"
JSW_HOSTNAME = "jsw002.m001.snc1"

test_config = TestConfig(
    name="JSW_PTP",
    basset_pool="dne.test",
    ignore_circuit_fbnet_status=True,
    endpoints=[
        Endpoint(name=RSW_HOSTNAME, dut=True, ixia_ports=["eth1/17/1"]),
        Endpoint(
            name=JSW_HOSTNAME,
            dut=True,
        ),
        Endpoint(
            name="xsw002.x007.snc1",
        ),
        Endpoint(name="ma01-02.labdcb1", ixia_ports=["eth7/3/1"]),
    ],
    ptp_configs=[
        ixia_thrift.PTPConfig(
            server_endpoint=ixia_thrift.PTPEndpoint(
                name="ma01-02.labdcb1:eth7/3/1",
            ),
            client_endpoints=[
                ixia_thrift.PTPEndpoint(
                    name=f"{RSW_HOSTNAME}:eth1/17/1",
                ),
            ],
        )
    ],
    basic_port_configs=[
        BasicPortConfig(
            device_group_configs=[
                DeviceGroupConfig(
                    multiplier=50,
                    device_group_index=0,
                )
            ],
            endpoint=f"{RSW_HOSTNAME}:eth1/17/1",
        ),
        BasicPortConfig(
            device_group_configs=[
                DeviceGroupConfig(
                    multiplier=50,
                    device_group_index=0,
                )
            ],
            endpoint="ma01-02.labdcb1:eth7/3/1",
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
                    name=f"{RSW_HOSTNAME}:eth1/17/1",
                    device_group_index=0,
                )
            ],
            dest_endpoints=[
                TrafficEndpoint(
                    name="ma01-02.labdcb1:eth7/3/1",
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
    playbooks=[
        get_ptp_remote_device_agent_warmboot_playbook(RSW_HOSTNAME),
        get_ptp_remote_device_bgp_restart_playbook(RSW_HOSTNAME),
        get_ptp_xcvr_restart_playbook(JSW_HOSTNAME),
        get_ptp_xcvr_ungraceful_restart_playbook(JSW_HOSTNAME),
        get_ptp_l3_forwarding_agent_restart_playbook(JSW_HOSTNAME),
        get_ptp_interface_flap_playbook([JSW_HOSTNAME, RSW_HOSTNAME]),
        get_ptp_continuous_interface_flap_playbook([JSW_HOSTNAME, RSW_HOSTNAME]),
        get_ptp_interface_drain_playbook(RSW_HOSTNAME),
        get_ptp_device_drain_playbook(JSW_HOSTNAME),
        get_ptp_device_reboot_playbook(JSW_HOSTNAME),
    ],
)

TEST_CONFIG = test_config
