# Copyright (c) Meta Platforms, Inc. and affiliates.
# pyre-unsafe
"""
BGP++ Conveyor Test Configuration for bag012.ash6.

This test config is designed for the EBB BGP++ CI/CD conveyor pipeline.
It runs the following playbooks:
- bgp_update_packing_validation_playbook
- constant_attribute_storage_varying_combinations_test

Test direction matches EB02_ARISTA_BGP_UPDATE_PACKING_VALIDATION:
- EBGP → IBGP: 10 EBGP peers inject routes, 1 IBGP peer captures UPDATEs
- 2 IXIA ports only (no BGP MON)

Constant Attribute Storage Varying Combinations Test:
- Validates that memory for storing pool of attributes is constant
- 8 EBGP peers + 2 IBGP peers (smaller scale, no openR)
- Uses custom setup tasks

Device: bag012.ash6
IXIA Chassis: ares1-my24520014
IXIA Ports:
- Et3/36/1 -> 7/7 (eBGP)
- Et3/36/2 -> 7/8 (iBGP)
"""

import typing as t

from ixia.ixia import types as ixia_types
from taac.constants import BgpPlusPlusProfile
from taac.playbooks.playbook_definitions import (
    create_new_peer_join_attribute_change_playbook,
    create_new_peer_join_full_sync_resilience_playbook,
    create_new_peer_join_routes_withdrawn_playbook,
)
from taac.routing.ebb.ebb_bgp_plus_plus_test_config.ebb_bgp_plus_plus_conveyor.conveyor_common_tasks import (
    build_per_iteration_factory_v4_capable,
    get_update_packing_setup_tasks,
)
from taac.routing.ebb.ebb_bgp_plus_plus_test_config.ebb_bgp_plus_plus_conveyor.conveyor_constants import (
    EBGP_PEER_COUNT_V6,
    EBGP_REMOTE_AS,
    IBGP_PEER_SCALE_PER_PLANE,
    IBGP_REMOTE_AS,
    IXIA_EBGP_IC_PARENT_NETWORK_V4,
    IXIA_EBGP_IC_PARENT_NETWORK_V6,
    IXIA_IBGP_IC_PARENT_NETWORK_V4_DC_PLANE1,
    IXIA_IBGP_IC_PARENT_NETWORK_V6_DC_PLANE1,
    IXIA_IPV4_START_OFFSET,
    PEERGROUP_EBGP_V4,
    PEERGROUP_EBGP_V6,
    PEERGROUP_IBGP_V4,
    PEERGROUP_IBGP_V6,
)
from taac.steps.step_definitions import (
    create_ixia_api_step,
    create_longevity_step,
    create_start_stop_bgp_peers_step,
)
from taac.testconfigs.routing.ebb.test_config_performance_scaling_case1 import (
    test_config_for_bgp_plus_plus_on_ebb_arista_performance_scaling,
)
from taac.testconfigs.routing.ebb.test_config_performance_scaling_case2 import (
    test_config_constant_attribute_storage_varying_combinations_on_eos,
)
from taac.testconfigs.routing.ebb.test_config_performance_scaling_case9 import (
    test_config_for_bgp_plus_plus_on_ebb_arista_bounded_ecmp_sets,
)
from taac.testconfigs.routing.ebb.test_config_queue_memory_monitor import (
    test_config_bgp_queue_memory_monitoring_with_route_scale,
)
from taac.testconfigs.routing.ebb.test_config_update_packing import (
    test_config_bgp_update_packing_validation,
)
from taac.test_as_a_config import types as taac_types
from taac.test_as_a_config.types import DirectIxiaConnection


# =============================================================================
# Device-specific configuration for bag012.ash6
# =============================================================================
DEVICE_NAME = "bag012.ash6"
IXIA_CHASSIS_IP = "2401:db00:2066:303b::3001"
BAG012_EOS_BGP_AS = 65012
BGPCPP_CONFIGERATOR_PATH = "taac/ebb_ci_cd_configs/ebb_full_scale_bgpcpp_config"
BAG012_ROUTER_ID = "10.163.28.11"

# IXIA interface mappings for bag012.ash6 (no BGP MON needed)
IXIA_INTERFACE_MIMIC_EBGP = "Ethernet3/36/1"
IXIA_INTERFACE_MIMIC_IBGP = "Ethernet3/36/2"

# IXIA port mappings (chassis slot/port)
IXIA_PORT_EBGP = "7/7"
IXIA_PORT_IBGP = "7/8"


def create_bag012_ash6_conveyor_test_config(
    enable_update_group: bool = False,
) -> taac_types.TestConfig:
    """
    Create the test configuration for bag012.ash6 conveyor testing.

    Reuses test_config_bgp_update_packing_validation() with bag012-specific
    setup_tasks and direct_ixia_connections.

    Test direction matches EB02_ARISTA_BGP_UPDATE_PACKING_VALIDATION:
    - EBGP → IBGP: 10 EBGP peers inject routes, 1 IBGP peer captures UPDATEs
    - ebgp_route_acceptance_communities=["65529:39744"]

    Args:
        enable_update_group: When True, dynamically toggles BGP++
            ``enable_update_group`` (and the ``update_group_config`` struct
            per D100093369) by patching ``/mnt/flash/bgpcpp_config`` in-shell
            during BGP++ deployment. The test config name is suffixed with
            ``_UPDATE_GROUP``.

    Returns:
        TestConfig object configured for bag012.ash6
    """
    name = "BAG012_ASH6_BGP_CONVEYOR_TEST"
    if enable_update_group:
        name += "_UPDATE_GROUP"
    setup_tasks = get_update_packing_setup_tasks(
        device_name=DEVICE_NAME,
        bgp_asn=BAG012_EOS_BGP_AS,
        ixia_interface_mimic_ebgp=IXIA_INTERFACE_MIMIC_EBGP,
        ixia_interface_mimic_ibgp=IXIA_INTERFACE_MIMIC_IBGP,
        ebgp_peer_count=10,
        ibgp_peer_count=1,
        ebgp_remote_as=EBGP_REMOTE_AS,
        ibgp_remote_as=IBGP_REMOTE_AS,
        ixia_ebgp_ic_parent_network_v6=IXIA_EBGP_IC_PARENT_NETWORK_V6,
        ixia_ibgp_ic_parent_network_v6=IXIA_IBGP_IC_PARENT_NETWORK_V6_DC_PLANE1,
        router_id=BAG012_ROUTER_ID,
        bgpcpp_configerator_path=BGPCPP_CONFIGERATOR_PATH,
        profile=BgpPlusPlusProfile.BGP_PLUS_PLUS_WITHOUT_OPEN_R,
        enable_update_group=enable_update_group,
    )

    return test_config_bgp_update_packing_validation(
        test_config_name=name,
        device_name=DEVICE_NAME,
        # EBGP configuration (ingress - routes sent here from Fabric Aggregators)
        ixia_interface_mimic_ebgp=IXIA_INTERFACE_MIMIC_EBGP,
        ebgp_remote_as=EBGP_REMOTE_AS,
        ixia_ebgp_ic_parent_network_v6=IXIA_EBGP_IC_PARENT_NETWORK_V6,
        ixia_ebgp_ic_parent_network_v4="",
        # IBGP configuration (egress - capture UPDATEs here)
        ixia_interface_mimic_ibgp=IXIA_INTERFACE_MIMIC_IBGP,
        ibgp_local_as=IBGP_REMOTE_AS,
        ixia_ibgp_ic_parent_network_v6=IXIA_IBGP_IC_PARENT_NETWORK_V6_DC_PLANE1,
        ixia_ibgp_ic_parent_network_v4="",
        # Test parameters (matching EB02)
        ebgp_peer_count=10,
        prefixes_per_peer=10000,
        ibgp_peer_count=1,
        test_address_families=["ipv6"],
        as_path_pool_size=10,
        community_pool_size=20,
        as_path_length=3,
        communities_per_route=2,
        ebgp_route_acceptance_communities=["65529:39744"],
        capture_duration_seconds=300,
        min_packed_size=4000,
        restart_bgp_for_complete_view=True,
        # Conveyor-specific configuration
        setup_tasks=setup_tasks,
        host_os_type_map={DEVICE_NAME: taac_types.DeviceOsType.ARISTA_FBOSS},
        direct_ixia_connections=[
            DirectIxiaConnection(
                interface=IXIA_INTERFACE_MIMIC_EBGP,
                ixia_chassis_ip=IXIA_CHASSIS_IP,
                ixia_port=IXIA_PORT_EBGP,
            ),
            DirectIxiaConnection(
                interface=IXIA_INTERFACE_MIMIC_IBGP,
                ixia_chassis_ip=IXIA_CHASSIS_IP,
                ixia_port=IXIA_PORT_IBGP,
            ),
        ],
        log_collection_timeout=600,
    )


def create_bag012_ash6_constant_attribute_storage_test_config(
    enable_update_group: bool = False,
) -> taac_types.TestConfig:
    """
    Create the constant attribute storage varying combinations test config
    for bag012.ash6.

    Validates that the amount of memory for storing pool of attributes
    remains constant regardless of the number of unique attribute-set
    combinations.

    Uses custom setup tasks (no openR) with smaller scale:
    - 8 EBGP peers + 2 IBGP peers

    Args:
        enable_update_group: When True, dynamically toggles BGP++
            ``enable_update_group`` on the device. Suffixes test name with
            ``_UPDATE_GROUP``.

    Returns:
        TestConfig object configured for bag012.ash6
    """
    name = "BAG012_ASH6_BGP_CONSTANT_ATTRIBUTE_STORAGE_CONVEYOR_TEST"
    if enable_update_group:
        name += "_UPDATE_GROUP"
    setup_tasks = get_update_packing_setup_tasks(
        device_name=DEVICE_NAME,
        bgp_asn=BAG012_EOS_BGP_AS,
        ixia_interface_mimic_ebgp=IXIA_INTERFACE_MIMIC_EBGP,
        ixia_interface_mimic_ibgp=IXIA_INTERFACE_MIMIC_IBGP,
        ebgp_peer_count=8,
        ibgp_peer_count=2,
        ebgp_remote_as=EBGP_REMOTE_AS,
        ibgp_remote_as=IBGP_REMOTE_AS,
        ixia_ebgp_ic_parent_network_v6=IXIA_EBGP_IC_PARENT_NETWORK_V6,
        ixia_ibgp_ic_parent_network_v6=IXIA_IBGP_IC_PARENT_NETWORK_V6_DC_PLANE1,
        router_id=BAG012_ROUTER_ID,
        bgpcpp_configerator_path=BGPCPP_CONFIGERATOR_PATH,
        profile=BgpPlusPlusProfile.BGP_PLUS_PLUS_WITHOUT_OPEN_R,
        enable_update_group=enable_update_group,
    )

    return test_config_constant_attribute_storage_varying_combinations_on_eos(
        test_config_name=name,
        device_name=DEVICE_NAME,
        # EBGP configuration
        ixia_interface_mimic_ebgp=IXIA_INTERFACE_MIMIC_EBGP,
        ebgp_remote_as=EBGP_REMOTE_AS,
        ixia_ebgp_ic_parent_network_v6=IXIA_EBGP_IC_PARENT_NETWORK_V6,
        ixia_ebgp_ic_parent_network_v4=IXIA_EBGP_IC_PARENT_NETWORK_V4,
        # IBGP configuration
        ixia_interface_mimic_ibgp=IXIA_INTERFACE_MIMIC_IBGP,
        ibgp_local_as=IBGP_REMOTE_AS,
        ixia_ibgp_ic_parent_network_v6=IXIA_IBGP_IC_PARENT_NETWORK_V6_DC_PLANE1,
        ixia_ibgp_ic_parent_network_v4=IXIA_IBGP_IC_PARENT_NETWORK_V4_DC_PLANE1,
        # Fixed: 8 EBGP peers + 2 IBGP peers (smaller scale)
        constant_ebgp_peer_count=8,
        constant_ibgp_peer_count=2,
        # Fixed: 800K total paths
        constant_total_paths=800_000,
        # Variable: unique combination counts
        unique_combination_counts=[
            100_000,
            200_000,
            400_000,
            600_000,
            800_000,
        ],
        soak_time_minutes=2,
        dump_attribute_assignments=True,
        test_address_families=["ipv6"],
        # Custom setup tasks (no openR)
        setup_tasks=setup_tasks,
        host_os_type_map={DEVICE_NAME: taac_types.DeviceOsType.ARISTA_FBOSS},
        direct_ixia_connections=[
            DirectIxiaConnection(
                interface=IXIA_INTERFACE_MIMIC_EBGP,
                ixia_chassis_ip=IXIA_CHASSIS_IP,
                ixia_port=IXIA_PORT_EBGP,
            ),
            DirectIxiaConnection(
                interface=IXIA_INTERFACE_MIMIC_IBGP,
                ixia_chassis_ip=IXIA_CHASSIS_IP,
                ixia_port=IXIA_PORT_IBGP,
            ),
        ],
        # Constant acceptance community (required by device BGP policy)
        constant_acceptance_communities=["65529:39744"],
        max_communities_per_route_from_pool=5,
        random_seed=42,
        # Device-level BGP peer group names
        peergroup_ebgp_v6=PEERGROUP_EBGP_V6,
        peergroup_ebgp_v4=PEERGROUP_EBGP_V4,
        peergroup_ibgp_v6=PEERGROUP_IBGP_V6,
        peergroup_ibgp_v4=PEERGROUP_IBGP_V4,
        log_collection_timeout=600,
    )


def create_bag012_ash6_queue_memory_monitor_test_config(
    enable_update_group: bool = False,
) -> taac_types.TestConfig:
    """
    Create the queue memory monitor test config for bag012.ash6.

    Monitors BGP++ fiber queue statistics and memory usage under route churn.
    - 140 EBGP peers with route flapping (15s up / 15s down)
    - 63 IBGP peers (full EBB scale)
    - Monitor for 60 minutes at 2-minute intervals

    Args:
        enable_update_group: When True, dynamically toggles BGP++
            ``enable_update_group`` on the device. Suffixes test name with
            ``_UPDATE_GROUP``.

    Returns:
        TestConfig object configured for bag012.ash6
    """
    name = "BAG012_ASH6_BGP_QUEUE_MEMORY_MONITOR_CONVEYOR_TEST"
    if enable_update_group:
        name += "_UPDATE_GROUP"
    setup_tasks = get_update_packing_setup_tasks(
        device_name=DEVICE_NAME,
        bgp_asn=BAG012_EOS_BGP_AS,
        ixia_interface_mimic_ebgp=IXIA_INTERFACE_MIMIC_EBGP,
        ixia_interface_mimic_ibgp=IXIA_INTERFACE_MIMIC_IBGP,
        ebgp_peer_count=EBGP_PEER_COUNT_V6,
        ibgp_peer_count=IBGP_PEER_SCALE_PER_PLANE,
        ebgp_remote_as=EBGP_REMOTE_AS,
        ibgp_remote_as=IBGP_REMOTE_AS,
        ixia_ebgp_ic_parent_network_v6=IXIA_EBGP_IC_PARENT_NETWORK_V6,
        ixia_ibgp_ic_parent_network_v6=IXIA_IBGP_IC_PARENT_NETWORK_V6_DC_PLANE1,
        router_id=BAG012_ROUTER_ID,
        bgpcpp_configerator_path=BGPCPP_CONFIGERATOR_PATH,
        profile=BgpPlusPlusProfile.BGP_PLUS_PLUS_WITHOUT_OPEN_R,
        enable_update_group=enable_update_group,
    )

    # CPU stress is deployed directly by the custom step (_deploy_cpu_stress)
    # when monitor_cpu_stress=True — no need for setup_tasks deployment.

    return test_config_bgp_queue_memory_monitoring_with_route_scale(
        test_config_name=name,
        device_name=DEVICE_NAME,
        # IBGP configuration
        ixia_interface_mimic_ibgp=IXIA_INTERFACE_MIMIC_IBGP,
        ibgp_local_as=IBGP_REMOTE_AS,
        ixia_ibgp_ic_parent_network_v6=IXIA_IBGP_IC_PARENT_NETWORK_V6_DC_PLANE1,
        ixia_ibgp_ic_parent_network_v4=IXIA_IBGP_IC_PARENT_NETWORK_V4_DC_PLANE1,
        # EBGP configuration
        ixia_interface_mimic_ebgp=IXIA_INTERFACE_MIMIC_EBGP,
        ebgp_remote_as=EBGP_REMOTE_AS,
        ixia_ebgp_ic_parent_network_v6=IXIA_EBGP_IC_PARENT_NETWORK_V6,
        ixia_ebgp_ic_parent_network_v4=IXIA_EBGP_IC_PARENT_NETWORK_V4,
        # Test parameters
        ibgp_peer_count=IBGP_PEER_SCALE_PER_PLANE,
        ebgp_peer_count=EBGP_PEER_COUNT_V6,
        prefixes_per_ebgp_peer=10000,
        ip_version="ipv6",
        # Route acceptance communities
        ebgp_route_acceptance_communities=["65529:39744"],
        # Monitoring parameters
        monitoring_duration_minutes=60,
        monitoring_interval_seconds=120,
        # Route flapping parameters
        flap_uptime_seconds=15,
        flap_downtime_seconds=15,
        # Conveyor-specific configuration
        setup_tasks=setup_tasks,
        monitor_cpu_stress=True,
        host_os_type_map={DEVICE_NAME: taac_types.DeviceOsType.ARISTA_FBOSS},
        direct_ixia_connections=[
            DirectIxiaConnection(
                interface=IXIA_INTERFACE_MIMIC_EBGP,
                ixia_chassis_ip=IXIA_CHASSIS_IP,
                ixia_port=IXIA_PORT_EBGP,
            ),
            DirectIxiaConnection(
                interface=IXIA_INTERFACE_MIMIC_IBGP,
                ixia_chassis_ip=IXIA_CHASSIS_IP,
                ixia_port=IXIA_PORT_IBGP,
            ),
        ],
        log_collection_timeout=600,
    )


# Export the test configs
BAG012_ASH6_CONVEYOR_TEST_CONFIG = create_bag012_ash6_conveyor_test_config()
BAG012_ASH6_CONSTANT_ATTRIBUTE_STORAGE_TEST_CONFIG = (
    create_bag012_ash6_constant_attribute_storage_test_config()
)
BAG012_ASH6_QUEUE_MEMORY_MONITOR_TEST_CONFIG = (
    create_bag012_ash6_queue_memory_monitor_test_config()
)


# =============================================================================
# BGP++ Performance Scaling — egress IBGP peer sweep on bag012.ash6 conveyor.
# =============================================================================
# Defaults match the simplified rewrite of D104072489: per stage n peers per
# AF, total = 2n + 2 EBGP. Each Stage rewrites /mnt/flash/bgpcpp_config to
# have exactly the matching number of peer entries (so BGP++ EOR completes
# from 100% of configured peers and convergence isn't clamped at the 2-min
# EOR-expiry timer).
BAG012_ASH6_PERFORMANCE_SCALING_EGRESS_PEER_COUNTS: list = [100, 200, 300, 400, 500]
BAG012_ASH6_PERFORMANCE_SCALING_PREFIX_COUNT: int = 50000


def create_bag012_ash6_performance_scaling_test_config(
    enable_update_group: bool = False,
) -> taac_types.TestConfig:
    """Egress IBGP peer-sweep TestConfig for bag012.ash6 conveyor (v6 + v4).

    Per Stage n in egress_peer_counts, the device is configured with n v6 +
    n v4 IBGP peers via in-shell bgpcpp_config rewrite, then 50K v6 + 50K v4
    EBGP prefixes are advertised and initial convergence is measured. A
    final aggregator Stage produces one consolidated everpaste plot.

    Args:
        enable_update_group: When True, dynamically toggles BGP++
            ``enable_update_group`` on the device. Suffixes test name with
            ``_UPDATE_GROUP``. The per-iteration factory only rewrites
            ``peers`` + ``router_id``; ``bgp_setting_config`` (where
            ``enable_update_group`` lives) is preserved across iterations.
    """
    name = "BAG012_ASH6_BGP_PERFORMANCE_SCALING_CONVEYOR_TEST"
    if enable_update_group:
        name += "_UPDATE_GROUP"
    setup_tasks = get_update_packing_setup_tasks(
        device_name=DEVICE_NAME,
        bgp_asn=BAG012_EOS_BGP_AS,
        ixia_interface_mimic_ebgp=IXIA_INTERFACE_MIMIC_EBGP,
        ixia_interface_mimic_ibgp=IXIA_INTERFACE_MIMIC_IBGP,
        ebgp_peer_count=1,
        ibgp_peer_count=BAG012_ASH6_PERFORMANCE_SCALING_EGRESS_PEER_COUNTS[0],
        ebgp_remote_as=EBGP_REMOTE_AS,
        ibgp_remote_as=IBGP_REMOTE_AS,
        ixia_ebgp_ic_parent_network_v6=IXIA_EBGP_IC_PARENT_NETWORK_V6,
        ixia_ibgp_ic_parent_network_v6=IXIA_IBGP_IC_PARENT_NETWORK_V6_DC_PLANE1,
        # v4 enables dual-stack IBGP/EBGP at startup so the initial
        # /mnt/flash/bgpcpp_config matches the v6+v4 layout that each
        # per-iteration factory call produces.
        ixia_ebgp_ic_parent_network_v4=IXIA_EBGP_IC_PARENT_NETWORK_V4,
        ixia_ibgp_ic_parent_network_v4=IXIA_IBGP_IC_PARENT_NETWORK_V4_DC_PLANE1,
        router_id=BAG012_ROUTER_ID,
        bgpcpp_configerator_path=BGPCPP_CONFIGERATOR_PATH,
        profile=BgpPlusPlusProfile.BGP_PLUS_PLUS_WITHOUT_OPEN_R,
        enable_update_group=enable_update_group,
    )
    factory = build_per_iteration_factory_v4_capable(
        device_name=DEVICE_NAME,
        router_id=BAG012_ROUTER_ID,
        ebgp_remote_as=EBGP_REMOTE_AS,
        ibgp_remote_as=IBGP_REMOTE_AS,
        ebgp_v6_base=IXIA_EBGP_IC_PARENT_NETWORK_V6,
        ebgp_v4_base=IXIA_EBGP_IC_PARENT_NETWORK_V4,
        ibgp_v6_base=IXIA_IBGP_IC_PARENT_NETWORK_V6_DC_PLANE1,
        ibgp_v4_base=IXIA_IBGP_IC_PARENT_NETWORK_V4_DC_PLANE1,
        peergroup_ebgp_v6=PEERGROUP_EBGP_V6,
        peergroup_ebgp_v4=PEERGROUP_EBGP_V4,
        peergroup_ibgp_v6=PEERGROUP_IBGP_V6,
        peergroup_ibgp_v4=PEERGROUP_IBGP_V4,
        ebgp_peer_count=1,
    )
    return test_config_for_bgp_plus_plus_on_ebb_arista_performance_scaling(
        test_config_name=name,
        device_name=DEVICE_NAME,
        host_driver_args=None,
        oss_mock_device_data=None,
        host_os_type_map={DEVICE_NAME: taac_types.DeviceOsType.ARISTA_FBOSS},
        ixia_interface_mimic_ebgp=IXIA_INTERFACE_MIMIC_EBGP,
        ixia_interface_mimic_ibgp=IXIA_INTERFACE_MIMIC_IBGP,
        direct_ixia_connections=[
            DirectIxiaConnection(
                interface=IXIA_INTERFACE_MIMIC_EBGP,
                ixia_chassis_ip=IXIA_CHASSIS_IP,
                ixia_port=IXIA_PORT_EBGP,
            ),
            DirectIxiaConnection(
                interface=IXIA_INTERFACE_MIMIC_IBGP,
                ixia_chassis_ip=IXIA_CHASSIS_IP,
                ixia_port=IXIA_PORT_IBGP,
            ),
        ],
        egress_peer_counts=BAG012_ASH6_PERFORMANCE_SCALING_EGRESS_PEER_COUNTS,
        prefix_count=BAG012_ASH6_PERFORMANCE_SCALING_PREFIX_COUNT,
        ebgp_peer_count=1,
        ebgp_remote_as=EBGP_REMOTE_AS,
        ibgp_remote_as=IBGP_REMOTE_AS,
        ixia_ebgp_ic_parent_network_v6=IXIA_EBGP_IC_PARENT_NETWORK_V6,
        ixia_ebgp_ic_parent_network_v4=IXIA_EBGP_IC_PARENT_NETWORK_V4,
        ixia_ibgp_ic_parent_network_v6=IXIA_IBGP_IC_PARENT_NETWORK_V6_DC_PLANE1,
        ixia_ibgp_ic_parent_network_v4=IXIA_IBGP_IC_PARENT_NETWORK_V4_DC_PLANE1,
        log_collection_timeout=600,
        setup_tasks=setup_tasks,
        per_iteration_setup_steps_factory=factory,
    )


BAG012_ASH6_PERFORMANCE_SCALING_TEST_CONFIG = (
    create_bag012_ash6_performance_scaling_test_config()
)

# =============================================================================
# _UPDATE_GROUP variants — same playbooks, but with BGP++ update_group +
# enableSerializeGroupPdu (per D100093369) patched into
# /mnt/flash/bgpcpp_config during BGP++ deployment so the conveyor qualifies
# the update-group BGP++ feature alongside the baseline.
# =============================================================================
BAG012_ASH6_CONVEYOR_TEST_UPDATE_GROUP_CONFIG = create_bag012_ash6_conveyor_test_config(
    enable_update_group=True,
)
BAG012_ASH6_CONSTANT_ATTRIBUTE_STORAGE_TEST_UPDATE_GROUP_CONFIG = (
    create_bag012_ash6_constant_attribute_storage_test_config(
        enable_update_group=True,
    )
)
BAG012_ASH6_QUEUE_MEMORY_MONITOR_TEST_UPDATE_GROUP_CONFIG = (
    create_bag012_ash6_queue_memory_monitor_test_config(
        enable_update_group=True,
    )
)
BAG012_ASH6_PERFORMANCE_SCALING_TEST_UPDATE_GROUP_CONFIG = (
    create_bag012_ash6_performance_scaling_test_config(
        enable_update_group=True,
    )
)


# =============================================================================
# BGP++ Bounded ECMP Sets on bag012.ash6 conveyor.
# Converted from EB02-ARISTA_PERFORMANCE_SCALING_TEST_9_BOUNDED_ECMP_SETS: the
# same upstream factory, retargeted to bag012.ash6 (IXIA ports 7/7 eBGP, 7/8
# iBGP). Device setup runs through netcastle's MANAGED shell (no raw SSH) — the
# factory patches /mnt/flash/bgpcpp_config + /usr/sbin/run_bgpcpp.sh and bounces
# the Bgp daemon via create_arista_daemon_control_task. The DUT runs with BGP++
# update_group enabled.
# =============================================================================
BAG012_ASH6_BOUNDED_ECMP_PEER_COUNT: int = 128
BAG012_ASH6_BOUNDED_ECMP_PREFIX_COUNT: int = 5000


def create_bag012_ash6_bounded_ecmp_sets_test_config() -> taac_types.TestConfig:
    """Bounded-ECMP-sets TestConfig for bag012.ash6 conveyor.

    Verifies BGP++ ECMP-set bounding at production peer scale (128 EBGP + 128
    IBGP per AFI) with update_group enabled. Targets bag012.ash6 (IXIA ports
    7/7 eBGP, 7/8 iBGP).

    Device setup uses the standard ``get_update_packing_setup_tasks`` helper --
    the same path Constant Attribute Storage / Queue Memory Monitor / Update
    Packing use -- so the configerator bgpcpp_config is deployed cleanly
    (BgpTcpdump disable, pre-IXIA interface config, control plane + ACLs,
    interface secondary IPs, config validator gate, OpenR profile handling,
    iptables flush) instead of patching the image's leftover config in place.

    Because bounded ECMP brings up IPv4 sessions too (most conveyor tests are
    validated IPv6-only), it passes ``v4_peer_start_offset=IXIA_IPV4_START_OFFSET``
    so the generated v4 peers align with the device's v4 secondary IPs and the
    bounded-ECMP IXIA-side addressing (v4 device gateways from ``.10``; v6 from
    ``::10`` which already matches the default offset 16).

    Returns:
        TestConfig object configured for bag012.ash6
    """
    setup_tasks = get_update_packing_setup_tasks(
        device_name=DEVICE_NAME,
        bgp_asn=BAG012_EOS_BGP_AS,
        ixia_interface_mimic_ebgp=IXIA_INTERFACE_MIMIC_EBGP,
        ixia_interface_mimic_ibgp=IXIA_INTERFACE_MIMIC_IBGP,
        ebgp_peer_count=BAG012_ASH6_BOUNDED_ECMP_PEER_COUNT,
        ibgp_peer_count=BAG012_ASH6_BOUNDED_ECMP_PEER_COUNT,
        ebgp_remote_as=EBGP_REMOTE_AS,
        ibgp_remote_as=IBGP_REMOTE_AS,
        ixia_ebgp_ic_parent_network_v6=IXIA_EBGP_IC_PARENT_NETWORK_V6,
        ixia_ibgp_ic_parent_network_v6=IXIA_IBGP_IC_PARENT_NETWORK_V6_DC_PLANE1,
        # Dual-stack: bounded ECMP runs v4 + v6 peers on both interfaces.
        ixia_ebgp_ic_parent_network_v4=IXIA_EBGP_IC_PARENT_NETWORK_V4,
        ixia_ibgp_ic_parent_network_v4=IXIA_IBGP_IC_PARENT_NETWORK_V4_DC_PLANE1,
        router_id=BAG012_ROUTER_ID,
        bgpcpp_configerator_path=BGPCPP_CONFIGERATOR_PATH,
        profile=BgpPlusPlusProfile.BGP_PLUS_PLUS_WITHOUT_OPEN_R,
        # Align v4 peers with the device v4 secondary IPs + IXIA .10 layout.
        v4_peer_start_offset=IXIA_IPV4_START_OFFSET,
        # DUT runs with BGP++ update_group enabled.
        enable_update_group=True,
    )

    return test_config_for_bgp_plus_plus_on_ebb_arista_bounded_ecmp_sets(
        test_config_name="BAG012_ASH6_BGP_BOUNDED_ECMP_SETS_CONVEYOR_TEST_UPDATE_GROUP",
        device_name=DEVICE_NAME,
        ixia_interface_mimic_ebgp=IXIA_INTERFACE_MIMIC_EBGP,
        ixia_interface_mimic_ibgp=IXIA_INTERFACE_MIMIC_IBGP,
        ebgp_peer_count_v6=BAG012_ASH6_BOUNDED_ECMP_PEER_COUNT,
        ibgp_peer_count_v6=BAG012_ASH6_BOUNDED_ECMP_PEER_COUNT,
        ebgp_peer_count_v4=BAG012_ASH6_BOUNDED_ECMP_PEER_COUNT,
        ibgp_peer_count_v4=BAG012_ASH6_BOUNDED_ECMP_PEER_COUNT,
        ebgp_remote_as=EBGP_REMOTE_AS,
        ibgp_remote_as=IBGP_REMOTE_AS,
        ixia_ebgp_ic_parent_network_v6=IXIA_EBGP_IC_PARENT_NETWORK_V6,
        ixia_ebgp_ic_parent_network_v4=IXIA_EBGP_IC_PARENT_NETWORK_V4,
        ixia_ibgp_ic_parent_network_v6=IXIA_IBGP_IC_PARENT_NETWORK_V6_DC_PLANE1,
        ixia_ibgp_ic_parent_network_v4=IXIA_IBGP_IC_PARENT_NETWORK_V4_DC_PLANE1,
        prefix_count=BAG012_ASH6_BOUNDED_ECMP_PREFIX_COUNT,
        direct_ixia_connections=[
            DirectIxiaConnection(
                interface=IXIA_INTERFACE_MIMIC_EBGP,
                ixia_chassis_ip=IXIA_CHASSIS_IP,
                ixia_port=IXIA_PORT_EBGP,
            ),
            DirectIxiaConnection(
                interface=IXIA_INTERFACE_MIMIC_IBGP,
                ixia_chassis_ip=IXIA_CHASSIS_IP,
                ixia_port=IXIA_PORT_IBGP,
            ),
        ],
        host_os_type_map={DEVICE_NAME: taac_types.DeviceOsType.ARISTA_FBOSS},
        # Standard device setup (configerator deploy + control plane + validator
        # + interface IPs + update_group), shared with the other bag012 conveyor
        # nodes. Passing setup_tasks skips case9's in-shell fallback.
        setup_tasks=setup_tasks,
        log_collection_timeout=600,
    )


BAG012_ASH6_BOUNDED_ECMP_SETS_TEST_UPDATE_GROUP_CONFIG = (
    create_bag012_ash6_bounded_ecmp_sets_test_config()
)


# =============================================================================
# BGP++ Update Group hardening characteristic test on bag012.ash6 -- combines
# specs 2.4.1, 2.4.2, 2.4.3 into a single TestConfig with three playbooks
# sharing one common topology: 3 eBGP receiver DGs + 3 iBGP sender DGs.
#
# Topology:
#
#   DG               multi  protocol  port            pool       role per test
#   ---------------  -----  --------  --------------  ---------- ----------------
#   Side A (receivers in EB-FA-V6 UG, on Et3/36/1)
#     DG_A_CTRL       4     eBGP      Et3/36/1        --         observe (all 3 tests)
#     DG_A_HELD       1     eBGP      Et3/36/1        --         SUT (all 3 tests)
#     DG_A_DISP      16     eBGP      Et3/36/1        --         kill 16 in 2.4.1
#   Side B (senders, on Et3/36/2)
#     DG_B_KEEP       1     iBGP      Et3/36/2        300 rts    baseline / "keep" / community
#     DG_B_VAR1       1     iBGP      Et3/36/2*       200 rts    inject / withdraw / idle
#     DG_B_VAR2       1     iBGP      Et3/36/2        50  rts    inject (2.4.1) only
#
# * VAR1 is brought UP by 2.4.2's own setup_steps (2.4.2 needs the 200 routes
#   already advertising at trigger time so a session-down trigger withdraws them).
#
# CRITICAL: Side A is eBGP and senders are iBGP -- this is the iBGP -> eBGP
# redistribution direction that bag012's existing conveyor tests use
# successfully. We tried the reverse (eBGP senders -> iBGP receivers) and
# empirically confirmed that bag012's `EB-EB-OUT` policy does NOT
# redistribute eBGP-learned routes to iBGP peers (DUT receives 300 routes
# from eBGP senders into RIB but PREFILTER advertised TO iBGP peers stays
# at 0 even with the well-known `65441:133` community attached). The
# iBGP -> eBGP direction works because that's the production flow on
# bag012's `EB-FA-OUT` policy.
#
# DUT-side `get_update_packing_setup_tasks(ebgp_peer_count=21, ibgp_peer_count=3,
# enable_update_group=True)`:
#   - 21 EB-FA-V6 peer entries at DUT-local ::10/12/.../38, IXIA peers
#     ::11/13/.../39 (EBGP network)
#   - 3 EB-EB-V6 peer entries at DUT-local ::10/12/14, IXIA peers ::11/13/15
#     (IBGP network, plane 1)
#
# All three playbooks share the same baseline-state contract:
#   {CTRL Established, HELD admin-DOWN, DISP Established, B_KEEP Established,
#    B_VAR1 admin-DOWN, B_VAR2 admin-DOWN}
# and restore it idempotently in their cleanup_steps. 2.4.2 brings B_VAR1 UP
# in its own setup_steps and restores it DOWN in its cleanup.
# =============================================================================

# UG hardening constants.
#
# IMPORTANT: Side A receivers (CTRL/HELD/DISP) live on the **eBGP** port
# (the EB-FA-V6 peer group). Side B senders live on the **iBGP** port
# (EB-EB-V6 peer group). This is the iBGP -> eBGP redistribution direction
# that bag012's existing conveyor tests use successfully.
#
# We tried the reverse (eBGP senders -> iBGP receivers) first and confirmed
# empirically that bag012's `EB-EB-OUT` policy does NOT redistribute
# eBGP-learned routes to iBGP peers -- the DUT receives routes from eBGP
# senders into RIB but PREFILTER advertised TO iBGP peers stays at 0 even
# with the well-known `65441:133` community attached. iBGP -> eBGP works.
#
# The UG-under-test is the EB-FA-V6 UG (Side A receivers). Held-back peer
# joins this UG mid-test in 2.4.1/2.4.2/2.4.3.
_UG_PEER_GROUP_SUBSTRING = "EB-FA-V6"
# Community values required to pass DUT's policy chain.
#
# The full iBGP-side community list used by bag010/011/013's working
# arista_ebb_scale tests (`arista_mimic_ebb_test_full_scale_test_config.py
# :63-71`). Routes carrying this list pass EB-EB-IN (iBGP ingress accept)
# AND survive EB-FA-OUT (eBGP egress propagation) on bag012's policy chain
# (shared bgpcpp_config). Multi-community is necessary because the policy
# permits routes matching ANY of these specific community values -- single
# communities (we tried `65441:133` and `65529:39744`) do not pass.
#
# Why multi-community: bag012's `EB-FA-OUT` policy has a deny-default with
# specific permit clauses; routes need to match at least one. The complete
# list is the production-validated set.
_UG_IBGP_SENDER_COMMUNITIES = [
    "65060:10012",
    "65140:65529",
    "65520:503",
    "65529:11610",
    "65529:39744",
    "65530:50300",
    "65530:50320",
    "65530:50800",
]
# 2.4.3 attribute-mutation: swap to a different combination. `0:665` is
# documented as permitted in both EB-FA-IN and EB-FA-OUT (per bag013 prior
# work). Keeping the full ibgp list to ensure mutated routes still pass.
_UG_INITIAL_COMMUNITY = "65529:39744"  # 2.4.3 starting "marker" community
# 2.4.3 post-mutation marker community. Must be individually permitted by
# bag012's EB-FA-OUT policy (otherwise the mutation produces routes that
# DUT silently drops at egress and the spec gate can't observe the change).
# Choice rationale: 65531:50200 (AS32934-PRIVATE-AGGREGATE) is permitted by
# EB-FA-OUT rule RULE_EB_FA_OUT_870/930 standalone, distinguishable from the
# initial 65529:39744 (rule 860). Previous choice "0:665" (EB-PLANE)
# required the AND-triplet [65529:39744, 0:665, 64562:665] (rule 850/970)
# so single-community mutation never matched any permit rule -- DUT dropped
# the mutated routes silently. Verified against the live bgpcpp_config
# `policies.bgp_policy_statements[].name="EB-FA-OUT"` dump on bag012
# 2026-06-23.
_UG_MUTATED_COMMUNITY = "65531:50200"
_UG_BASE_SENDER_COMMUNITIES = _UG_IBGP_SENDER_COMMUNITIES

# Per-DG counts (multiplier). Side A (eBGP receivers): 4+1+16 = 21 sessions.
# Side B (iBGP senders): 4 sessions (KEEP_INITIAL, KEEP_MUTATED, VAR1, VAR2).
_UG_CTRL_MULTIPLIER = 4
_UG_DISP_MULTIPLIER = 16
_UG_DISP_KILL_COUNT = 16  # kill all 16 in 2.4.1
_UG_TOTAL_EBGP_PEERS = _UG_CTRL_MULTIPLIER + 1 + _UG_DISP_MULTIPLIER  # 21
# 2.4.3 uses a two-DG topology for the attribute-change trigger: KEEP_INITIAL
# and KEEP_MUTATED both advertise the SAME 300 prefix range, but with
# different communities. At baseline only INITIAL is UP; the trigger toggles
# INITIAL DOWN + MUTATED UP, forcing DUT bestpath to flip and re-distribute
# with the new community. This bypasses IXIA's configure_community_pool API
# which empirically fails to update the wire on this topology (bag012
# 2026-06-23 v5+v6 runs: full protocol bounce via restart_protocols=True
# didn't reach DUT either with 1-community or 8-community combinations).
_UG_TOTAL_IBGP_PEERS = 1 + 1 + 1 + 1  # KEEP_INITIAL + KEEP_MUTATED + VAR1 + VAR2

# Pool sizes. KEEP+VAR1=500 gives the 2.4.2 spec's "500 routes injected,
# withdraw 200 -> 300 left" arithmetic.
_UG_KEEP_ROUTE_COUNT = 300
_UG_VAR1_ROUTE_COUNT = 200
_UG_VAR2_ROUTE_COUNT = 50

# Tag names = IXIA peer-object regex handles used by step_definitions.
# Side A receivers (CTRL/HELD/DISP) are eBGP peers in EB-FA-V6 UG.
# Side B senders (KEEP_INITIAL/KEEP_MUTATED/VAR1/VAR2) are iBGP peers.
_UG_DG_A_CTRL_TAG = "BGP_PEER_IPV6_EBGP_UG_CTRL"
_UG_DG_A_HELD_TAG = "BGP_PEER_IPV6_EBGP_UG_HELD"
_UG_DG_A_DISP_TAG = "BGP_PEER_IPV6_EBGP_UG_DISP"
_UG_DG_B_KEEP_TAG = "BGP_PEER_IPV6_IBGP_UG_B_KEEP"  # = INITIAL (legacy name)
_UG_DG_B_KEEP_MUTATED_TAG = "BGP_PEER_IPV6_IBGP_UG_B_KEEP_MUTATED"
_UG_DG_B_VAR1_TAG = "BGP_PEER_IPV6_IBGP_UG_B_VAR1"
_UG_DG_B_VAR2_TAG = "BGP_PEER_IPV6_IBGP_UG_B_VAR2"


# IXIA-side peer addresses derived from `_generate_ixia_v6_peer_entries_for_bgpcpp`
# (start_offset=0x10, stride=2). For each AF: DUT-local at offset i*2+0x10
# (::10, ::12, ...); IXIA-side peer at i*2+0x11 (::11, ::13, ...).
def _ug_ibgp_peer_addr(idx: int) -> str:
    """IXIA-side peer address for the idx-th iBGP peer (0-based)."""
    return f"{IXIA_IBGP_IC_PARENT_NETWORK_V6_DC_PLANE1}::{0x11 + 2 * idx:x}"


def _ug_ibgp_gateway_addr(idx: int) -> str:
    """DUT-side iBGP local address (= IXIA-side gateway) for the idx-th peer."""
    return f"{IXIA_IBGP_IC_PARENT_NETWORK_V6_DC_PLANE1}::{0x10 + 2 * idx:x}"


def _ug_ebgp_peer_addr(idx: int) -> str:
    """IXIA-side peer address for the idx-th eBGP peer (sender)."""
    return f"{IXIA_EBGP_IC_PARENT_NETWORK_V6}::{0x11 + 2 * idx:x}"


def _ug_ebgp_gateway_addr(idx: int) -> str:
    """DUT-side eBGP local address (= IXIA-side gateway) for the idx-th peer."""
    return f"{IXIA_EBGP_IC_PARENT_NETWORK_V6}::{0x10 + 2 * idx:x}"


# Allocate peer index ranges to roles within their respective AF/protocol.
# eBGP indices (Side A receivers): 21 peers total on Et3/36/1.
_UG_EBGP_CTRL_START_IDX = 0  # 0..3
_UG_EBGP_HELD_IDX = 4
_UG_EBGP_DISP_START_IDX = 5  # 5..20
# iBGP indices (Side B senders): 4 peers total on Et3/36/2.
_UG_IBGP_B_KEEP_IDX = 0  # KEEP_INITIAL -- baseline UP, advertises initial community
_UG_IBGP_B_KEEP_MUTATED_IDX = (
    1  # KEEP_MUTATED -- baseline DOWN, advertises mutated community
)
_UG_IBGP_B_VAR1_IDX = 2
_UG_IBGP_B_VAR2_IDX = 3

# Mutated 8-community list: base list with the marker position swapped from
# _UG_INITIAL_COMMUNITY -> _UG_MUTATED_COMMUNITY. KEEP_MUTATED advertises with
# this so DUT bestpath flip (KEEP_INITIAL DOWN, KEEP_MUTATED UP) propagates
# the swap through EB-FA-OUT to HELD+CTRL.
_UG_MUTATED_SENDER_COMMUNITIES = [
    _UG_MUTATED_COMMUNITY if c == _UG_INITIAL_COMMUNITY else c
    for c in _UG_BASE_SENDER_COMMUNITIES
]

# Resolved peer-IP lists used by playbook factories.
_UG_CTRL_PEER_ADDRS = [
    _ug_ebgp_peer_addr(_UG_EBGP_CTRL_START_IDX + i) for i in range(_UG_CTRL_MULTIPLIER)
]
_UG_HELD_PEER_ADDR = _ug_ebgp_peer_addr(_UG_EBGP_HELD_IDX)
_UG_DISP_PEER_ADDRS = [
    _ug_ebgp_peer_addr(_UG_EBGP_DISP_START_IDX + i) for i in range(_UG_DISP_MULTIPLIER)
]
_UG_B_KEEP_PEER_ADDR = _ug_ibgp_peer_addr(_UG_IBGP_B_KEEP_IDX)
_UG_B_KEEP_MUTATED_PEER_ADDR = _ug_ibgp_peer_addr(_UG_IBGP_B_KEEP_MUTATED_IDX)
_UG_B_VAR1_PEER_ADDR = _ug_ibgp_peer_addr(_UG_IBGP_B_VAR1_IDX)
_UG_B_VAR2_PEER_ADDR = _ug_ibgp_peer_addr(_UG_IBGP_B_VAR2_IDX)


def _ug_bgp_dg(
    *,
    device_group_index: int,
    tag_name: str,
    multiplier: int,
    starting_peer_ip: str,
    gateway_ip: str,
    remote_as: int,
    is_ebgp: bool,
    advertised_route_count: int = 0,
    starting_prefix: str = "",
    communities: t.Optional[t.List[str]] = None,
) -> taac_types.DeviceGroupConfig:
    """Build one BGP DG (eBGP or iBGP) for the UG hardening topology.

    When ``advertised_route_count == 0`` the DG is receive-only (no
    ``v6_bgp_config.route_scales``). When > 0, attaches a single
    ``RouteScaleSpec`` carrying ``advertised_route_count`` /128 prefixes
    starting at ``starting_prefix`` with optional ``bgp_communities``.

    The peer's BgpConfig name (``bgp_peer_name=tag_name``) is what
    ``create_start_stop_bgp_peers_step``'s ``peer_regex`` matches against.
    """
    route_scales = []
    if advertised_route_count > 0:
        route_scales = [
            taac_types.RouteScaleSpec(
                network_group_index=0,
                v6_route_scale=taac_types.RouteScale(
                    multiplier=1,
                    prefix_count=advertised_route_count,
                    prefix_length=128,
                    starting_prefixes=starting_prefix,
                    prefix_step="0:0:0:0::1",
                    bgp_communities=list(communities or []),
                    ip_address_family=ixia_types.IpAddressFamily.IPV6,
                ),
            ),
        ]

    peer_type = ixia_types.BgpPeerType.EBGP if is_ebgp else ixia_types.BgpPeerType.IBGP

    return taac_types.DeviceGroupConfig(
        device_group_index=device_group_index,
        tag_name=tag_name,
        multiplier=multiplier,
        v6_addresses_config=taac_types.IpAddressesConfig(
            starting_ip=starting_peer_ip,
            increment_ip="0:0:0:0::2",
            gateway_starting_ip=gateway_ip,
            gateway_increment_ip="0:0:0:0::2",
            mask=127,
            start_index=0,
        ),
        v6_bgp_config=taac_types.BgpConfig(
            bgp_peer_name=tag_name,
            local_as_4_bytes=remote_as,
            enable_4_byte_local_as=True,
            bgp_peer_type=peer_type,
            bgp_capabilities=[ixia_types.BgpCapability.IpV6Unicast],
            hold_timer=30,
            keepalive_timer=10,
            route_scales=route_scales,
        ),
    )


def _ebgp_dgs() -> list:
    """Return the 3 eBGP receiver DGs on Et3/36/1 (CTRL, HELD, DISP).

    Receivers are passively in the EB-FA-V6 UG. The DUT's `EB-FA-OUT`
    policy advertises iBGP-learned routes (from senders B_KEEP/VAR1/VAR2
    on Et3/36/2) out to these eBGP peers -- the canonical iBGP -> eBGP
    redistribution direction that all existing bag012 conveyor tests use.
    """
    return [
        _ug_bgp_dg(
            device_group_index=0,
            tag_name=_UG_DG_A_CTRL_TAG,
            multiplier=_UG_CTRL_MULTIPLIER,
            starting_peer_ip=_ug_ebgp_peer_addr(_UG_EBGP_CTRL_START_IDX),
            gateway_ip=_ug_ebgp_gateway_addr(_UG_EBGP_CTRL_START_IDX),
            remote_as=EBGP_REMOTE_AS,
            is_ebgp=True,
        ),
        _ug_bgp_dg(
            device_group_index=1,
            tag_name=_UG_DG_A_HELD_TAG,
            multiplier=1,
            starting_peer_ip=_ug_ebgp_peer_addr(_UG_EBGP_HELD_IDX),
            gateway_ip=_ug_ebgp_gateway_addr(_UG_EBGP_HELD_IDX),
            remote_as=EBGP_REMOTE_AS,
            is_ebgp=True,
        ),
        _ug_bgp_dg(
            device_group_index=2,
            tag_name=_UG_DG_A_DISP_TAG,
            multiplier=_UG_DISP_MULTIPLIER,
            starting_peer_ip=_ug_ebgp_peer_addr(_UG_EBGP_DISP_START_IDX),
            gateway_ip=_ug_ebgp_gateway_addr(_UG_EBGP_DISP_START_IDX),
            remote_as=EBGP_REMOTE_AS,
            is_ebgp=True,
        ),
    ]


def _ibgp_dgs() -> list:
    """Return the 4 iBGP sender DGs on Et3/36/2.

    DGs:
      - KEEP_INITIAL: 300 rts at 2401:db00:1000::, initial community marker,
        baseline UP -> DUT bestpath at start.
      - KEEP_MUTATED: SAME 300 rts at 2401:db00:1000::, mutated community
        marker, baseline DOWN. The 2.4.3 trigger toggles INITIAL DOWN +
        MUTATED UP, forcing DUT bestpath to flip and re-distribute the
        mutated community via EB-FA-OUT to HELD+CTRL.
      - VAR1: 200 rts at 2401:db00:2000:: (2.4.2 withdraw target).
      - VAR2: 50 rts at 2401:db00:3000::.

    Senders advertise routes INTO the DUT RIB via iBGP; the DUT then
    redistributes via EB-FA-OUT (iBGP -> eBGP) to the Side A receivers.
    """
    return [
        _ug_bgp_dg(
            device_group_index=0,
            tag_name=_UG_DG_B_KEEP_TAG,
            multiplier=1,
            starting_peer_ip=_ug_ibgp_peer_addr(_UG_IBGP_B_KEEP_IDX),
            gateway_ip=_ug_ibgp_gateway_addr(_UG_IBGP_B_KEEP_IDX),
            remote_as=IBGP_REMOTE_AS,
            is_ebgp=False,
            advertised_route_count=_UG_KEEP_ROUTE_COUNT,
            starting_prefix="2401:db00:1000::",
            communities=_UG_BASE_SENDER_COMMUNITIES,
        ),
        _ug_bgp_dg(
            device_group_index=1,
            tag_name=_UG_DG_B_KEEP_MUTATED_TAG,
            multiplier=1,
            starting_peer_ip=_ug_ibgp_peer_addr(_UG_IBGP_B_KEEP_MUTATED_IDX),
            gateway_ip=_ug_ibgp_gateway_addr(_UG_IBGP_B_KEEP_MUTATED_IDX),
            remote_as=IBGP_REMOTE_AS,
            is_ebgp=False,
            advertised_route_count=_UG_KEEP_ROUTE_COUNT,
            starting_prefix="2401:db00:1000::",
            communities=_UG_MUTATED_SENDER_COMMUNITIES,
        ),
        _ug_bgp_dg(
            device_group_index=2,
            tag_name=_UG_DG_B_VAR1_TAG,
            multiplier=1,
            starting_peer_ip=_ug_ibgp_peer_addr(_UG_IBGP_B_VAR1_IDX),
            gateway_ip=_ug_ibgp_gateway_addr(_UG_IBGP_B_VAR1_IDX),
            remote_as=IBGP_REMOTE_AS,
            is_ebgp=False,
            advertised_route_count=_UG_VAR1_ROUTE_COUNT,
            starting_prefix="2401:db00:2000::",
            communities=_UG_BASE_SENDER_COMMUNITIES,
        ),
        _ug_bgp_dg(
            device_group_index=3,
            tag_name=_UG_DG_B_VAR2_TAG,
            multiplier=1,
            starting_peer_ip=_ug_ibgp_peer_addr(_UG_IBGP_B_VAR2_IDX),
            gateway_ip=_ug_ibgp_gateway_addr(_UG_IBGP_B_VAR2_IDX),
            remote_as=IBGP_REMOTE_AS,
            is_ebgp=False,
            advertised_route_count=_UG_VAR2_ROUTE_COUNT,
            starting_prefix="2401:db00:3000::",
            communities=_UG_BASE_SENDER_COMMUNITIES,
        ),
    ]


def _baseline_steps(
    *,
    bring_var1_up: bool = False,
) -> list:
    """Return setup_steps that bring HELD/VAR1/VAR2 to a clean baseline state.

    SCRUB-THEN-REARM pattern:
      Plain ``start_bgp_peers(start=False)`` only halts the IXIA BGP FSM --
      DUT's adj-RIB-out keeps the sender's previously-advertised routes as
      STALE entries (BGP++ doesn't withdraw on session-IDLE alone). Across
      a 3-playbook run that contamination accumulates: 2.4.3 ends up seeing
      550 advertised prefixes (300 KEEP fresh + 200 VAR1 stale + 50 VAR2
      stale, all carrying the OLD community) which breaks the 2.4.3 spec
      gate's "no route carries the OLD community" assertion.

      The fix: ``toggle_device_groups(enable=False)`` on VAR1 + VAR2 -- the
      durable DG-admin-down primitive proven to drive DUT withdrawal (per
      the 2.4.2 trigger). Settle long enough for DUT's hold-timer to fire
      and routes to leave adj-RIB-out (~90s observed empirically on
      bag012). Then re-enable the DGs so subsequent ``start_bgp_peers``
      can act on them, and place sessions at the per-playbook state.

      HELD uses plain start_bgp_peers throughout (no scrub needed -- HELD
      is admin-down at baseline AND the trigger brings it UP via the same
      start_bgp_peers API; no stale-route concern because HELD is a
      RECEIVER, not a sender).

    Per-playbook expected end state:
      - 2.4.1 / 2.4.3 (``bring_var1_up=False``): {HELD DOWN, VAR1 DOWN,
        VAR2 DOWN, KEEP_MUTATED DG-disabled}
      - 2.4.2 (``bring_var1_up=True``): {HELD DOWN, VAR1 UP, VAR2 DOWN,
        KEEP_MUTATED DG-disabled}
        (VAR1 is the 2.4.2 withdrawal trigger target -- must be advertising.)

    KEEP_MUTATED stays DG-disabled at baseline across all playbooks so only
    KEEP_INITIAL contributes routes to DUT bestpath. The 2.4.3 trigger flips
    the pair (INITIAL DOWN + MUTATED UP) to swap the community on the wire.

    Cost: +~90s per playbook setup for the scrub. Worth it to keep spec
    gates clean (wireshark captures in tcpdump prove the withdraw fires on
    wire when DG is disabled -- see 2.4.2 v17 empirical work).
    """
    return [
        # SCRUB Phase: DG-disable VAR1 + VAR2 + KEEP_MUTATED to clear stale
        # adj-RIB-out on DUT (the transient start_bgp_peers approach leaves
        # stale; and KEEP_MUTATED is DG-disabled at baseline so only
        # KEEP_INITIAL contributes the 300-prefix bestpath).
        create_ixia_api_step(
            api_name="toggle_device_groups",
            args_dict={
                "enable": False,
                "device_group_name_regex": _UG_DG_B_VAR1_TAG,
                "sleep_time_before_applying_change": 0,
            },
            description=(
                "UG baseline SCRUB: DG-disable DG_B_VAR1 -- forces DUT to "
                "drop stale VAR1 routes from adj-RIB-out via hold-timer"
            ),
        ),
        create_ixia_api_step(
            api_name="toggle_device_groups",
            args_dict={
                "enable": False,
                "device_group_name_regex": _UG_DG_B_VAR2_TAG,
                "sleep_time_before_applying_change": 0,
            },
            description=(
                "UG baseline SCRUB: DG-disable DG_B_VAR2 -- forces DUT to "
                "drop stale VAR2 routes from adj-RIB-out via hold-timer"
            ),
        ),
        create_ixia_api_step(
            api_name="toggle_device_groups",
            args_dict={
                "enable": False,
                "device_group_name_regex": _UG_DG_B_KEEP_MUTATED_TAG,
                "sleep_time_before_applying_change": 0,
            },
            description=(
                "UG baseline SCRUB: DG-disable DG_B_KEEP_MUTATED -- ensures "
                "only KEEP_INITIAL advertises the 300-prefix range at baseline "
                "(2.4.3 trigger toggles this pair to swap community)"
            ),
        ),
        create_longevity_step(
            duration=90,
            description=(
                "UG baseline SCRUB: settle 90s for DUT hold-timer expiry "
                "+ adj-RIB-out withdraw to propagate (iBGP peer-group "
                "hold-time is >60s on bag012, per 2.4.2 v17 finding)"
            ),
        ),
        # REARM Phase: re-enable VAR1 + VAR2 DGs so the per-playbook
        # start_bgp_peers admin-state moves below have a valid DG to act on.
        # KEEP_MUTATED stays DG-disabled (2.4.3 trigger flips it).
        create_ixia_api_step(
            api_name="toggle_device_groups",
            args_dict={
                "enable": True,
                "device_group_name_regex": _UG_DG_B_VAR1_TAG,
                "sleep_time_before_applying_change": 0,
            },
            description="UG baseline REARM: re-enable DG_B_VAR1",
        ),
        create_ixia_api_step(
            api_name="toggle_device_groups",
            args_dict={
                "enable": True,
                "device_group_name_regex": _UG_DG_B_VAR2_TAG,
                "sleep_time_before_applying_change": 0,
            },
            description="UG baseline REARM: re-enable DG_B_VAR2",
        ),
        # Per-playbook session-state placement
        create_start_stop_bgp_peers_step(
            peer_regex=_UG_DG_A_HELD_TAG,
            start=False,
            start_idx=1,
            end_idx=1,
            description="UG baseline: bring HELD admin-DOWN",
        ),
        create_start_stop_bgp_peers_step(
            peer_regex=_UG_DG_B_VAR1_TAG,
            start=bring_var1_up,
            start_idx=1,
            end_idx=1,
            description=(
                "UG baseline: bring DG_B_VAR1 admin-"
                + ("UP" if bring_var1_up else "DOWN")
            ),
        ),
        create_start_stop_bgp_peers_step(
            peer_regex=_UG_DG_B_VAR2_TAG,
            start=False,
            start_idx=1,
            end_idx=1,
            description="UG baseline: bring DG_B_VAR2 admin-DOWN",
        ),
    ]


def _pb_2_4_1() -> taac_types.Playbook:
    return create_new_peer_join_full_sync_resilience_playbook(
        device_name=DEVICE_NAME,
        control_peer_addrs=_UG_CTRL_PEER_ADDRS,
        held_back_peer_addr=_UG_HELD_PEER_ADDR,
        held_back_peer_regex=_UG_DG_A_HELD_TAG,
        disp_peer_addrs=_UG_DISP_PEER_ADDRS,
        disp_peer_regex=_UG_DG_A_DISP_TAG,
        disp_session_start_idx=1,
        disp_session_end_idx=_UG_DISP_KILL_COUNT,
        b_keep_peer_addr=_UG_B_KEEP_PEER_ADDR,
        b_keep_route_count=_UG_KEEP_ROUTE_COUNT,
        b_var1_peer_regex=_UG_DG_B_VAR1_TAG,
        b_var1_peer_addr=_UG_B_VAR1_PEER_ADDR,
        b_var1_route_count=_UG_VAR1_ROUTE_COUNT,
        b_var2_peer_regex=_UG_DG_B_VAR2_TAG,
        b_var2_peer_addr=_UG_B_VAR2_PEER_ADDR,
        b_var2_route_count=_UG_VAR2_ROUTE_COUNT,
        ug_peer_group_substring=_UG_PEER_GROUP_SUBSTRING,
        setup_steps=_baseline_steps(bring_var1_up=False),
    )


def _pb_2_4_2() -> taac_types.Playbook:
    # 2.4.2 needs DG_B_VAR1 ESTABLISHED before its prechecks run -- the
    # common baseline brings it DOWN. The factory's `setup_steps` is the hook
    # for "do this before prechecks run".
    return create_new_peer_join_routes_withdrawn_playbook(
        device_name=DEVICE_NAME,
        control_peer_addrs=_UG_CTRL_PEER_ADDRS,
        held_back_peer_addr=_UG_HELD_PEER_ADDR,
        held_back_peer_regex=_UG_DG_A_HELD_TAG,
        b_keep_peer_addr=_UG_B_KEEP_PEER_ADDR,
        b_keep_route_count=_UG_KEEP_ROUTE_COUNT,
        b_var1_peer_regex=_UG_DG_B_VAR1_TAG,
        b_var1_peer_addr=_UG_B_VAR1_PEER_ADDR,
        b_var1_route_count=_UG_VAR1_ROUTE_COUNT,
        b_var1_device_group_regex=_UG_DG_B_VAR1_TAG,
        ug_peer_group_substring=_UG_PEER_GROUP_SUBSTRING,
        capture_tcpdump_device=DEVICE_NAME,
        setup_steps=_baseline_steps(bring_var1_up=True),
    )


def _pb_2_4_3() -> taac_types.Playbook:
    return create_new_peer_join_attribute_change_playbook(
        device_name=DEVICE_NAME,
        control_peer_addrs=_UG_CTRL_PEER_ADDRS,
        held_back_peer_addr=_UG_HELD_PEER_ADDR,
        held_back_peer_regex=_UG_DG_A_HELD_TAG,
        b_keep_peer_addr=_UG_B_KEEP_PEER_ADDR,
        b_keep_route_count=_UG_KEEP_ROUTE_COUNT,
        b_keep_peer_regex=_UG_DG_B_KEEP_TAG,
        b_keep_device_group_regex=_UG_DG_B_KEEP_TAG,
        b_keep_mutated_peer_addr=_UG_B_KEEP_MUTATED_PEER_ADDR,
        b_keep_mutated_device_group_regex=_UG_DG_B_KEEP_MUTATED_TAG,
        initial_community=_UG_INITIAL_COMMUNITY,
        mutated_community=_UG_MUTATED_COMMUNITY,
        ug_peer_group_substring=_UG_PEER_GROUP_SUBSTRING,
        setup_steps=_baseline_steps(bring_var1_up=False),
    )


def _config_shell(
    *,
    name: str,
    playbooks: list,
) -> taac_types.TestConfig:
    """Shared TestConfig shell for the UG hardening "new peer join" test."""
    setup_tasks = get_update_packing_setup_tasks(
        device_name=DEVICE_NAME,
        bgp_asn=BAG012_EOS_BGP_AS,
        ixia_interface_mimic_ebgp=IXIA_INTERFACE_MIMIC_EBGP,
        ixia_interface_mimic_ibgp=IXIA_INTERFACE_MIMIC_IBGP,
        ebgp_peer_count=_UG_TOTAL_EBGP_PEERS,  # 3 senders
        ibgp_peer_count=_UG_TOTAL_IBGP_PEERS,  # 21 receivers (CTRL+HELD+DISP)
        ebgp_remote_as=EBGP_REMOTE_AS,
        ibgp_remote_as=IBGP_REMOTE_AS,
        ixia_ebgp_ic_parent_network_v6=IXIA_EBGP_IC_PARENT_NETWORK_V6,
        ixia_ibgp_ic_parent_network_v6=IXIA_IBGP_IC_PARENT_NETWORK_V6_DC_PLANE1,
        router_id=BAG012_ROUTER_ID,
        bgpcpp_configerator_path=BGPCPP_CONFIGERATOR_PATH,
        profile=BgpPlusPlusProfile.BGP_PLUS_PLUS_WITHOUT_OPEN_R,
        enable_update_group=True,
    )

    return taac_types.TestConfig(
        name=name,
        skip_ixia_protocol_verification=True,
        log_collection_timeout=600,
        basset_pool="dne.test",
        # IxiaConfigCache enabled by default -- the framework's hashing
        # method now correctly invalidates on topology changes so stale
        # caches are no longer a risk.
        endpoints=[
            taac_types.Endpoint(
                name=DEVICE_NAME,
                dut=True,
                ixia_ports=[
                    f"{IXIA_CHASSIS_IP}:{IXIA_PORT_EBGP}",
                    f"{IXIA_CHASSIS_IP}:{IXIA_PORT_IBGP}",
                ],
                direct_ixia_connections=[
                    taac_types.DirectIxiaConnection(
                        interface=IXIA_INTERFACE_MIMIC_EBGP,
                        ixia_chassis_ip=IXIA_CHASSIS_IP,
                        ixia_port=IXIA_PORT_EBGP,
                    ),
                    taac_types.DirectIxiaConnection(
                        interface=IXIA_INTERFACE_MIMIC_IBGP,
                        ixia_chassis_ip=IXIA_CHASSIS_IP,
                        ixia_port=IXIA_PORT_IBGP,
                    ),
                ],
            ),
        ],
        host_os_type_map={DEVICE_NAME: taac_types.DeviceOsType.ARISTA_FBOSS},
        startup_checks=[],
        setup_tasks=setup_tasks,
        teardown_tasks=[],
        basic_port_configs=[
            taac_types.BasicPortConfig(
                endpoint=f"{DEVICE_NAME}:{IXIA_INTERFACE_MIMIC_EBGP}",
                device_group_configs=_ebgp_dgs(),
            ),
            taac_types.BasicPortConfig(
                endpoint=f"{DEVICE_NAME}:{IXIA_INTERFACE_MIMIC_IBGP}",
                device_group_configs=_ibgp_dgs(),
            ),
        ],
        playbooks=playbooks,
    )


def create_bgp_ug_new_peer_join_test_config() -> taac_types.TestConfig:
    """Return the BGP++ Update Group "new peer join" TestConfig -- the 3
    qualification playbooks 2.4.1 / 2.4.2 / 2.4.3 sharing one 21-eBGP +
    4-iBGP testbed. ``enable_update_group=True`` is hard-coded (UG MUST be
    on for these specs).
    """
    return _config_shell(
        name="BGP_UG_NEW_PEER_JOIN_TEST",
        playbooks=[_pb_2_4_1(), _pb_2_4_2(), _pb_2_4_3()],
    )


BGP_UG_NEW_PEER_JOIN_TEST_CONFIG = create_bgp_ug_new_peer_join_test_config()
