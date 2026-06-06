# pyre-unsafe
"""
FBOSS DCTypeF 51T NPI CPU Queue Test Configuration

This module provides configuration for testing CPU queue classification
on FBOSS DCTypeF 51T platforms. It includes only non-disruptive CPU queue
tests, excluding warmboot, coldboot, and service restart playbooks.
"""

import asyncio
import json

from ixia.ixia import types as ixia_types
from taac.packet_headers import (
    ARP_REQUEST_TRAFFIC_PACKET_HEADERS,
    ARP_RESPONSE_TRAFFIC_PACKET_HEADERS,
    BGP_CP_TRAFFIC_PACKET_HEADERS,
    BGP_CP_V4_DSCP0_TRAFFIC_PACKET_HEADERS,
    BGP_CP_V4_TRAFFIC_PACKET_HEADERS,
    DHCP_V4_DISCOVER_TO_SERVER_TRAFFIC_PACKET_HEADERS,
    DHCP_V4_DISCOVER_TRAFFIC_PACKET_HEADERS,
    DHCP_V6_TRAFFIC_PACKET_HEADERS,
    HOP_LIMIT_0_IPV6_TRAFFIC_PACKET_HEADERS,
    HOP_LIMIT_1_IPV6_TRAFFIC_PACKET_HEADERS,
    ICMP_V4_DEST_UNREACHABLE_TRAFFIC_PACKET_HEADERS,
    ICMP_V4_ECHO_REPLY_TRAFFIC_PACKET_HEADERS,
    ICMP_V4_ECHO_REQUEST_TRAFFIC_PACKET_HEADERS,
    ICMP_V4_TIME_EXCEEDED_TRAFFIC_PACKET_HEADERS,
    ICMP_V6_DEST_UNREACHABLE_GLOBAL_DSCP48_TRAFFIC_PACKET_HEADERS,
    ICMP_V6_DEST_UNREACHABLE_LINK_LOCAL_TRAFFIC_PACKET_HEADERS,
    ICMP_V6_ECHO_REPLY_GLOBAL_DSCP48_TRAFFIC_PACKET_HEADERS,
    ICMP_V6_ECHO_REPLY_LINK_LOCAL_TRAFFIC_PACKET_HEADERS,
    ICMP_V6_ECHO_REQUEST_GLOBAL_DSCP48_TRAFFIC_PACKET_HEADERS,
    ICMP_V6_ECHO_REQUEST_LINK_LOCAL_TRAFFIC_PACKET_HEADERS,
    ICMP_V6_PACKET_TOO_BIG_GLOBAL_DSCP48_TRAFFIC_PACKET_HEADERS,
    ICMP_V6_PACKET_TOO_BIG_LINK_LOCAL_TRAFFIC_PACKET_HEADERS,
    ICMP_V6_REQUEST_TRAFFIC_PACKET_HEADERS,
    ICMP_V6_TIME_EXCEEDED_GLOBAL_DSCP48_TRAFFIC_PACKET_HEADERS,
    ICMP_V6_TIME_EXCEEDED_LINK_LOCAL_TRAFFIC_PACKET_HEADERS,
    LACP_SLOW_TIMER_TRAFFIC_PACKET_HEADERS,
    LLDP_TRAFFIC_PACKET_HEADERS,
    NDP_NA_MULTICAST_TRAFFIC_PACKET_HEADERS,
    NDP_NA_UNICAST_TRAFFIC_PACKET_HEADERS,
    NDP_NS_MULTICAST_TRAFFIC_PACKET_HEADERS,
    NDP_NS_UNICAST_TRAFFIC_PACKET_HEADERS,
    NDP_RA_MULTICAST_TRAFFIC_PACKET_HEADERS,
    NDP_RA_UNICAST_TRAFFIC_PACKET_HEADERS,
    NDP_RS_MULTICAST_TRAFFIC_PACKET_HEADERS,
    NDP_RS_UNICAST_TRAFFIC_PACKET_HEADERS,
    TTL_0_IPV4_TRAFFIC_PACKET_HEADERS,
    TTL_1_IPV4_TRAFFIC_PACKET_HEADERS,
    UNH_REMOTE_SUBNET_128_IPV6_TRAFFIC_PACKET_HEADERS,
    UNH_REMOTE_SUBNET_IPV6_TRAFFIC_PACKET_HEADERS,
)
from taac.playbooks.playbook_definitions import (
    add_common_checks_to_cpu_queue_playbooks,
    create_cpu_queue_playbooks,
)
from taac.task_definitions import (
    create_configure_parallel_bgp_peers_task,
    create_coop_apply_patchers_task,
    create_coop_register_patcher_task,
    create_coop_unregister_patchers_task,
    create_wait_for_agent_convergence_task,
)
from taac.utils.netwhoami_utils import fetch_whoami
from taac.test_as_a_config import types as taac_types
from taac.test_as_a_config.types import TestConfig


def get_cpu_queue_constants(hostname: str):
    """
    Determine CPU queue constants based on hardware type using netwhoami.

    Args:
        hostname: Device hostname to query hardware information

    Returns:
        tuple: (low_queue, mid_queue, high_queue) values based on hardware

    Raises:
        ValueError: If hardware type is unknown or unsupported
        Exception: If netwhoami fetch fails
    """
    try:
        # Use asyncio.run to call the async fetch_whoami function synchronously
        netwhoami = asyncio.run(fetch_whoami(hostname))
        # Normalize hardware to its symbolic name so this works identically for
        # the Meta NetWhoAmI thrift (enum .name) and the OSS stand-in (string name).
        hardware = netwhoami.hw.name if netwhoami.hw else ""

        # Check against specific Hardware names from the thrift Hardware enum.
        if (
            hardware
            in (
                "MONTBLANC",  # MONTBLANC = 40 (for minipack3)
                "MINIPACK3BA",  # MINIPACK3BA = 72
                "ICECUBE800BC",  # ICECUBE800BC = 70 (IcePack TH6 — Pavan-confirmed same queues as Minipack3)
            )
        ):
            return (0, 2, 9)
        elif hardware == "MORGAN800CC":  # MORGAN800CC = 46 (Kodiak3)
            return (0, 2, 7)
        else:
            raise ValueError(
                f"Unknown or unsupported hardware type '{hardware}' for {hostname}. "
                f"Please add CPU queue constants for this hardware type."
            )
    except Exception as e:
        if isinstance(e, ValueError):
            # Re-raise ValueError (unknown hardware type)
            raise
        # For all other exceptions (netwhoami fetch failures), raise with context
        raise Exception(f"Failed to fetch netwhoami for {hostname}: {e}") from e


def create_dctypef_npi_cpu_queue_test_config(
    test_config_name,
    device_name,
    local_mac_address,
    ixia_downlink_interface,
    ixia_uplink_interface,
    ixia_rogue_interface,
    peergroup_uplink_mimic_v6,
    peergroup_downlink_mimic_v6,
    peergroup_uplink_mimic_v4,
    peergroup_downlink_mimic_v4,
    peergroup_rogue_mimic_v6,
    peergroup_rogue_mimic_v4,
    route_map_uplink_ingress,
    route_map_uplink_egress,
    route_map_downlink_ingress,
    route_map_downlink_egress,
    route_map_rogue_ingress,
    route_map_rogue_egress,
    ixia_downlink_ic_parent_network_v6,
    ixia_uplink_ic_parent_network_v6,
    ixia_rogue_ic_parent_network_v6,
    ixia_downlink_ic_parent_network_v4,
    ixia_uplink_ic_parent_network_v4,
    ixia_rogue_ic_parent_network_v4,
    unique_prefix_limit,
    per_peer_max_route_limit,
    downlink_peer_count,
    uplink_peer_count,
    rogue_peer_count,
    remote_uplink_as_4byte,
    remote_downlink_as_4byte,
    remote_as_4_byte_step,
    remote_rogue_as_4byte,
    is_uplink_peer_confed,
    is_downlink_peer_confed,
    is_rogue_peer_confed,
    ixia_downlink_prefix_count_v6,
    ixia_uplink_prefix_count_v6,
    ixia_rogue_prefix_count_v6,
    ixia_downlink_prefix_count_v4,
    ixia_uplink_prefix_count_v4,
    ixia_rogue_prefix_count_v4,
    ixia_downlink_communities,
    ixia_uplink_communities,
    uplink_peer_tag,
    downlink_peer_tag,
    bgpd_rss_limit=5,
    bgpd_cache_size_limit=4000,
    bgpd_restart_no_of_interations=1,
    wedge_agent_restart_no_of_interations=1,
    direct_ixia_connections=None,
    basset_pool=None,
    ixia_packet_loss_threshold: str = "0.1",
):
    """Build the DC-TypeF 51T NPI CPU queue TestConfig.

    Constructs a single-DUT TestConfig for the DC-TypeF 51T New Product Introduction
    (NPI) flow that exercises CPU-queue prioritization (control plane vs. data plane)
    on a TH4 / TH5-class platform. Configures uplink/downlink/rogue BGP peer groups
    (V6 + V4 SAFI), ECMP overflow, and runs the NPI CPU queue check playbook.

    Args:
        test_config_name: Name to register in the TestConfig (CLI-callable).
        device_name: DUT hostname.
        local_mac_address: Local MAC address for the DUT side of IXIA peering.
        ixia_downlink_interface / ixia_uplink_interface / ixia_rogue_interface:
            DUT-facing IXIA ports for each peer group.
        peergroup_*_mimic_v6 / _v4: BGP peer-group names per direction and AFI.
        route_map_*_ingress / _egress: Inbound/outbound policy per direction.
        ixia_*_ic_parent_network_v6 / _v4: IXIA-side parent IP for each interface.
        unique_prefix_limit: Per-peer unique-prefix cap programmed on the DUT.
        per_peer_max_route_limit: Per-peer max-route guard.
        downlink_peer_count / uplink_peer_count / rogue_peer_count: Mimic peer counts.
        remote_uplink_as_4byte / remote_downlink_as_4byte: Remote AS numbers (4-byte).
        remote_as_4_byte_step: Remote-AS increment between peers.
        bgpd_rss_limit / bgpd_cache_size_limit: BGPd resource limits.
        bgpd_restart_no_of_interations / wedge_agent_restart_no_of_interations:
            Restart iteration counts (sic — preserves historical typo).
        direct_ixia_connections: Optional explicit direct-IXIA connection mapping.
        basset_pool: Override basset pool selection.

    Returns:
        TestConfig: The DC-TypeF NPI CPU queue TestConfig.
    """
    # Get hardware-specific CPU queue constants
    low_queue, mid_queue, high_queue = get_cpu_queue_constants(device_name)
    # Create and return the complete test configuration
    return TestConfig(
        name=test_config_name,
        ixia_protocol_verification_timeout=600,
        basset_pool="dne.test",
        endpoints=[
            taac_types.Endpoint(
                name=device_name,
                ixia_ports=[
                    ixia_downlink_interface,
                    ixia_uplink_interface,
                ],
                dut=True,
                mac_address=local_mac_address,
                direct_ixia_connections=direct_ixia_connections or [],
            ),
        ],
        # Setup tasks to configure the device before testing
        setup_tasks=[
            create_coop_unregister_patchers_task(device_name),
            # Remove all the bgp peers present in the device first
            create_coop_register_patcher_task(
                hostname=device_name,
                config_name="bgpcpp",
                patcher_name="a_remove_bgp_peers",
                task_name="coop_register_patcher",
                patcher_args={"delete_all": "True"},
                py_func_name="remove_bgp_peers",
            ),
            # Configure BGP switch prefix limit
            create_coop_register_patcher_task(
                hostname=device_name,
                config_name="bgpcpp",
                patcher_name="configure_bgp_switch_limit",
                task_name="coop_register_patcher",
                patcher_args={
                    "prefix_limit": unique_prefix_limit,
                },
                py_func_name="configure_bgp_switch_limit",
            ),
            create_coop_register_patcher_task(
                hostname=device_name,
                config_name="bgpcpp",
                patcher_name=f"update_peer_group_patcher_{peergroup_downlink_mimic_v6}",
                task_name="coop_register_patcher",
                patcher_args={
                    "name": peergroup_downlink_mimic_v6,
                    "attributes_to_update_json": json.dumps(
                        {
                            "disable_ipv4_afi": "True",
                            "v4_over_v6_nexthop": "False",
                            "is_passive": "False",
                            "max_routes": per_peer_max_route_limit,
                            "is_confed_peer": is_downlink_peer_confed,
                        }
                    ),
                },
                py_func_name="configure_bgp_peer_group",
            ),
            create_coop_register_patcher_task(
                hostname=device_name,
                config_name="bgpcpp",
                patcher_name=f"update_peer_group_patcher_{peergroup_uplink_mimic_v6}",
                task_name="coop_register_patcher",
                patcher_args={
                    "name": peergroup_uplink_mimic_v6,
                    "attributes_to_update_json": json.dumps(
                        {
                            "disable_ipv4_afi": "True",
                            "v4_over_v6_nexthop": "False",
                            "is_passive": "False",
                            "max_routes": per_peer_max_route_limit,
                            "is_confed_peer": is_uplink_peer_confed,
                        }
                    ),
                },
                py_func_name="configure_bgp_peer_group",
            ),
            create_coop_register_patcher_task(
                hostname=device_name,
                config_name="bgpcpp",
                patcher_name=f"add_peer_group_patcher_{peergroup_downlink_mimic_v4}",
                task_name="coop_register_patcher",
                patcher_args={
                    "name": peergroup_downlink_mimic_v4,
                    "description": "BGP peering from SSW to FSW, IPv4 sessions",
                    "next_hop_self": "True",
                    "disable_ipv4_afi": "False",
                    "disable_ipv6_afi": "True",
                    "is_confed_peer": is_downlink_peer_confed,
                    "ingress_policy_name": route_map_downlink_ingress,
                    "egress_policy_name": route_map_downlink_egress,
                    "bgp_peer_timers_hold_time_seconds": "30",
                    "bgp_peer_timers_keep_alive_seconds": "10",
                    "bgp_peer_timers_out_delay_seconds": "7",
                    "bgp_peer_timers_withdraw_unprog_delay_seconds": "0",
                    "peer_tag": downlink_peer_tag,
                    "max_routes": per_peer_max_route_limit,
                    "warning_only": "True",
                    "warning_limit": "0",
                    "link_bandwidth_bps": "auto",
                    "v4_over_v6_nexthop": "False",
                    "is_passive": "False",
                },
                py_func_name="add_peer_group_patcher",
            ),
            create_coop_register_patcher_task(
                hostname=device_name,
                config_name="bgpcpp",
                patcher_name=f"add_peer_group_patcher_{peergroup_uplink_mimic_v4}",
                task_name="coop_register_patcher",
                patcher_args={
                    "name": peergroup_uplink_mimic_v4,
                    "description": "BGP peering from FAUU to EB, IPV6 sessions",
                    "next_hop_self": "True",
                    "disable_ipv4_afi": "False",
                    "disable_ipv6_afi": "False",
                    "is_confed_peer": is_uplink_peer_confed,
                    "ingress_policy_name": route_map_uplink_ingress,
                    "egress_policy_name": route_map_uplink_egress,
                    "bgp_peer_timers_hold_time_seconds": "30",
                    "bgp_peer_timers_keep_alive_seconds": "10",
                    "bgp_peer_timers_out_delay_seconds": "7",
                    "bgp_peer_timers_withdraw_unprog_delay_seconds": "0",
                    "peer_tag": uplink_peer_tag,
                    "warning_only": "True",
                    "max_routes": per_peer_max_route_limit,
                    "warning_limit": "0",
                    "link_bandwidth_bps": "auto",
                    "v4_over_v6_nexthop": "true",
                    "is_passive": "False",
                    "receive_link_bandwidth": "1",
                },
                py_func_name="add_peer_group_patcher",
            ),
            create_coop_apply_patchers_task(
                hostnames=[device_name],
                config_name="bgpcpp",
            ),
            create_configure_parallel_bgp_peers_task(
                hostname=device_name,
                peer_configs=[
                    {
                        "configure_vlans_patcher_name": "configure_vlans_patcher_name_downlink",
                        "add_bgp_peers_patcher_name": "add_bgp_peers_patcher_name_downlink",
                        "config_json": json.dumps(
                            {
                                ixia_downlink_interface: [
                                    {
                                        "starting_ip": f"{ixia_downlink_ic_parent_network_v6}::10",
                                        "increment_ip": "0:0:0:0::2",
                                        "prefix_length": 127,
                                        "description": "Downlink IPv6 Peers",
                                        "peer_group_name": peergroup_downlink_mimic_v6,
                                        "num_sessions": downlink_peer_count,
                                        "remote_as_4_byte": remote_downlink_as_4byte,
                                        "remote_as_4_byte_step": remote_as_4_byte_step,
                                        "gateway_starting_ip": f"{ixia_downlink_ic_parent_network_v6}::11",
                                        "gateway_increment_ip": "0:0:0:0::2",
                                    },
                                    {
                                        "starting_ip": f"{ixia_downlink_ic_parent_network_v4}.0",
                                        "increment_ip": "0.0.0.2",
                                        "prefix_length": 31,
                                        "description": "Downlink IPv4 Peers",
                                        "peer_group_name": peergroup_downlink_mimic_v4,
                                        "num_sessions": downlink_peer_count,
                                        "remote_as_4_byte": remote_downlink_as_4byte,
                                        "remote_as_4_byte_step": remote_as_4_byte_step,
                                        "gateway_starting_ip": f"{ixia_downlink_ic_parent_network_v4}.1",
                                        "gateway_increment_ip": "0.0.0.2",
                                    },
                                ]
                            }
                        ),
                    }
                ],
            ),
            create_wait_for_agent_convergence_task(
                hostnames=[device_name],
            ),
            create_configure_parallel_bgp_peers_task(
                hostname=device_name,
                peer_configs=[
                    {
                        "configure_vlans_patcher_name": "configure_vlans_patcher_name_uplink",
                        "add_bgp_peers_patcher_name": "add_bgp_peers_patcher_name_uplink",
                        "config_json": json.dumps(
                            {
                                ixia_uplink_interface: [
                                    {
                                        "starting_ip": f"{ixia_uplink_ic_parent_network_v6}::10",
                                        "increment_ip": "0:0:0:0::2",
                                        "prefix_length": 127,
                                        "description": "Uplink IPv6 Peers",
                                        "peer_group_name": peergroup_uplink_mimic_v6,
                                        "num_sessions": uplink_peer_count,
                                        "remote_as_4_byte": remote_uplink_as_4byte,
                                        "remote_as_4_byte_step": remote_as_4_byte_step,
                                        "gateway_starting_ip": f"{ixia_uplink_ic_parent_network_v6}::11",
                                        "gateway_increment_ip": "0:0:0:0::2",
                                    },
                                    {
                                        "starting_ip": f"{ixia_uplink_ic_parent_network_v4}.0",
                                        "increment_ip": "0.0.0.2",
                                        "prefix_length": 31,
                                        "description": "Uplink IPv4 Peers",
                                        "peer_group_name": peergroup_uplink_mimic_v4,
                                        "num_sessions": uplink_peer_count,
                                        "remote_as_4_byte": remote_uplink_as_4byte,
                                        "remote_as_4_byte_step": remote_as_4_byte_step,
                                        "gateway_starting_ip": f"{ixia_uplink_ic_parent_network_v4}.1",
                                        "gateway_increment_ip": "0.0.0.2",
                                    },
                                ]
                            }
                        ),
                    }
                ],
            ),
            create_coop_apply_patchers_task(
                hostnames=[device_name],
            ),
        ],
        # Tasks to clean up after testing is complete
        teardown_tasks=[
            create_coop_unregister_patchers_task(device_name),
        ],
        # Configure IXIA ports for traffic generation
        basic_port_configs=[
            taac_types.BasicPortConfig(
                endpoint=f"{device_name}:{ixia_downlink_interface}",
                device_group_configs=[
                    taac_types.DeviceGroupConfig(
                        device_group_index=0,
                        multiplier=downlink_peer_count,
                        v6_addresses_config=taac_types.IpAddressesConfig(
                            starting_ip=f"{ixia_downlink_ic_parent_network_v6}::11",
                            increment_ip="0:0:0:0::2",
                            gateway_starting_ip=f"{ixia_downlink_ic_parent_network_v6}::10",
                            gateway_increment_ip="0:0:0:0::2",
                        ),
                        v6_bgp_config=taac_types.BgpConfig(
                            local_as_4_bytes=remote_downlink_as_4byte,
                            local_as_increment=1,
                            enable_4_byte_local_as=True,
                            is_confed=is_downlink_peer_confed == "True",
                            bgp_capabilities=[ixia_types.BgpCapability.IpV6Unicast],
                            route_scales=[
                                taac_types.RouteScaleSpec(
                                    network_group_index=0,
                                    v6_route_scale=taac_types.RouteScale(
                                        multiplier=1,
                                        prefix_count=ixia_downlink_prefix_count_v6,
                                        prefix_length=64,
                                        starting_prefixes="9000:1::",
                                        prefix_step="0:0:0:0::0",
                                        bgp_communities=ixia_downlink_communities,
                                        ip_address_family=ixia_types.IpAddressFamily.IPV6,
                                    ),
                                ),
                            ],
                        ),
                    ),
                    taac_types.DeviceGroupConfig(
                        device_group_index=1,
                        multiplier=downlink_peer_count,
                        v4_addresses_config=taac_types.IpAddressesConfig(
                            starting_ip=f"{ixia_downlink_ic_parent_network_v4}.1",
                            increment_ip="0.0.0.2",
                            gateway_starting_ip=f"{ixia_downlink_ic_parent_network_v4}.0",
                            gateway_increment_ip="0.0.0.2",
                            mask=31,
                        ),
                        v4_bgp_config=taac_types.BgpConfig(
                            local_as_4_bytes=remote_downlink_as_4byte,
                            local_as_increment=1,
                            enable_4_byte_local_as=True,
                            is_confed=is_downlink_peer_confed == "True",
                            bgp_capabilities=[ixia_types.BgpCapability.IpV4Unicast],
                            route_scales=[
                                taac_types.RouteScaleSpec(
                                    network_group_index=0,
                                    v4_route_scale=taac_types.RouteScale(
                                        multiplier=1,
                                        prefix_count=ixia_downlink_prefix_count_v4,
                                        prefix_length=24,
                                        starting_prefixes="101.1.0.0",
                                        prefix_step="0.0.0.0",
                                        bgp_communities=ixia_downlink_communities,
                                        ip_address_family=ixia_types.IpAddressFamily.IPV4,
                                    ),
                                ),
                            ],
                        ),
                    ),
                ],
            ),
            taac_types.BasicPortConfig(
                endpoint=f"{device_name}:{ixia_uplink_interface}",
                device_group_configs=[
                    taac_types.DeviceGroupConfig(
                        device_group_index=0,
                        multiplier=uplink_peer_count,
                        v6_addresses_config=taac_types.IpAddressesConfig(
                            starting_ip=f"{ixia_uplink_ic_parent_network_v6}::11",
                            increment_ip="0:0:0:0::2",
                            gateway_starting_ip=f"{ixia_uplink_ic_parent_network_v6}::10",
                            gateway_increment_ip="0:0:0:0::2",
                            mask=127,
                        ),
                        v6_bgp_config=taac_types.BgpConfig(
                            local_as_4_bytes=remote_uplink_as_4byte,
                            local_as_increment=1,
                            enable_4_byte_local_as=True,
                            is_confed=is_uplink_peer_confed == "True",
                            bgp_capabilities=[ixia_types.BgpCapability.IpV6Unicast],
                            route_scales=[
                                taac_types.RouteScaleSpec(
                                    network_group_index=0,
                                    v6_route_scale=taac_types.RouteScale(
                                        multiplier=1,
                                        prefix_count=ixia_uplink_prefix_count_v6,
                                        prefix_length=64,
                                        starting_prefixes="8000:1::",
                                        prefix_step="0:0:0:0::0",
                                        bgp_communities=ixia_uplink_communities,
                                        ip_address_family=ixia_types.IpAddressFamily.IPV6,
                                    ),
                                ),
                            ],
                        ),
                    ),
                    taac_types.DeviceGroupConfig(
                        device_group_index=1,
                        multiplier=uplink_peer_count,
                        v4_addresses_config=taac_types.IpAddressesConfig(
                            starting_ip=f"{ixia_uplink_ic_parent_network_v4}.1",
                            increment_ip="0.0.0.2",
                            gateway_starting_ip=f"{ixia_uplink_ic_parent_network_v4}.0",
                            gateway_increment_ip="0.0.0.2",
                            mask=31,
                        ),
                        v4_bgp_config=taac_types.BgpConfig(
                            local_as_4_bytes=remote_uplink_as_4byte,
                            local_as_increment=1,
                            enable_4_byte_local_as=True,
                            is_confed=is_uplink_peer_confed == "True",
                            bgp_capabilities=[ixia_types.BgpCapability.IpV4Unicast],
                            route_scales=[
                                taac_types.RouteScaleSpec(
                                    network_group_index=0,
                                    v4_route_scale=taac_types.RouteScale(
                                        multiplier=1,
                                        prefix_count=ixia_uplink_prefix_count_v4,
                                        prefix_length=24,
                                        starting_prefixes="201.1.0.0",
                                        prefix_step="0.0.0.0",
                                        bgp_communities=ixia_uplink_communities,
                                        ip_address_family=ixia_types.IpAddressFamily.IPV4,
                                    ),
                                ),
                            ],
                        ),
                    ),
                ],
            ),
        ],
        # Define traffic patterns between endpoints
        basic_traffic_item_configs=[
            taac_types.BasicTrafficItemConfig(
                name="V6_DIRECTIONAL_TRAFFIC_BETWEEN_DOWNLINK_AND_UPLINK",
                bidirectional=True,
                merge_destinations=True,
                line_rate=10,
                src_dest_mesh=ixia_types.SrcDestMeshType.MANY_TO_MANY,
                src_endpoints=[
                    taac_types.TrafficEndpoint(
                        name=f"{device_name}:{ixia_uplink_interface}",
                        network_group_index=0,
                        device_group_index=0,
                    )
                ],
                dest_endpoints=[
                    taac_types.TrafficEndpoint(
                        name=f"{device_name}:{ixia_downlink_interface}",
                        network_group_index=0,
                        device_group_index=0,
                    )
                ],
                traffic_type=ixia_types.TrafficType.IPV6,
                tracking_types=[ixia_types.TrafficStatsTrackingType.TRAFFIC_ITEM],
            ),
            taac_types.BasicTrafficItemConfig(
                name="V4_DIRECTIONAL_TRAFFIC_BETWEEN_DOWNLINK_AND_UPLINK",
                bidirectional=True,
                merge_destinations=True,
                line_rate=10,
                src_dest_mesh=ixia_types.SrcDestMeshType.MANY_TO_MANY,
                src_endpoints=[
                    taac_types.TrafficEndpoint(
                        name=f"{device_name}:{ixia_uplink_interface}",
                        network_group_index=0,
                        device_group_index=1,
                    )
                ],
                dest_endpoints=[
                    taac_types.TrafficEndpoint(
                        name=f"{device_name}:{ixia_downlink_interface}",
                        network_group_index=0,
                        device_group_index=1,
                    )
                ],
                traffic_type=ixia_types.TrafficType.IPV4,
                tracking_types=[ixia_types.TrafficStatsTrackingType.TRAFFIC_ITEM],
            ),
            taac_types.BasicTrafficItemConfig(
                src_endpoints=[
                    taac_types.TrafficEndpoint(
                        name=f"{device_name}:{ixia_uplink_interface}",
                        network_group_index=0,
                        device_group_index=0,
                    )
                ],
                dest_endpoints=[
                    taac_types.TrafficEndpoint(
                        name=f"{device_name}:{ixia_downlink_interface}",
                        network_group_index=0,
                        device_group_index=0,
                    )
                ],
                name="TEST_RAW_BGP_CP_TRAFFIC",
                line_rate_type=ixia_types.RateType.FRAMES_PER_SECOND,
                line_rate=2000,
                traffic_type=ixia_types.TrafficType.RAW,
                bidirectional=False,
                packet_headers=BGP_CP_TRAFFIC_PACKET_HEADERS,
            ),
            # BGP v4 CP traffic (DSCP 48) - punted to HIGH queue
            taac_types.BasicTrafficItemConfig(
                src_endpoints=[
                    taac_types.TrafficEndpoint(
                        name=f"{device_name}:{ixia_uplink_interface}",
                        network_group_index=0,
                        device_group_index=1,
                    )
                ],
                dest_endpoints=[
                    taac_types.TrafficEndpoint(
                        name=f"{device_name}:{ixia_downlink_interface}",
                        network_group_index=0,
                        device_group_index=1,
                    )
                ],
                name="TEST_RAW_BGP_CP_V4_TRAFFIC",
                line_rate_type=ixia_types.RateType.FRAMES_PER_SECOND,
                line_rate=2000,
                traffic_type=ixia_types.TrafficType.RAW,
                bidirectional=False,
                packet_headers=BGP_CP_V4_TRAFFIC_PACKET_HEADERS,
            ),
            # BGP v4 CP traffic (DSCP 0) - punted to HIGH queue
            taac_types.BasicTrafficItemConfig(
                src_endpoints=[
                    taac_types.TrafficEndpoint(
                        name=f"{device_name}:{ixia_uplink_interface}",
                        network_group_index=0,
                        device_group_index=1,
                    )
                ],
                dest_endpoints=[
                    taac_types.TrafficEndpoint(
                        name=f"{device_name}:{ixia_downlink_interface}",
                        network_group_index=0,
                        device_group_index=1,
                    )
                ],
                name="TEST_RAW_BGP_CP_V4_DSCP0_TRAFFIC",
                line_rate_type=ixia_types.RateType.FRAMES_PER_SECOND,
                line_rate=2000,
                traffic_type=ixia_types.TrafficType.RAW,
                bidirectional=False,
                packet_headers=BGP_CP_V4_DSCP0_TRAFFIC_PACKET_HEADERS,
            ),
            taac_types.BasicTrafficItemConfig(
                src_endpoints=[
                    taac_types.TrafficEndpoint(
                        name=f"{device_name}:{ixia_uplink_interface}",
                        network_group_index=0,
                        device_group_index=0,
                    )
                ],
                dest_endpoints=[
                    taac_types.TrafficEndpoint(
                        name=f"{device_name}:{ixia_downlink_interface}",
                        network_group_index=0,
                        device_group_index=0,
                    )
                ],
                name="TEST_RAW_LLDP_TRAFFIC",
                line_rate_type=ixia_types.RateType.FRAMES_PER_SECOND,
                line_rate=2000,
                traffic_type=ixia_types.TrafficType.RAW,
                bidirectional=False,
                packet_headers=LLDP_TRAFFIC_PACKET_HEADERS,
            ),
            taac_types.BasicTrafficItemConfig(
                name="BGP_PREFIX_TRAFFIC",
                bidirectional=False,
                merge_destinations=True,
                line_rate=10,
                src_dest_mesh=ixia_types.SrcDestMeshType.MANY_TO_MANY,
                src_endpoints=[
                    taac_types.TrafficEndpoint(
                        name=f"{device_name}:{ixia_uplink_interface}",
                        network_group_index=0,
                        device_group_index=0,
                    )
                ],
                dest_endpoints=[
                    taac_types.TrafficEndpoint(
                        name=f"{device_name}:{ixia_downlink_interface}",
                        network_group_index=0,
                        device_group_index=0,
                    )
                ],
                traffic_type=ixia_types.TrafficType.IPV6,
                frame_size_settings=ixia_types.FrameSize(
                    type=ixia_types.FrameSizeType.CUSTOM_IMIX
                ),
            ),
            # IPv4 BGP prefix data plane traffic (background for v4 CP tests)
            taac_types.BasicTrafficItemConfig(
                name="BGP_PREFIX_TRAFFIC_V4",
                bidirectional=False,
                merge_destinations=True,
                line_rate=10,
                src_dest_mesh=ixia_types.SrcDestMeshType.MANY_TO_MANY,
                src_endpoints=[
                    taac_types.TrafficEndpoint(
                        name=f"{device_name}:{ixia_uplink_interface}",
                        network_group_index=0,
                        device_group_index=1,
                    )
                ],
                dest_endpoints=[
                    taac_types.TrafficEndpoint(
                        name=f"{device_name}:{ixia_downlink_interface}",
                        network_group_index=0,
                        device_group_index=1,
                    )
                ],
                traffic_type=ixia_types.TrafficType.IPV4,
                frame_size_settings=ixia_types.FrameSize(
                    type=ixia_types.FrameSizeType.CUSTOM_IMIX
                ),
            ),
            taac_types.BasicTrafficItemConfig(
                name="IPV6_TRAFFIC",
                bidirectional=False,
                merge_destinations=True,
                line_rate=10,
                src_dest_mesh=ixia_types.SrcDestMeshType.MANY_TO_MANY,
                src_endpoints=[
                    taac_types.TrafficEndpoint(
                        name=f"{device_name}:{ixia_uplink_interface}",
                        network_group_index=0,
                        device_group_index=0,
                    )
                ],
                dest_endpoints=[
                    taac_types.TrafficEndpoint(
                        name=f"{device_name}:{ixia_downlink_interface}",
                        network_group_index=0,
                        device_group_index=0,
                    )
                ],
                traffic_type=ixia_types.TrafficType.IPV6,
                frame_size_settings=ixia_types.FrameSize(
                    type=ixia_types.FrameSizeType.CUSTOM_IMIX
                ),
            ),
            taac_types.BasicTrafficItemConfig(
                src_endpoints=[
                    taac_types.TrafficEndpoint(
                        name=f"{device_name}:{ixia_uplink_interface}",
                        device_group_index=0,
                    ),
                ],
                dest_endpoints=[
                    taac_types.TrafficEndpoint(
                        name=f"{device_name}:{ixia_downlink_interface}",
                        device_group_index=0,
                    ),
                ],
                name="TEST_RAW_DHCP_V6_TRAFFIC",
                line_rate_type=ixia_types.RateType.FRAMES_PER_SECOND,
                line_rate=2000,
                traffic_type=ixia_types.TrafficType.RAW,
                bidirectional=False,
                packet_headers=DHCP_V6_TRAFFIC_PACKET_HEADERS,
            ),
            taac_types.BasicTrafficItemConfig(
                src_endpoints=[
                    taac_types.TrafficEndpoint(
                        name=f"{device_name}:{ixia_uplink_interface}",
                        device_group_index=1,
                    ),
                ],
                dest_endpoints=[
                    taac_types.TrafficEndpoint(
                        name=f"{device_name}:{ixia_downlink_interface}",
                        device_group_index=1,
                    ),
                ],
                name="TEST_RAW_DHCP_V4_DISCOVER_TRAFFIC",
                line_rate_type=ixia_types.RateType.FRAMES_PER_SECOND,
                line_rate=2000,
                traffic_type=ixia_types.TrafficType.RAW,
                bidirectional=False,
                packet_headers=DHCP_V4_DISCOVER_TRAFFIC_PACKET_HEADERS,
            ),
            taac_types.BasicTrafficItemConfig(
                src_endpoints=[
                    taac_types.TrafficEndpoint(
                        name=f"{device_name}:{ixia_uplink_interface}",
                        device_group_index=1,
                    ),
                ],
                dest_endpoints=[
                    taac_types.TrafficEndpoint(
                        name=f"{device_name}:{ixia_downlink_interface}",
                        device_group_index=1,
                    ),
                ],
                name="TEST_RAW_DHCP_V4_DISCOVER_TO_SERVER_TRAFFIC",
                line_rate_type=ixia_types.RateType.FRAMES_PER_SECOND,
                line_rate=2000,
                traffic_type=ixia_types.TrafficType.RAW,
                bidirectional=False,
                packet_headers=DHCP_V4_DISCOVER_TO_SERVER_TRAFFIC_PACKET_HEADERS,
            ),
            taac_types.BasicTrafficItemConfig(
                src_endpoints=[
                    taac_types.TrafficEndpoint(
                        name=f"{device_name}:{ixia_uplink_interface}",
                        device_group_index=0,
                    ),
                ],
                dest_endpoints=[
                    taac_types.TrafficEndpoint(
                        name=f"{device_name}:{ixia_downlink_interface}",
                        device_group_index=0,
                    ),
                ],
                name="TEST_RAW_ARP_REQUEST_TRAFFIC",
                line_rate_type=ixia_types.RateType.FRAMES_PER_SECOND,
                line_rate=2000,
                traffic_type=ixia_types.TrafficType.RAW,
                bidirectional=False,
                packet_headers=ARP_REQUEST_TRAFFIC_PACKET_HEADERS,
            ),
            taac_types.BasicTrafficItemConfig(
                src_endpoints=[
                    taac_types.TrafficEndpoint(
                        name=f"{device_name}:{ixia_uplink_interface}",
                        device_group_index=0,
                    ),
                ],
                dest_endpoints=[
                    taac_types.TrafficEndpoint(
                        name=f"{device_name}:{ixia_downlink_interface}",
                        device_group_index=0,
                    ),
                ],
                name="TEST_RAW_ARP_RESPONSE_TRAFFIC",
                line_rate_type=ixia_types.RateType.FRAMES_PER_SECOND,
                line_rate=2000,
                traffic_type=ixia_types.TrafficType.RAW,
                bidirectional=False,
                packet_headers=ARP_RESPONSE_TRAFFIC_PACKET_HEADERS,
            ),
            taac_types.BasicTrafficItemConfig(
                src_endpoints=[
                    taac_types.TrafficEndpoint(
                        name=f"{device_name}:{ixia_uplink_interface}",
                        device_group_index=0,
                    ),
                ],
                dest_endpoints=[
                    taac_types.TrafficEndpoint(
                        name=f"{device_name}:{ixia_downlink_interface}",
                        device_group_index=0,
                    ),
                ],
                name="TEST_RAW_ICMP_V6_REQUEST_TRAFFIC",
                line_rate_type=ixia_types.RateType.FRAMES_PER_SECOND,
                line_rate=2000,
                traffic_type=ixia_types.TrafficType.RAW,
                bidirectional=False,
                packet_headers=ICMP_V6_REQUEST_TRAFFIC_PACKET_HEADERS,
            ),
            taac_types.BasicTrafficItemConfig(
                src_endpoints=[
                    taac_types.TrafficEndpoint(
                        name=f"{device_name}:{ixia_uplink_interface}",
                        device_group_index=0,
                    ),
                ],
                dest_endpoints=[
                    taac_types.TrafficEndpoint(
                        name=f"{device_name}:{ixia_downlink_interface}",
                        device_group_index=0,
                    ),
                ],
                name="TEST_RAW_ICMP_V4_ECHO_REQUEST_TRAFFIC",
                line_rate_type=ixia_types.RateType.FRAMES_PER_SECOND,
                line_rate=2000,
                traffic_type=ixia_types.TrafficType.RAW,
                bidirectional=False,
                packet_headers=ICMP_V4_ECHO_REQUEST_TRAFFIC_PACKET_HEADERS,
            ),
            taac_types.BasicTrafficItemConfig(
                src_endpoints=[
                    taac_types.TrafficEndpoint(
                        name=f"{device_name}:{ixia_uplink_interface}",
                        device_group_index=0,
                    ),
                ],
                dest_endpoints=[
                    taac_types.TrafficEndpoint(
                        name=f"{device_name}:{ixia_downlink_interface}",
                        device_group_index=0,
                    ),
                ],
                name="TEST_RAW_ICMP_V4_ECHO_REPLY_TRAFFIC",
                line_rate_type=ixia_types.RateType.FRAMES_PER_SECOND,
                line_rate=2000,
                traffic_type=ixia_types.TrafficType.RAW,
                bidirectional=False,
                packet_headers=ICMP_V4_ECHO_REPLY_TRAFFIC_PACKET_HEADERS,
            ),
            taac_types.BasicTrafficItemConfig(
                src_endpoints=[
                    taac_types.TrafficEndpoint(
                        name=f"{device_name}:{ixia_uplink_interface}",
                        device_group_index=0,
                    ),
                ],
                dest_endpoints=[
                    taac_types.TrafficEndpoint(
                        name=f"{device_name}:{ixia_downlink_interface}",
                        device_group_index=0,
                    ),
                ],
                name="TEST_RAW_ICMP_V4_DEST_UNREACHABLE_TRAFFIC",
                line_rate_type=ixia_types.RateType.FRAMES_PER_SECOND,
                line_rate=2000,
                traffic_type=ixia_types.TrafficType.RAW,
                bidirectional=False,
                packet_headers=ICMP_V4_DEST_UNREACHABLE_TRAFFIC_PACKET_HEADERS,
            ),
            taac_types.BasicTrafficItemConfig(
                src_endpoints=[
                    taac_types.TrafficEndpoint(
                        name=f"{device_name}:{ixia_uplink_interface}",
                        device_group_index=0,
                    ),
                ],
                dest_endpoints=[
                    taac_types.TrafficEndpoint(
                        name=f"{device_name}:{ixia_downlink_interface}",
                        device_group_index=0,
                    ),
                ],
                name="TEST_RAW_ICMP_V4_TIME_EXCEEDED_TRAFFIC",
                line_rate_type=ixia_types.RateType.FRAMES_PER_SECOND,
                line_rate=2000,
                traffic_type=ixia_types.TrafficType.RAW,
                bidirectional=False,
                packet_headers=ICMP_V4_TIME_EXCEEDED_TRAFFIC_PACKET_HEADERS,
            ),
            taac_types.BasicTrafficItemConfig(
                src_endpoints=[
                    taac_types.TrafficEndpoint(
                        name=f"{device_name}:{ixia_uplink_interface}",
                        device_group_index=0,
                    ),
                ],
                dest_endpoints=[
                    taac_types.TrafficEndpoint(
                        name=f"{device_name}:{ixia_downlink_interface}",
                        device_group_index=0,
                    ),
                ],
                name="TEST_NEXTHOP_LIMIT_1_IPV6_TRAFFIC",
                line_rate_type=ixia_types.RateType.FRAMES_PER_SECOND,
                line_rate=2000,
                traffic_type=ixia_types.TrafficType.RAW,
                bidirectional=False,
                packet_headers=HOP_LIMIT_1_IPV6_TRAFFIC_PACKET_HEADERS,
            ),
            taac_types.BasicTrafficItemConfig(
                src_endpoints=[
                    taac_types.TrafficEndpoint(
                        name=f"{device_name}:{ixia_uplink_interface}",
                        device_group_index=0,
                    ),
                ],
                dest_endpoints=[
                    taac_types.TrafficEndpoint(
                        name=f"{device_name}:{ixia_downlink_interface}",
                        device_group_index=0,
                    ),
                ],
                name="TEST_NEXTHOP_LIMIT_0_IPV6_TRAFFIC",
                line_rate_type=ixia_types.RateType.FRAMES_PER_SECOND,
                line_rate=2000,
                traffic_type=ixia_types.TrafficType.RAW,
                bidirectional=False,
                packet_headers=HOP_LIMIT_0_IPV6_TRAFFIC_PACKET_HEADERS,
            ),
            taac_types.BasicTrafficItemConfig(
                src_endpoints=[
                    taac_types.TrafficEndpoint(
                        name=f"{device_name}:{ixia_uplink_interface}",
                        device_group_index=1,
                    ),
                ],
                dest_endpoints=[
                    taac_types.TrafficEndpoint(
                        name=f"{device_name}:{ixia_downlink_interface}",
                        device_group_index=1,
                    ),
                ],
                name="TEST_TTL_1_IPV4_TRAFFIC",
                line_rate_type=ixia_types.RateType.FRAMES_PER_SECOND,
                line_rate=2000,
                traffic_type=ixia_types.TrafficType.RAW,
                bidirectional=False,
                packet_headers=TTL_1_IPV4_TRAFFIC_PACKET_HEADERS,
            ),
            taac_types.BasicTrafficItemConfig(
                src_endpoints=[
                    taac_types.TrafficEndpoint(
                        name=f"{device_name}:{ixia_uplink_interface}",
                        device_group_index=1,
                    ),
                ],
                dest_endpoints=[
                    taac_types.TrafficEndpoint(
                        name=f"{device_name}:{ixia_downlink_interface}",
                        device_group_index=1,
                    ),
                ],
                name="TEST_TTL_0_IPV4_TRAFFIC",
                line_rate_type=ixia_types.RateType.FRAMES_PER_SECOND,
                line_rate=2000,
                traffic_type=ixia_types.TrafficType.RAW,
                bidirectional=False,
                packet_headers=TTL_0_IPV4_TRAFFIC_PACKET_HEADERS,
            ),
            taac_types.BasicTrafficItemConfig(
                src_endpoints=[
                    taac_types.TrafficEndpoint(
                        name=f"{device_name}:{ixia_uplink_interface}",
                        device_group_index=0,
                    ),
                ],
                dest_endpoints=[
                    taac_types.TrafficEndpoint(
                        name=f"{device_name}:{ixia_downlink_interface}",
                        device_group_index=0,
                    ),
                ],
                name="TEST_LACP_SLOW_TIMER_TRAFFIC",
                line_rate_type=ixia_types.RateType.FRAMES_PER_SECOND,
                line_rate=2000,
                traffic_type=ixia_types.TrafficType.RAW,
                bidirectional=False,
                packet_headers=LACP_SLOW_TIMER_TRAFFIC_PACKET_HEADERS,
            ),
            taac_types.BasicTrafficItemConfig(
                src_endpoints=[
                    taac_types.TrafficEndpoint(
                        name=f"{device_name}:{ixia_uplink_interface}",
                        device_group_index=0,
                    ),
                ],
                dest_endpoints=[
                    taac_types.TrafficEndpoint(
                        name=f"{device_name}:{ixia_downlink_interface}",
                        device_group_index=0,
                    ),
                ],
                name="TEST_NDP_NS_MULTICAST_TRAFFIC",
                line_rate_type=ixia_types.RateType.FRAMES_PER_SECOND,
                line_rate=2000,
                traffic_type=ixia_types.TrafficType.RAW,
                bidirectional=False,
                packet_headers=NDP_NS_MULTICAST_TRAFFIC_PACKET_HEADERS,
            ),
            taac_types.BasicTrafficItemConfig(
                src_endpoints=[
                    taac_types.TrafficEndpoint(
                        name=f"{device_name}:{ixia_uplink_interface}",
                        device_group_index=0,
                    ),
                ],
                dest_endpoints=[
                    taac_types.TrafficEndpoint(
                        name=f"{device_name}:{ixia_downlink_interface}",
                        device_group_index=0,
                    ),
                ],
                name="TEST_NDP_NA_MULTICAST_TRAFFIC",
                line_rate_type=ixia_types.RateType.FRAMES_PER_SECOND,
                line_rate=2000,
                traffic_type=ixia_types.TrafficType.RAW,
                bidirectional=False,
                packet_headers=NDP_NA_MULTICAST_TRAFFIC_PACKET_HEADERS,
            ),
            taac_types.BasicTrafficItemConfig(
                src_endpoints=[
                    taac_types.TrafficEndpoint(
                        name=f"{device_name}:{ixia_uplink_interface}",
                        device_group_index=0,
                    ),
                ],
                dest_endpoints=[
                    taac_types.TrafficEndpoint(
                        name=f"{device_name}:{ixia_downlink_interface}",
                        device_group_index=0,
                    ),
                ],
                name="TEST_NDP_RS_MULTICAST_TRAFFIC",
                line_rate_type=ixia_types.RateType.FRAMES_PER_SECOND,
                line_rate=2000,
                traffic_type=ixia_types.TrafficType.RAW,
                bidirectional=False,
                packet_headers=NDP_RS_MULTICAST_TRAFFIC_PACKET_HEADERS,
            ),
            taac_types.BasicTrafficItemConfig(
                src_endpoints=[
                    taac_types.TrafficEndpoint(
                        name=f"{device_name}:{ixia_uplink_interface}",
                        device_group_index=0,
                    ),
                ],
                dest_endpoints=[
                    taac_types.TrafficEndpoint(
                        name=f"{device_name}:{ixia_downlink_interface}",
                        device_group_index=0,
                    ),
                ],
                name="TEST_NDP_RA_MULTICAST_TRAFFIC",
                line_rate_type=ixia_types.RateType.FRAMES_PER_SECOND,
                line_rate=2000,
                traffic_type=ixia_types.TrafficType.RAW,
                bidirectional=False,
                packet_headers=NDP_RA_MULTICAST_TRAFFIC_PACKET_HEADERS,
            ),
            taac_types.BasicTrafficItemConfig(
                src_endpoints=[
                    taac_types.TrafficEndpoint(
                        name=f"{device_name}:{ixia_uplink_interface}",
                        device_group_index=0,
                    ),
                ],
                dest_endpoints=[
                    taac_types.TrafficEndpoint(
                        name=f"{device_name}:{ixia_downlink_interface}",
                        device_group_index=0,
                    ),
                ],
                name="TEST_NDP_NS_UNICAST_TRAFFIC",
                line_rate_type=ixia_types.RateType.FRAMES_PER_SECOND,
                line_rate=2000,
                traffic_type=ixia_types.TrafficType.RAW,
                bidirectional=False,
                packet_headers=NDP_NS_UNICAST_TRAFFIC_PACKET_HEADERS,
            ),
            taac_types.BasicTrafficItemConfig(
                src_endpoints=[
                    taac_types.TrafficEndpoint(
                        name=f"{device_name}:{ixia_uplink_interface}",
                        device_group_index=0,
                    ),
                ],
                dest_endpoints=[
                    taac_types.TrafficEndpoint(
                        name=f"{device_name}:{ixia_downlink_interface}",
                        device_group_index=0,
                    ),
                ],
                name="TEST_NDP_NA_UNICAST_TRAFFIC",
                line_rate_type=ixia_types.RateType.FRAMES_PER_SECOND,
                line_rate=2000,
                traffic_type=ixia_types.TrafficType.RAW,
                bidirectional=False,
                packet_headers=NDP_NA_UNICAST_TRAFFIC_PACKET_HEADERS,
            ),
            taac_types.BasicTrafficItemConfig(
                src_endpoints=[
                    taac_types.TrafficEndpoint(
                        name=f"{device_name}:{ixia_uplink_interface}",
                        device_group_index=0,
                    ),
                ],
                dest_endpoints=[
                    taac_types.TrafficEndpoint(
                        name=f"{device_name}:{ixia_downlink_interface}",
                        device_group_index=0,
                    ),
                ],
                name="TEST_NDP_RS_UNICAST_TRAFFIC",
                line_rate_type=ixia_types.RateType.FRAMES_PER_SECOND,
                line_rate=2000,
                traffic_type=ixia_types.TrafficType.RAW,
                bidirectional=False,
                packet_headers=NDP_RS_UNICAST_TRAFFIC_PACKET_HEADERS,
            ),
            taac_types.BasicTrafficItemConfig(
                src_endpoints=[
                    taac_types.TrafficEndpoint(
                        name=f"{device_name}:{ixia_uplink_interface}",
                        device_group_index=0,
                    ),
                ],
                dest_endpoints=[
                    taac_types.TrafficEndpoint(
                        name=f"{device_name}:{ixia_downlink_interface}",
                        device_group_index=0,
                    ),
                ],
                name="TEST_NDP_RA_UNICAST_TRAFFIC",
                line_rate_type=ixia_types.RateType.FRAMES_PER_SECOND,
                line_rate=2000,
                traffic_type=ixia_types.TrafficType.RAW,
                bidirectional=False,
                packet_headers=NDP_RA_UNICAST_TRAFFIC_PACKET_HEADERS,
            ),
            # ICMPv6 Non-NDP with Link-Local Addresses
            taac_types.BasicTrafficItemConfig(
                src_endpoints=[
                    taac_types.TrafficEndpoint(
                        name=f"{device_name}:{ixia_uplink_interface}",
                        device_group_index=0,
                    ),
                ],
                dest_endpoints=[
                    taac_types.TrafficEndpoint(
                        name=f"{device_name}:{ixia_downlink_interface}",
                        device_group_index=0,
                    ),
                ],
                name="TEST_ICMPV6_ECHO_REQUEST_LINK_LOCAL_TRAFFIC",
                line_rate_type=ixia_types.RateType.FRAMES_PER_SECOND,
                line_rate=2000,
                traffic_type=ixia_types.TrafficType.RAW,
                bidirectional=False,
                packet_headers=ICMP_V6_ECHO_REQUEST_LINK_LOCAL_TRAFFIC_PACKET_HEADERS,
            ),
            taac_types.BasicTrafficItemConfig(
                src_endpoints=[
                    taac_types.TrafficEndpoint(
                        name=f"{device_name}:{ixia_uplink_interface}",
                        device_group_index=0,
                    ),
                ],
                dest_endpoints=[
                    taac_types.TrafficEndpoint(
                        name=f"{device_name}:{ixia_downlink_interface}",
                        device_group_index=0,
                    ),
                ],
                name="TEST_ICMPV6_ECHO_REPLY_LINK_LOCAL_TRAFFIC",
                line_rate_type=ixia_types.RateType.FRAMES_PER_SECOND,
                line_rate=2000,
                traffic_type=ixia_types.TrafficType.RAW,
                bidirectional=False,
                packet_headers=ICMP_V6_ECHO_REPLY_LINK_LOCAL_TRAFFIC_PACKET_HEADERS,
            ),
            taac_types.BasicTrafficItemConfig(
                src_endpoints=[
                    taac_types.TrafficEndpoint(
                        name=f"{device_name}:{ixia_uplink_interface}",
                        device_group_index=0,
                    ),
                ],
                dest_endpoints=[
                    taac_types.TrafficEndpoint(
                        name=f"{device_name}:{ixia_downlink_interface}",
                        device_group_index=0,
                    ),
                ],
                name="TEST_ICMPV6_DEST_UNREACHABLE_LINK_LOCAL_TRAFFIC",
                line_rate_type=ixia_types.RateType.FRAMES_PER_SECOND,
                line_rate=2000,
                traffic_type=ixia_types.TrafficType.RAW,
                bidirectional=False,
                packet_headers=ICMP_V6_DEST_UNREACHABLE_LINK_LOCAL_TRAFFIC_PACKET_HEADERS,
            ),
            taac_types.BasicTrafficItemConfig(
                src_endpoints=[
                    taac_types.TrafficEndpoint(
                        name=f"{device_name}:{ixia_uplink_interface}",
                        device_group_index=0,
                    ),
                ],
                dest_endpoints=[
                    taac_types.TrafficEndpoint(
                        name=f"{device_name}:{ixia_downlink_interface}",
                        device_group_index=0,
                    ),
                ],
                name="TEST_ICMPV6_PACKET_TOO_BIG_LINK_LOCAL_TRAFFIC",
                line_rate_type=ixia_types.RateType.FRAMES_PER_SECOND,
                line_rate=2000,
                traffic_type=ixia_types.TrafficType.RAW,
                bidirectional=False,
                packet_headers=ICMP_V6_PACKET_TOO_BIG_LINK_LOCAL_TRAFFIC_PACKET_HEADERS,
            ),
            taac_types.BasicTrafficItemConfig(
                src_endpoints=[
                    taac_types.TrafficEndpoint(
                        name=f"{device_name}:{ixia_uplink_interface}",
                        device_group_index=0,
                    ),
                ],
                dest_endpoints=[
                    taac_types.TrafficEndpoint(
                        name=f"{device_name}:{ixia_downlink_interface}",
                        device_group_index=0,
                    ),
                ],
                name="TEST_ICMPV6_TIME_EXCEEDED_LINK_LOCAL_TRAFFIC",
                line_rate_type=ixia_types.RateType.FRAMES_PER_SECOND,
                line_rate=2000,
                traffic_type=ixia_types.TrafficType.RAW,
                bidirectional=False,
                packet_headers=ICMP_V6_TIME_EXCEEDED_LINK_LOCAL_TRAFFIC_PACKET_HEADERS,
            ),
            # ICMPv6 Non-NDP with Global Addresses and DSCP 48
            taac_types.BasicTrafficItemConfig(
                src_endpoints=[
                    taac_types.TrafficEndpoint(
                        name=f"{device_name}:{ixia_uplink_interface}",
                        device_group_index=0,
                    ),
                ],
                dest_endpoints=[
                    taac_types.TrafficEndpoint(
                        name=f"{device_name}:{ixia_downlink_interface}",
                        device_group_index=0,
                    ),
                ],
                name="TEST_ICMPV6_ECHO_REQUEST_GLOBAL_DSCP48_TRAFFIC",
                line_rate_type=ixia_types.RateType.FRAMES_PER_SECOND,
                line_rate=2000,
                traffic_type=ixia_types.TrafficType.RAW,
                bidirectional=False,
                packet_headers=ICMP_V6_ECHO_REQUEST_GLOBAL_DSCP48_TRAFFIC_PACKET_HEADERS,
            ),
            taac_types.BasicTrafficItemConfig(
                src_endpoints=[
                    taac_types.TrafficEndpoint(
                        name=f"{device_name}:{ixia_uplink_interface}",
                        device_group_index=0,
                    ),
                ],
                dest_endpoints=[
                    taac_types.TrafficEndpoint(
                        name=f"{device_name}:{ixia_downlink_interface}",
                        device_group_index=0,
                    ),
                ],
                name="TEST_ICMPV6_ECHO_REPLY_GLOBAL_DSCP48_TRAFFIC",
                line_rate_type=ixia_types.RateType.FRAMES_PER_SECOND,
                line_rate=2000,
                traffic_type=ixia_types.TrafficType.RAW,
                bidirectional=False,
                packet_headers=ICMP_V6_ECHO_REPLY_GLOBAL_DSCP48_TRAFFIC_PACKET_HEADERS,
            ),
            taac_types.BasicTrafficItemConfig(
                src_endpoints=[
                    taac_types.TrafficEndpoint(
                        name=f"{device_name}:{ixia_uplink_interface}",
                        device_group_index=0,
                    ),
                ],
                dest_endpoints=[
                    taac_types.TrafficEndpoint(
                        name=f"{device_name}:{ixia_downlink_interface}",
                        device_group_index=0,
                    ),
                ],
                name="TEST_ICMPV6_DEST_UNREACHABLE_GLOBAL_DSCP48_TRAFFIC",
                line_rate_type=ixia_types.RateType.FRAMES_PER_SECOND,
                line_rate=2000,
                traffic_type=ixia_types.TrafficType.RAW,
                bidirectional=False,
                packet_headers=ICMP_V6_DEST_UNREACHABLE_GLOBAL_DSCP48_TRAFFIC_PACKET_HEADERS,
            ),
            taac_types.BasicTrafficItemConfig(
                src_endpoints=[
                    taac_types.TrafficEndpoint(
                        name=f"{device_name}:{ixia_uplink_interface}",
                        device_group_index=0,
                    ),
                ],
                dest_endpoints=[
                    taac_types.TrafficEndpoint(
                        name=f"{device_name}:{ixia_downlink_interface}",
                        device_group_index=0,
                    ),
                ],
                name="TEST_ICMPV6_PACKET_TOO_BIG_GLOBAL_DSCP48_TRAFFIC",
                line_rate_type=ixia_types.RateType.FRAMES_PER_SECOND,
                line_rate=2000,
                traffic_type=ixia_types.TrafficType.RAW,
                bidirectional=False,
                packet_headers=ICMP_V6_PACKET_TOO_BIG_GLOBAL_DSCP48_TRAFFIC_PACKET_HEADERS,
            ),
            taac_types.BasicTrafficItemConfig(
                src_endpoints=[
                    taac_types.TrafficEndpoint(
                        name=f"{device_name}:{ixia_uplink_interface}",
                        device_group_index=0,
                    ),
                ],
                dest_endpoints=[
                    taac_types.TrafficEndpoint(
                        name=f"{device_name}:{ixia_downlink_interface}",
                        device_group_index=0,
                    ),
                ],
                name="TEST_ICMPV6_TIME_EXCEEDED_GLOBAL_DSCP48_TRAFFIC",
                line_rate_type=ixia_types.RateType.FRAMES_PER_SECOND,
                line_rate=2000,
                traffic_type=ixia_types.TrafficType.RAW,
                bidirectional=False,
                packet_headers=ICMP_V6_TIME_EXCEEDED_GLOBAL_DSCP48_TRAFFIC_PACKET_HEADERS,
            ),
            # Burst traffic item for queue prioritization testing
            # High rate traffic to LOW queue (TTL=1 IPv4) to create drops
            taac_types.BasicTrafficItemConfig(
                src_endpoints=[
                    taac_types.TrafficEndpoint(
                        name=f"{device_name}:{ixia_uplink_interface}",
                        device_group_index=1,
                    ),
                ],
                dest_endpoints=[
                    taac_types.TrafficEndpoint(
                        name=f"{device_name}:{ixia_downlink_interface}",
                        device_group_index=1,
                    ),
                ],
                name="BURST_LOW_QUEUE_TTL1_TRAFFIC",
                line_rate_type=ixia_types.RateType.FRAMES_PER_SECOND,
                line_rate=100000,
                traffic_type=ixia_types.TrafficType.RAW,
                bidirectional=False,
                packet_headers=TTL_1_IPV4_TRAFFIC_PACKET_HEADERS,
            ),
            # High rate traffic to MID queue (DHCPv6) to create drops
            taac_types.BasicTrafficItemConfig(
                src_endpoints=[
                    taac_types.TrafficEndpoint(
                        name=f"{device_name}:{ixia_uplink_interface}",
                        device_group_index=0,
                    ),
                ],
                dest_endpoints=[
                    taac_types.TrafficEndpoint(
                        name=f"{device_name}:{ixia_downlink_interface}",
                        device_group_index=0,
                    ),
                ],
                name="BURST_MID_QUEUE_DHCPV6_TRAFFIC",
                line_rate_type=ixia_types.RateType.FRAMES_PER_SECOND,
                line_rate=100000,
                traffic_type=ixia_types.TrafficType.RAW,
                bidirectional=False,
                packet_headers=DHCP_V6_TRAFFIC_PACKET_HEADERS,
            ),
            # UNH (Unreachable Next Hop) traffic items — RAW IPv6 destined
            # to the prefix that register_cpu_queue_static_route_patcher
            # installs as a static route. Keeps frames sourcing into the
            # switch after the downlink BGP session drops (which stops
            # BGP_PREFIX_TRAFFIC / IPV6_TRAFFIC), so the
            # test_fboss_cpu_*_unh playbooks can observe punts on the CPU
            # low queue during the disable→enable window.
            taac_types.BasicTrafficItemConfig(
                src_endpoints=[
                    taac_types.TrafficEndpoint(
                        name=f"{device_name}:{ixia_uplink_interface}",
                        device_group_index=0,
                    ),
                ],
                dest_endpoints=[
                    taac_types.TrafficEndpoint(
                        name=f"{device_name}:{ixia_downlink_interface}",
                        device_group_index=0,
                    ),
                ],
                name="TEST_RAW_UNH_REMOTE_SUBNET_IPV6_TRAFFIC",
                line_rate_type=ixia_types.RateType.FRAMES_PER_SECOND,
                line_rate=2000,
                traffic_type=ixia_types.TrafficType.RAW,
                bidirectional=False,
                packet_headers=UNH_REMOTE_SUBNET_IPV6_TRAFFIC_PACKET_HEADERS,
            ),
            taac_types.BasicTrafficItemConfig(
                src_endpoints=[
                    taac_types.TrafficEndpoint(
                        name=f"{device_name}:{ixia_uplink_interface}",
                        device_group_index=0,
                    ),
                ],
                dest_endpoints=[
                    taac_types.TrafficEndpoint(
                        name=f"{device_name}:{ixia_downlink_interface}",
                        device_group_index=0,
                    ),
                ],
                name="TEST_RAW_UNH_REMOTE_SUBNET_128_IPV6_TRAFFIC",
                line_rate_type=ixia_types.RateType.FRAMES_PER_SECOND,
                line_rate=2000,
                traffic_type=ixia_types.TrafficType.RAW,
                bidirectional=False,
                packet_headers=UNH_REMOTE_SUBNET_128_IPV6_TRAFFIC_PACKET_HEADERS,
            ),
        ],
        # Test execution playbooks - CPU queue classification tests only
        playbooks=add_common_checks_to_cpu_queue_playbooks(
            create_cpu_queue_playbooks(
                low_queue=low_queue,
                mid_queue=mid_queue,
                high_queue=high_queue,
                ixia_downlink_interface=ixia_downlink_interface,
            ),
            unique_prefix_limit=unique_prefix_limit,
            ixia_packet_loss_threshold=ixia_packet_loss_threshold,
        ),
    )
