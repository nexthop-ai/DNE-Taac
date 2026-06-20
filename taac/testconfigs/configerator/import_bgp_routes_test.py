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
    name="IMPORT_BGP_ROUTES_TEST",
    basset_pool="dne.test",
    ignore_circuit_fbnet_status=True,
    endpoints=[
        taac_thrift.Endpoint(
            name="fa001-uu002.qzd1", dut=True, ixia_ports=["eth6/13/1"]
        ),
    ],
    postchecks=[
        taac_thrift.PointInTimeHealthCheck(
            name=hc_thrift.CheckName.IXIA_PACKET_LOSS_CHECK,
        ),
    ],
    prechecks=[
        taac_thrift.PointInTimeHealthCheck(
            name=hc_thrift.CheckName.IXIA_PACKET_LOSS_CHECK,
        ),
    ],
    basic_port_configs=[
        taac_thrift.BasicPortConfig(
            device_group_configs=[
                taac_thrift.DeviceGroupConfig(
                    multiplier=10,
                    device_group_index=0,
                    v6_bgp_config=taac_thrift.BgpConfig(
                        import_bgp_routes_params_list=[
                            ixia_thrift.ImportBgpRoutesParams(
                                multiplier=10,
                                bgp_route_import_file_path="ipv6_routes_plane_1.csv",
                                import_file_type=ixia_thrift.BgpRouteImportFileType.CSV,
                                network_group_index=0,
                                bgp_attribute_configs=[
                                    ixia_thrift.BgpAttributeConfig(
                                        attribute=ixia_thrift.BgpAttribute.COMMUNITIES,
                                        value_lists=[
                                            ["11111:11111", "22222:22222"],
                                            ["33333:33333", "44444:44444"],
                                        ],
                                        distribution_type=ixia_thrift.DistribitionType.ROUND_ROBIN,
                                    )
                                ],
                            )
                        ]
                    ),
                )
            ],
            endpoint="fa001-uu002.qzd1:eth6/13/1",
        ),
    ],
    playbooks=[
        taac_thrift.Playbook(
            name="test_longevity",
            description="Test packet loss in 1 minute longevity",
            stages=[
                taac_thrift.Stage(
                    steps=[
                        taac_thrift.Step(
                            name=taac_thrift.StepName.LONGEVITY_STEP,
                            step_params=taac_thrift.Params(
                                json_params='{"duration": 60}'
                            ),
                        )
                    ]
                )
            ],
        ),
    ],
)

TEST_CONFIG = test_config
