# Copyright (c) Meta Platforms, Inc. and affiliates.

# pyre-unsafe
"""CHRONOS_NODE_FRAMEWORK_VALIDATION_AGENT_RESTART_QZD1 — fast framework-validation TestConfig.

Purpose: this is NOT an FBOSS product test. It is a quick *framework*
validation that exercises the SAME stack touchpoints as the full-scale
longevity config (`CHRONOS_NODE_FULL_SCALE_SSW_ELBERT_QZD1`) — the full
`build_bgp_dc_test_config` setup_tasks (bgpd restart, agent-convergence
waits, COOP unregister/apply/register patchers, basset reservation), BGP
peering bring-up, IXIA emulation, and pre/post/snapshot health checks —
but at drastically reduced scale and wait time so it completes fast and
can be used as a smoke test (including under `TAAC_OSS=1`).

It replaces the heavy longevity playbook
(`test_longevity_session_flap_all_prefixes_plus_bgp_restart`) with a single
`test_agent_restart` playbook (restart the agent, wait for convergence),
run for ONE iteration instead of the default ten.

Same device topology as `CHRONOS_NODE_FULL_SCALE_SSW_ELBERT_QZD1`
(device, MAC, IXIA ports, peergroups, route-maps, networks). Only the
scale and wait knobs differ:

  * peers:     20/20/20  -> 2/2/2
  * prefixes:  10k/7.5k/17.5k (v6/v4/rogue) -> 50 each
  * prefix_limit / per_peer_max_route_limit reduced
  * platform entry/ecmp counts reduced (not exercised by test_agent_restart,
    kept small for a consistent low-scale profile)
  * agent-restart iterations: 10 -> 1   (wedge_agent_restart_no_of_interations)
  * agent-convergence waits capped (convergence_wait_timeout/_interval) so a
    slow/unhealthy device fails fast instead of hanging on the full ceiling

Built from the centralized `build_bgp_dc_test_config` factory.
"""

from taac.testconfigs.routing import build_bgp_dc_test_config


CHRONOS_NODE_FRAMEWORK_VALIDATION_AGENT_RESTART_QZD1_TEST_CONFIG = build_bgp_dc_test_config(
    test_config_name="CHRONOS_NODE_FRAMEWORK_VALIDATION_AGENT_RESTART_QZD1",
    device_name="ssw001.s002.f01.qzd1",
    local_mac_address="c2:18:50:9c:1f:1d",
    ixia_downlink_interface="eth7/16/1",
    ixia_uplink_interface="eth8/16/1",
    ixia_rogue_interface="eth9/16/1",
    peergroup_uplink_mimic_v6="PEERGROUP_SSW_FADU_V6",
    peergroup_uplink_mimic_v4="PEERGROUP_SSW_FADU_V4",
    peergroup_downlink_mimic_v6="PEERGROUP_SSW_FSW_V6",
    peergroup_downlink_mimic_v4="PEERGROUP_SSW_FSW_V4",
    peergroup_rogue_mimic_v6="PEERGROUP_SSW_FADU_V6",  # Setting Same as uplink
    peergroup_rogue_mimic_v4="PEERGROUP_SSW_FADU_V4",  # Setting Same as uplink
    route_map_uplink_ingress="PROPAGATE_SSW_FADU_IN",
    route_map_uplink_egress="PROPAGATE_SSW_FADU_OUT",
    route_map_downlink_ingress="PROPAGATE_SSW_FSW_IN",
    route_map_downlink_egress="PROPAGATE_SSW_FSW_OUT",
    route_map_rogue_ingress="PROPAGATE_SSW_FADU_IN",  # Setting Same as uplink
    route_map_rogue_egress="PROPAGATE_SSW_FSW_OUT",  # Setting Same as uplink
    ixia_downlink_ic_parent_network_v6="2401:db00:e50d:11:8",
    ixia_uplink_ic_parent_network_v6="2401:db00:e50d:11:9",
    ixia_rogue_ic_parent_network_v6="2401:db00:e50d:11:10",
    ixia_downlink_ic_parent_network_v4="10.163.28",
    ixia_uplink_ic_parent_network_v4="10.164.28",
    ixia_rogue_ic_parent_network_v4="10.165.28",
    good_ndp_entry_network_v6="2401:db00:e50d:11:9",
    rogue_ndp_entry_network_v6="2401:db00:e50d:11:8",
    good_arp_entry_network_v4="192.168",
    rogue_arp_entry_network_v4="193.168",
    # --- reduced scale (load-bearing for the agent-restart run) ---
    prefix_limit="5000",
    per_peer_max_route_limit="2000",
    downlink_peer_count=2,
    uplink_peer_count=2,
    rogue_peer_count=2,
    remote_downlink_as_4byte=65409,
    remote_uplink_as_4byte=65271,
    remote_rogue_as_4byte=2500,
    is_uplink_peer_confed="False",
    is_downlink_peer_confed="False",
    is_rogue_peer_confed="False",  # Setting Same as uplink
    ixia_downlink_prefix_count_v6=50,
    ixia_uplink_prefix_count_v6=50,
    ixia_rogue_prefix_count_v6=50,
    ixia_downlink_prefix_count_v4=50,
    ixia_uplink_prefix_count_v4=50,
    ixia_rogue_prefix_count_v4=50,
    ixia_uplink_good_ndp_network="2401:db00:e50d:1101:9",
    ixia_downlink_good_ndp_network="2401:db00:e50d:1101:8",
    ixia_downlink_communities=[
        "65529:34814",
        "65441:131",
    ],
    ixia_uplink_communities=[
        "65441:261",
    ],
    downlink_peer_tag="RSW",
    uplink_peer_tag="SSW",
    # --- reduced platform entry/ecmp counts ---
    # ecmp_group_limit/ecmp_member_limit feed the add_stress_static_routes SETUP
    # task, which must satisfy: max_member == sum of group sizes, where each of
    # ecmp_group_limit groups holds between min_size(=2) and
    # max_size(=min(36, nh_list//4)) members, and nh_list ~= good_ndp_entries_uplink.
    # With good_ndp_entries_uplink=10 -> max_size=2, so every group is size 2 and
    # ecmp_member_limit must equal ecmp_group_limit*2. Uniqueness needs
    # C(10,2)=45 >= ecmp_group_limit. 10 groups * 2 = 20 members satisfies both.
    ecmp_group_limit=10,
    ecmp_member_limit=20,
    good_ndp_entries_uplink=10,
    good_ndp_entries_downlink=10,
    rogue_ndp_entries=20,
    good_arp_entries=10,
    rogue_arp_entries=20,
    good_mac_entry_count=10,
    rogue_mac_entry_count=20,
    bgp_induced_ecmp_group_count=5,
    basset_pool="dne.test",
    # --- single quick playbook: restart the agent + wait for convergence ---
    playbooks_selected=["test_agent_restart"],
    # --- quick-validation wait/iteration knobs ---
    wedge_agent_restart_no_of_interations=1,
    convergence_wait_timeout=120,
    convergence_wait_interval=5,
)
