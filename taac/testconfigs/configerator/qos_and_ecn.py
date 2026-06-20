# Copyright (c) Meta Platforms, Inc. and affiliates.

# pyre-unsafe

import itertools
from typing import List

from ixia.ixia import types as ixia_thrift
from neteng.qosdb.Cos import types as cos
from taac.testconfigs.configerator.test_config import (
    thrift_to_json,
)
from taac.health_check.health_check import types as hc_thrift
from taac.test_as_a_config import types as taac_thrift


QUEUE_DSCP_VALUE_MAP = {
    cos.ClassOfService.BRONZE: 10,
    cos.ClassOfService.SILVER: 0,
    cos.ClassOfService.GOLD: 18,
    cos.ClassOfService.ICP: 35,
    cos.ClassOfService.NC: 48,
}

COS_QUEUE_TO_STR = {
    cos.ClassOfService.BRONZE: "BRONZE",
    cos.ClassOfService.SILVER: "SILVER",
    cos.ClassOfService.GOLD: "GOLD",
    cos.ClassOfService.ICP: "ICP",
    cos.ClassOfService.NC: "NC",
}

FRAME_SIZE_SETTING_MAPPING = {
    "64": ixia_thrift.FrameSize(
        type=ixia_thrift.FrameSizeType.FIXED,
        fixed_size=64,
    ),
    "9000": ixia_thrift.FrameSize(
        type=ixia_thrift.FrameSizeType.FIXED,
        fixed_size=9000,
    ),
    "64_TO_9000": ixia_thrift.FrameSize(
        type=ixia_thrift.FrameSizeType.RANDOM,
        random_min=64,
        random_max=9000,
    ),
}


def create_qos_ipv6_traffic_item(
    src_endpoint: str,
    dst_endpoint: str,
    cos: cos.ClassOfService,
    ecn_capability: ixia_thrift.EcnCapability = ixia_thrift.EcnCapability.MIXED,
    line_rate: int = 10,
) -> List[taac_thrift.BasicTrafficItemConfig]:
    return [
        taac_thrift.BasicTrafficItemConfig(
            name=f"IPV6_{COS_QUEUE_TO_STR[cos]}_TRAFFIC_PACKET_SIZE_{frame_size_str}",
            bidirectional=False,
            merge_destinations=True,
            line_rate=line_rate,
            src_dest_mesh=ixia_thrift.SrcDestMeshType.MANY_TO_MANY,
            src_endpoints=[
                taac_thrift.TrafficEndpoint(
                    name=src_endpoint,
                    device_group_index=0,
                ),
            ],
            dest_endpoints=[
                taac_thrift.TrafficEndpoint(
                    name=dst_endpoint,
                    device_group_index=0,
                ),
            ],
            traffic_type=ixia_thrift.TrafficType.IPV6,
            frame_size_settings=frame_size_setting,
            qos_config=ixia_thrift.QoSConfig(
                dscp_value=QUEUE_DSCP_VALUE_MAP[cos],
                ecn_capability=ecn_capability,
            ),
        )
        for frame_size_str, frame_size_setting in FRAME_SIZE_SETTING_MAPPING.items()
    ]


def create_qos_playbook(
    hostname: str,
    egress_ixia_port: str,
    cos: cos.ClassOfService,
    frame_size_str: str,
) -> taac_thrift.Playbook:
    return taac_thrift.Playbook(
        traffic_items_to_start=[
            f"IPV6_{COS_QUEUE_TO_STR[cos]}_TRAFFIC_PACKET_SIZE_{frame_size_str}",
        ],
        snapshot_checks=[
            taac_thrift.SnapshotHealthCheck(
                name=hc_thrift.CheckName.QOS_DSCP_TX_QUEUE_CHECK,
                input_json=thrift_to_json(
                    hc_thrift.QoSDscpTxQueueHealthCheckIn(
                        tx_queue_info_list=[
                            hc_thrift.TxQueueInfo(
                                hostname=hostname,
                                interface=egress_ixia_port,
                                cos_list=[cos],
                                val=1000,
                            )
                        ]
                    )
                ),
            )
        ],
        name=f"test_ipv6_{COS_QUEUE_TO_STR[cos].lower()}_packet_size_{frame_size_str.lower()}_traffic",
        stages=[
            taac_thrift.Stage(
                steps=[
                    taac_thrift.Step(
                        name=taac_thrift.StepName.LONGEVITY_STEP,
                        step_params=taac_thrift.Params(json_params='{"duration": 60}'),
                    )
                ],
            ),
        ],
    )


def create_qos_test_config(
    test_config_name: str,
    hostname: str,
    ingress_ixia_port: str,
    egress_ixia_port: str,
    basic_port_configs: List[taac_thrift.BasicPortConfig],
    basset_pool: str = "dne.test",
) -> taac_thrift.TestConfig:
    return taac_thrift.TestConfig(
        name=test_config_name,
        basset_pool=basset_pool,
        ignore_circuit_fbnet_status=True,
        endpoints=[
            taac_thrift.Endpoint(
                name=hostname,
                dut=True,
                ixia_ports=[ingress_ixia_port, egress_ixia_port],
            ),
        ],
        postchecks=[
            taac_thrift.PointInTimeHealthCheck(
                name=hc_thrift.CheckName.IXIA_PACKET_LOSS_CHECK,
                input_json=thrift_to_json(
                    hc_thrift.IxiaPacketLossHealthCheckIn(
                        thresholds=[hc_thrift.PacketLossThreshold(str_value="0.1")]
                    )
                ),
            ),
            taac_thrift.PointInTimeHealthCheck(
                name=hc_thrift.CheckName.UNCLEAN_EXIT_CHECK,
                check_params=taac_thrift.Params(
                    jq_params={
                        "start_time": ".test_case_start_time",
                    }
                ),
            ),
        ],
        prechecks=[
            taac_thrift.PointInTimeHealthCheck(
                name=hc_thrift.CheckName.IXIA_PACKET_LOSS_CHECK,
                input_json=thrift_to_json(
                    hc_thrift.IxiaPacketLossHealthCheckIn(
                        thresholds=[hc_thrift.PacketLossThreshold(str_value="0.1")]
                    )
                ),
            ),
        ],
        snapshot_checks=[
            taac_thrift.SnapshotHealthCheck(name=hc_thrift.CheckName.CORE_DUMPS_CHECK)
        ],
        basic_traffic_item_configs=[
            item
            for cos in COS_QUEUE_TO_STR.keys()
            for item in create_qos_ipv6_traffic_item(
                src_endpoint=f"{hostname}:{ingress_ixia_port}",
                dst_endpoint=f"{hostname}:{egress_ixia_port}",
                cos=cos,
            )
        ],
        basic_port_configs=basic_port_configs,
        playbooks=[
            *[
                create_qos_playbook(
                    hostname=hostname,
                    egress_ixia_port=egress_ixia_port,
                    cos=cos,
                    frame_size_str=frame_size_str,
                )
                for cos in COS_QUEUE_TO_STR.keys()
                for frame_size_str in FRAME_SIZE_SETTING_MAPPING.keys()
            ]
        ],
    )
