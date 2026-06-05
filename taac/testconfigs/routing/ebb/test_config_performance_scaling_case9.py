# pyre-unsafe
"""Arista BGP++ performance scaling test case 9: bounded ECMP sets.

Builds a TestConfig that exercises Arista BGP++ ECMP set bounding logic
under IBGP + EBGP peering at production scale. Used to verify that the
DUT properly caps ECMP next-hop set size and recovers correctly when
peers come and go.
"""

from taac.playbooks.playbook_definitions import (
    create_bgp_plus_plus_arista_bounded_ecmp_sets_playbook,
)
from taac.routing.ebb.arista_bgp_plus_plus_performance_scaling_tests.ixia_configs_for_tests import (
    create_ebb_bounded_ecmp_sets_port_configs,
)
from taac.task_definitions import (
    create_configure_bgpcpp_startup_task,
    create_replace_bgp_peers_task,
)
from taac.test_as_a_config.types import Endpoint, TestConfig


def test_config_for_bgp_plus_plus_on_ebb_arista_bounded_ecmp_sets(
    test_config_name: str,
    device_name: str,
    ixia_interface_mimic_ebgp: str,
    ixia_interface_mimic_ibgp: str,
    ebgp_peer_count_v6: int,
    ibgp_peer_count_v6: int,
    ebgp_peer_count_v4: int,
    ibgp_peer_count_v4: int,
    ebgp_remote_as: int,
    ibgp_remote_as: int,
    ixia_ebgp_ic_parent_network_v6: str,
    ixia_ibgp_ic_parent_network_v6: str,
    ixia_ebgp_ic_parent_network_v4: str,
    ixia_ibgp_ic_parent_network_v4: str,
    prefix_count: int,
    direct_ixia_connections: list,
    log_collection_timeout=None,
    oss_mock_device_data=None,
    host_os_type_map=None,
    host_driver_args=None,
    ssh_user: str = "admin",
    ssh_password: str = "",
    peergroup_ebgp_v6: str = "EB-FA-V6",
    peergroup_ebgp_v4: str = "EB-FA-V4",
    peergroup_ibgp_v6: str = "EB-EB-V6",
    peergroup_ibgp_v4: str = "EB-EB-V4",
):
    """Build the case-9 (bounded ECMP sets) BGP++ TestConfig.

    Configures EBGP + IBGP peer groups (v4 + v6) via bgpcpp dynamic peer
    replacement, then runs `create_bgp_plus_plus_arista_bounded_ecmp_sets_playbook`
    to verify the DUT's ECMP set bounding behavior at production peer scale.

    Args:
        test_config_name: Final name of the produced TestConfig.
        device_name: DUT hostname (Arista EBB).
        ixia_interface_mimic_ebgp / ixia_interface_mimic_ibgp: IXIA port
            names used as peer endpoints.
        ebgp_peer_count_v6 / ibgp_peer_count_v6 / ebgp_peer_count_v4 /
        ibgp_peer_count_v4: Per-AFI peer counts.
        ebgp_remote_as / ibgp_remote_as: Remote ASNs.
        ixia_*_ic_parent_network_v6/v4: Parent networks for IXIA-side prefix
            generation.
        prefix_count: Number of prefixes advertised per peer.
        direct_ixia_connections: Optional direct IXIA-port connection list.
        log_collection_timeout / oss_mock_device_data / host_os_type_map /
        host_driver_args: Optional overrides for OSS harness wiring.
        ssh_user / ssh_password: Credentials for dynamic bgpcpp peer
            configuration.
        peergroup_*: Peer-group names (defaults match EB-FA/EB-EB).

    Returns:
        TestConfig: The case-9 bounded-ECMP-sets TestConfig (consumed via
        `testconfigs.routing.ebb`).
    """
    return TestConfig(
        name=test_config_name,
        skip_ixia_protocol_verification=True,
        log_collection_timeout=log_collection_timeout,
        basset_pool="dne.test",
        endpoints=[
            Endpoint(
                name=device_name,
                dut=True,
                ixia_ports=[ixia_interface_mimic_ebgp],
                direct_ixia_connections=direct_ixia_connections
                if direct_ixia_connections
                else [],
            ),
        ],
        host_driver_args=host_driver_args,
        oss_mock_device_data=oss_mock_device_data,
        host_os_type_map=host_os_type_map,
        startup_checks=[],
        setup_tasks=[
            create_configure_bgpcpp_startup_task(
                hostname=device_name,
                flags={
                    "agent_thrift_recv_timeout_ms": "160000",
                },
                ssh_user=ssh_user,
                ssh_password=ssh_password,
            ),
            create_replace_bgp_peers_task(
                hostname=device_name,
                peer_configs=[
                    {
                        "peer_group_name": peergroup_ebgp_v6,
                        "remote_as": ebgp_remote_as,
                        "base_network": ixia_ebgp_ic_parent_network_v6,
                        "is_v6": True,
                        "peer_count": ebgp_peer_count_v6,
                        "start_offset": 16,
                    },
                    {
                        "peer_group_name": peergroup_ebgp_v4,
                        "remote_as": ebgp_remote_as,
                        "base_network": ixia_ebgp_ic_parent_network_v4,
                        "is_v6": False,
                        "peer_count": ebgp_peer_count_v4,
                        "start_offset": 10,
                    },
                    {
                        "peer_group_name": peergroup_ibgp_v6,
                        "remote_as": ibgp_remote_as,
                        "base_network": ixia_ibgp_ic_parent_network_v6,
                        "is_v6": True,
                        "peer_count": ibgp_peer_count_v6,
                        "start_offset": 16,
                    },
                    {
                        "peer_group_name": peergroup_ibgp_v4,
                        "remote_as": ibgp_remote_as,
                        "base_network": ixia_ibgp_ic_parent_network_v4,
                        "is_v6": False,
                        "peer_count": ibgp_peer_count_v4,
                        "start_offset": 10,
                    },
                ],
            ),
        ],
        teardown_tasks=[],
        # Deprecated - define at playbook level
        # prechecks=[],
        # postchecks=[],
        # snapshot_checks=[],
        basic_port_configs=create_ebb_bounded_ecmp_sets_port_configs(
            device_name=device_name,
            ixia_interface_mimic_ebgp=ixia_interface_mimic_ebgp,
            ixia_interface_mimic_ibgp=ixia_interface_mimic_ibgp,
            ebgp_peer_count_v6=ebgp_peer_count_v6,
            ebgp_peer_count_v4=ebgp_peer_count_v4,
            ibgp_peer_count_v6=ibgp_peer_count_v6,
            ibgp_peer_count_v4=ibgp_peer_count_v4,
            ebgp_remote_as=ebgp_remote_as,
            ibgp_remote_as=ibgp_remote_as,
            prefix_count=prefix_count,
            ixia_ebgp_ic_parent_network_v6=ixia_ebgp_ic_parent_network_v6,
            ixia_ebgp_ic_parent_network_v4=ixia_ebgp_ic_parent_network_v4,
            ixia_ibgp_ic_parent_network_v6=ixia_ibgp_ic_parent_network_v6,
            ixia_ibgp_ic_parent_network_v4=ixia_ibgp_ic_parent_network_v4,
        ),
        playbooks=[
            create_bgp_plus_plus_arista_bounded_ecmp_sets_playbook(
                device_name=device_name,
            ),
        ],
    )
