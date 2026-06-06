# (c) Meta Platforms, Inc. and affiliates. Confidential and proprietary.

# pyre-unsafe
"""NPI_DVT_ICEPACK_GTSW__CPU_QUEUE_TEST_CONFIG — TestConfig.

Built from the centralized `create_dctypef_npi_cpu_queue_test_config` factory.
First-pass IcePack instantiation for `gtsw001.l1001.c085.ash6.tfbnw.net` (leaf
in a GTSW->STSW fabric; TH6 ASIC; netwhoami `hw=ICECUBE800BC=70`,
`chmodel=CHMODEL_ICEPACK_BCMTH6_GENERIC=3050`). Pavan-confirmed 2026-06-04:
TH6 (low, mid, high) = (0, 2, 9), same as Minipack3; per-packet queue mapping
is platform-agnostic; GTSW testing alone is sufficient (no STSW config needed).
"""

from taac.testconfigs.fboss_solution_tests.fboss_dctypef_51t_npi_cpu_queue_test_config import (
    create_dctypef_npi_cpu_queue_test_config,
)

NPI_DVT_ICEPACK_GTSW__CPU_QUEUE_TEST_CONFIG = create_dctypef_npi_cpu_queue_test_config(
    test_config_name="NPI_DVT_ICEPACK_GTSW__CPU_QUEUE_TEST_CONFIG",
    device_name="gtsw001.l1001.c085.ash6",
    local_mac_address="02:00:00:00:0f:0c",
    # IXIA ports: factory uses uplink as source of CPU-queue test traffic,
    # downlink as sink + BGP-flap target. Rogue is unused for CPU-queue
    # items but required by the factory signature.
    ixia_downlink_interface="eth1/13/1",
    ixia_uplink_interface="eth1/13/3",
    ixia_rogue_interface="eth1/13/5",
    # Uplink: real existing peer group toward the STSW spine.
    peergroup_uplink_mimic_v6="PEERGROUP_GTSW_STSW_V6",
    peergroup_uplink_mimic_v4="PEERGROUP_GTSW_STSW_V4",
    # Downlink: this GTSW is a leaf (no native host-facing peer group), so we
    # attach IXIA-mimic downlink peers to the real PEERGROUP_GTSW_STSW_V6.
    # The factory's update_peer_group_patcher only works on existing groups;
    # using the fictional PEERGROUP_GTSW_HOST_MIMIC_V6 crashed bgpd because
    # update is a no-op on non-existent groups, leaving peers referencing an
    # undefined group. v4 still uses add_peer_group_patcher (creates from
    # scratch), so the fictional v4 name is fine.
    peergroup_downlink_mimic_v6="PEERGROUP_GTSW_STSW_V6",
    peergroup_downlink_mimic_v4="PEERGROUP_GTSW_HOST_MIMIC_V4",
    # Rogue: mirror uplink (KO3 convention).
    peergroup_rogue_mimic_v6="PEERGROUP_GTSW_STSW_V6",
    peergroup_rogue_mimic_v4="PEERGROUP_GTSW_STSW_V4",
    # All directions point at the only real route-map pair on this leaf
    # (PROPAGATE_GTSW_STSW_IN/OUT). The add_peer_group_patcher validates that
    # ingress/egress policies exist before accepting the peer-group config;
    # fictional names crash bgpd at startup. Sharing one policy across uplink,
    # downlink, and rogue is fine for first-run CPU-queue validation.
    route_map_uplink_ingress="PROPAGATE_GTSW_STSW_IN",
    route_map_uplink_egress="PROPAGATE_GTSW_STSW_OUT",
    route_map_downlink_ingress="PROPAGATE_GTSW_STSW_IN",
    route_map_downlink_egress="PROPAGATE_GTSW_STSW_OUT",
    route_map_rogue_ingress="PROPAGATE_GTSW_STSW_IN",
    route_map_rogue_egress="PROPAGATE_GTSW_STSW_OUT",
    # IXIA-side parent networks: use the pre-configured BGP_MONITOR
    # placeholder ranges already present on the DUT
    # (v4 10.127.240.0/23, v6 2401:db00:1ff:c100::/56).
    ixia_downlink_ic_parent_network_v6="2401:db00:1ff:c108",
    ixia_uplink_ic_parent_network_v6="2401:db00:1ff:c109",
    ixia_rogue_ic_parent_network_v6="2401:db00:1ff:c10a",
    ixia_downlink_ic_parent_network_v4="10.127.240",
    ixia_uplink_ic_parent_network_v4="10.127.241",
    ixia_rogue_ic_parent_network_v4="10.127.242",
    # Scale: minimal for CPU-queue test first-pass. BGP peers are anchors for
    # IXIA traffic injection; the CPU-queue assertions don't depend on prefix
    # count. KO3 baseline of 32 peers × 5000 prefixes overwhelmed TH6's CPU
    # (21M+ drops on low queue, 100% loss on BGP_PREFIX background — see
    # earlier failed runs). Scaling to 8 peers × 500 prefixes reduces BGP
    # control-plane load ~10×.
    unique_prefix_limit="5000",
    per_peer_max_route_limit="20000",
    downlink_peer_count=8,
    uplink_peer_count=8,
    rogue_peer_count=8,
    # Private-range ASNs that are DIFFERENT from DUT's local AS (4200601001).
    # IXIA's BGP-mimic always uses step=1 (doesn't honor step=0) and treats
    # peers as EBGP since peer-group has no confed flag. EBGP requires peer AS
    # != local AS; if our base ASN matched DUT's 4200601001, peer 0 would be
    # rejected with BN_OM_BAD_PEER_AS. Picking 65272 (uplink) / 7001 (downlink)
    # mirrors KO3 reference; both are well outside DUT's AS range.
    remote_uplink_as_4byte=65272,
    remote_downlink_as_4byte=7001,
    remote_as_4_byte_step=1,
    remote_rogue_as_4byte=2500,
    is_uplink_peer_confed="False",
    is_downlink_peer_confed="False",
    is_rogue_peer_confed="False",
    ixia_downlink_prefix_count_v6=500,
    ixia_uplink_prefix_count_v6=500,
    ixia_rogue_prefix_count_v6=500,
    ixia_downlink_prefix_count_v4=500,
    ixia_uplink_prefix_count_v4=500,
    ixia_rogue_prefix_count_v4=500,
    # `PROPAGATE_GTSW_STSW_IN` is a path-vector BGP-compiler policy that DENYs
    # by default. Routes need three communities to be accepted + installed in
    # FIB (otherwise `BGP_PREFIX_TRAFFIC` sees 100% loss):
    #   - `65446:30`  LIVE — sets LP=100, marks alive (rule 1)
    #   - `65441:323` PATH_COMMUNITY_GTSW_E_HOP3 — required (rule 4 DENY if missing)
    #   - `65456:323` LP=90 marker — one of `654[51-63]:323` is required (rule 17 DENY if none match)
    # 65456:323 specifically matches what real STSW peers carry (their accepted
    # routes show LP=90 in `fboss2 show bgp table`).
    # Both uplink and downlink IXIA-mimic peers attach to PEERGROUP_GTSW_STSW_V6,
    # so both must carry the same community set.
    ixia_downlink_communities=["65446:30", "65441:323", "65456:323"],
    ixia_uplink_communities=["65446:30", "65441:323", "65456:323"],
    downlink_peer_tag="HOST",
    uplink_peer_tag="STSW",
    bgpd_restart_no_of_interations=5,
    wedge_agent_restart_no_of_interations=5,
    basset_pool="dne.test",
)
