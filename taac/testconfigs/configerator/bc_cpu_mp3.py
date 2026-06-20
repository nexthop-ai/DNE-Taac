# Copyright (c) Meta Platforms, Inc. and affiliates.

# pyre-unsafe

from ixia.ixia import types as ixia_thrift
from taac.testconfigs.configerator.cpu_queue import (
    create_cpu_queue_test_config,
)
from taac.test_as_a_config import types as taac_thrift


hostname = "bc001.v001.p001.s001.qzr1"
ingress_ixia_port = "eth1/62/1"
egress_ixia_port = "eth1/63/1"
mac_address = "b6:db:91:95:ff:59"

basic_port_configs = [
    taac_thrift.BasicPortConfig(
        device_group_configs=[
            taac_thrift.DeviceGroupConfig(
                multiplier=10,
                device_group_index=0,
                v6_bgp_config=taac_thrift.BgpConfig(
                    bgp_peer_type=ixia_thrift.BgpPeerType.IBGP,
                    local_as_4_bytes=4210205999,
                    route_scales=[
                        taac_thrift.RouteScaleSpec(
                            network_group_index=0,
                            v6_route_scale=taac_thrift.RouteScale(
                                multiplier=10,
                                prefix_count=1500,
                                prefix_length=64,
                                starting_prefixes="4000::",
                                bgp_communities=["65529:51710"],
                                prefix_step="0:0:0:0:1::",
                                ip_address_family=ixia_thrift.IpAddressFamily.IPV6,
                            ),
                        ),
                    ],
                ),
            )
        ],
        endpoint=f"{hostname}:{egress_ixia_port}",
    ),
    taac_thrift.BasicPortConfig(
        device_group_configs=[
            taac_thrift.DeviceGroupConfig(
                device_group_index=0,
                multiplier=10,
                v6_bgp_config=taac_thrift.BgpConfig(
                    bgp_peer_type=ixia_thrift.BgpPeerType.IBGP,
                    local_as_4_bytes=4210205999,
                    route_scales=[
                        taac_thrift.RouteScaleSpec(
                            network_group_index=0,
                            v6_route_scale=taac_thrift.RouteScale(
                                multiplier=10,
                                prefix_count=1500,
                                prefix_length=64,
                                starting_prefixes="5000::",
                                bgp_communities=["65529:51710"],
                                prefix_step="0:0:0:0:1::",
                                ip_address_family=ixia_thrift.IpAddressFamily.IPV6,
                            ),
                        ),
                    ],
                ),
            )
        ],
        endpoint=f"{hostname}:{ingress_ixia_port}",
    ),
]


test_config = create_cpu_queue_test_config(
    "BC_CPU_MP3",
    hostname,
    ingress_ixia_port,
    egress_ixia_port,
    mac_address,
    basic_port_configs,
)

TEST_CONFIG = test_config
