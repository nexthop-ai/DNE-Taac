# Copyright (c) Meta Platforms, Inc. and affiliates.
# pyre-unsafe

"""
IcePack ECMP/DLB Resource Testing Configuration.

Testbed: gtsw001.l1001.c085.ash6 (IcePack, TH6 / ICECUBE800BC = 70)
IXIA: ixia19.netcastle.ash6 (chassis 2401:db00:2066:31fb::3019)

Mirrors `testconfigs/ai_bb/wedge400_ecmp_resource_testing_config.py` shape
(3-port topology: downlink + rogue + remote; Gold/Silver/Rouge BGP
sessions on the rogue port + NDP-supporting NH device group). Reuses the 3
playbook factories `create_ecmp_groups_playbooks`,
`create_ecmp_members_playbooks`, `create_spillover_testing_playbooks`
as-is.

PORT COLLISION NOTE: eth1/1/1, /3, /5 on this GTSW are also referenced by
`testconfigs/ai_bb/mp3n_prefix_profiling_ixia_config.py` Section 12
(GTSW001_CONTIGUOUS/HYBRID/NON_CONTIGUOUS_PREFIX_ALL using ixia19 ports
1/25, 1/27, 1/29). Per user direction 2026-06-18 these are the
"properly IXIA ready" ports for this DUT. Only one of the two testbeds
may run at a time on this DUT.

DLB resource budget (Gold/Silver/Rouge multipliers + ecmp_widths) is
currently the Wedge400/TH3 placeholder set (Gold=7000x64, Silver=34500x25,
Rouge=7000x64). TH6 has its own DLB budget (per the ECMP/DLB hardening
background doc, TH6 DLB groups/members/width are TBD pending
Pavan/Rahul). When confirmed, replace the placeholder values in
`AsicEcmpLimits`-style derivation rather than hard-coding here.
"""

import json
import os

from ixia.ixia import types as ixia_types
from taac.health_checks.healthcheck_definitions import (
    create_core_dumps_snapshot_check,
    create_prefix_limit_check,
    create_systemctl_active_state_check,
)
from taac.packet_headers import DSF_RDMA_IB_PACKET_HEADERS
from taac.playbooks.playbook_definitions import (
    create_dlb_topology_smoke_playbook,
)
from taac.task_definitions import (
    create_coop_apply_patchers_task,
    create_coop_register_patcher_task,
    create_coop_unregister_patchers_task,
)
from taac.testconfigs.npi.dlb_csvs import gen_dlb_csv
from taac.health_check.health_check import types as hc_types
from taac.test_as_a_config import types as taac_types
from taac.test_as_a_config.types import Playbook, TestConfig


# Peer group constant. Matches the naming convention already used on this
# DUT by `mp3n_prefix_profiling_ixia_config.py` (PEERGROUP_GTSW_IXIA_V6).
PEERGROUP_GTSW_IXIA_V6 = "PEERGROUP_GTSW_IXIA_V6"


# =============================================================================
# DLB CSV generation (runtime, ephemeral, NOT in fbcode)
#
# Generates the DLB add-path CSV fixtures into a fresh /tmp directory at
# module load. We feed those file paths into IXIA via
# `ImportBgpRoutesParams.bgp_route_import_file_path` (see SECTION 6),
# which `ixia.py::import_bgp_attribute_profile_from_configerator` accepts
# in its post-2026-06-23 "absolute path" mode (bypasses the configerator
# round-trip needed for the original EBB-style CSV upload). When the CSV
# catalog stabilises the proper landing is to drop the fixtures under
# `~/configerator/source/taac/bgp_attribute_profiles/dlb/` and switch
# the testconfig back to relative paths.
# =============================================================================
# Fixed (NOT random) directory so the testconfig's serialized
# `bgp_route_import_file_path` is deterministic — required for the
# golden manifest hash to be stable across runs/processes. Output is
# idempotent (same generator inputs → same CSV bytes) so concurrent
# loads from different processes overwriting the same files is safe.
_DLB_CSV_DIR: str = "/tmp/icepack_dlb_csvs"
os.makedirs(_DLB_CSV_DIR, exist_ok=True)
# Default knobs match gen_dlb_csv.py CLI defaults (511 groups, 120 width,
# 128 NHs). Generated in-process so we avoid spawning a subprocess from a
# Buck par binary (where `sys.executable` is the par, not python3).
gen_dlb_csv.write_csv(
    os.path.join(_DLB_CSV_DIR, "dlb_width_128.csv"),
    gen_dlb_csv.gen_width(128),
)
gen_dlb_csv.write_csv(
    os.path.join(_DLB_CSV_DIR, "dlb_members_128.csv"),
    gen_dlb_csv.gen_members(128, 120),
)
gen_dlb_csv.write_csv(
    os.path.join(_DLB_CSV_DIR, "dlb_fill_511.csv"),
    gen_dlb_csv.gen_fill(511, 120, 128),
)
gen_dlb_csv.write_csv(
    os.path.join(_DLB_CSV_DIR, "dlb_overflow_129.csv"),
    gen_dlb_csv.gen_overflow(120, 128),
)
gen_dlb_csv.write_communities_csv(os.path.join(_DLB_CSV_DIR, "dlb_communities.csv"))
DLB_WIDTH_128_CSV_PATH: str = os.path.join(_DLB_CSV_DIR, "dlb_width_128.csv")
DLB_FILL_511_CSV_PATH: str = os.path.join(_DLB_CSV_DIR, "dlb_fill_511.csv")
DLB_MEMBERS_128_CSV_PATH: str = os.path.join(_DLB_CSV_DIR, "dlb_members_128.csv")
DLB_OVERFLOW_129_CSV_PATH: str = os.path.join(_DLB_CSV_DIR, "dlb_overflow_129.csv")
DLB_COMMUNITIES_CSV_PATH: str = os.path.join(_DLB_CSV_DIR, "dlb_communities.csv")


# =============================================================================
# SECTION 2: L1 AND FRAME SIZE CONFIGURATIONS
# Identical to the W400 testconfig; DLB engagement on TH-class silicon
# requires RDMA-IB-style headers, not raw IPv6.
# =============================================================================
DSF_FRAME_SIZES = ixia_types.FrameSize(
    type=ixia_types.FrameSizeType.CUSTOM_IMIX,
    imix_weight={94: 1, 96: 18, 192: 3, 512: 1, 1200: 1, 4600: 76},
)

DSF_L1_CONFIG = ixia_types.L1Config(
    enable_fcoe=True,
    flow_control_config=ixia_types.FlowControlConfig(
        pfc_prority_groups_config=ixia_types.PfcPriorityGroupsConfig(
            priority0_pfc_queue=ixia_types.PfcQueue.TWO,
            priority1_pfc_queue=ixia_types.PfcQueue.ONE,
            priority2_pfc_queue=ixia_types.PfcQueue.ZERO,
            priority3_pfc_queue=ixia_types.PfcQueue.THREE,
        ),
        enable_pfc_pause_delay=False,
    ),
)


# =============================================================================
# SECTION 4.2: ECMP RESOURCE TESTING PEER-GROUP HELPER
#
# Creates our own dedicated peer-group (PEERGROUP_GTSW_IXIA_V6) — we need
# it because the existing fabric peer-groups don't negotiate BGP AddPath
# (add_path = BOTH), which we require for multi-path advertisement of
# Gold/Silver/Rouge prefixes.
#
# BUT the peer-group reuses the existing on-device policy chain
# `PROPAGATE_GTSW_STSW_IN/OUT` instead of creating a fresh empty one.
# The stock GTSW policy chain has a 4-rule community-gated import path
# (rule 1 LIVE 65446:30 / rule 4 PATH_COMMUNITY 65441:323 / rule 17 LP=90
# marker 654[51-63]:323) that gates whether received routes install into
# FIB. A fresh empty `PROPAGATE_GTSW_IXIA_IN` policy doesn't satisfy that
# chain, so routes get into BGP RIB (PA increments) but never reach FIB —
# verified on gtsw001.l1001.c085.ash6 on 2026-06-18: PA=48500 but FIB=0.
#
# This matches the pattern used by the IcePack CPU-queue testconfig
# (`cpu_queue_test_config.py`), which also reuses PROPAGATE_GTSW_STSW_IN.
# The IXIA-side `community_list` on each network group must include all
# three required communities (see SECTION 6 device-group configs).
# =============================================================================
def get_gtsw_ixia_peer_group_tasks(device_name):
    """Return COOP patcher tasks that configure the IcePack GTSW peer group
    for uplink eBGP peering with IXIA. Reuses the on-device
    PROPAGATE_GTSW_STSW_IN/OUT policy chain (which has the community-gated
    FIB-install rules) instead of creating a fresh empty IXIA policy."""
    return [
        create_coop_register_patcher_task(
            hostname=device_name,
            config_name="bgpcpp",
            patcher_name="add_peer_group_patcher_PEERGROUP_GTSW_IXIA_V6",
            task_name="add_peer_group_patcher",
            patcher_args={
                "name": PEERGROUP_GTSW_IXIA_V6,
                "description": "eBGP peering from GTSW to IXIA, IPv6 sessions",
                "disable_ipv4_afi": "True",
                "disable_ipv6_afi": "False",
                "ingress_policy_name": "PROPAGATE_GTSW_STSW_IN",
                "egress_policy_name": "PROPAGATE_GTSW_STSW_OUT",
                "bgp_peer_timers_hold_time_seconds": "30",
                "bgp_peer_timers_keep_alive_seconds": "10",
                "bgp_peer_timers_out_delay_seconds": "0",
                "bgp_peer_timers_withdraw_unprog_delay_seconds": "0",
                "peer_tag": "IXIA",
                "max_routes": "900000",
                "warning_only": "True",
                "warning_limit": "0",
                "next_hop_self": "False",
                "add_path": "BOTH",
                "is_confed_peer": "False",
                "is_passive": "False",
                "v4_over_v6_nexthop": "False",
                "link_bandwidth_bps": "auto",
            },
            py_func_name="add_peer_group_patcher",
        ),
    ]


# =============================================================================
# SECTION 6: TEST CONFIG FACTORY FUNCTION
# Parameterized factory; one TestConfig instance is declared in Section 7
# for the gtsw001.l1001.c085.ash6 testbed.
# =============================================================================
def test_config_for_icepack_ecmp_resource_testing(
    test_config_name,
    device_name,
    local_mac_address,
    ixia_downlink_interface,
    ixia_rogue_interface,
    ixia_remote_interface,
    ixia_downlink_ic_parent_network_v6,
    ixia_rogue_ic_parent_network_v6,
    ixia_remote_ic_parent_network_v6,
    ixia_nexthop_supporting_ndp_network,
    ixia_nexthop_supporting_ndp_gateway,
    remote_uplink_as_4byte,
    is_uplink_peer_confed,
    prefix_limit,
    direct_ixia_connections=None,
    basset_pool=None,
):
    """Build the IcePack ECMP/DLB resource testing TestConfig.

    Single-DUT, 3-port topology mirroring W400:
    - Downlink port: pure L3 traffic source, no BGP
    - Rogue port: hosts the 3 BGP sessions (Gold = DLB-eligible,
      Silver = non-DLB ECMP, Rouge = overcommit) and the
      NDP_SUPPORTING_NEXTHOP device group
    - Remote port: pure L3 traffic source for Silver+Rouge

    DLB resource budget (Gold/Silver/Rouge `network_group_multiplier` and
    `ecmp_width`) uses W400/TH3 placeholder values. TH6 values are TBD
    pending Pavan/Rahul confirmation; swap them in here when known.
    """
    tc_prechecks = [
        create_systemctl_active_state_check(
            services=[
                hc_types.Service.WEDGE_AGENT,
                hc_types.Service.BGPD,
                hc_types.Service.QSFP_SERVICE,
                hc_types.Service.FSDB,
                hc_types.Service.FBOSS_SW_AGENT,
                # NOTE: IcePack does NOT have a `fboss_hw_agent_0` systemd
                # unit (verified live 2026-06-18 — `systemctl status
                # fboss_hw_agent_0` → "could not be found"). TH6 multi-ASIC
                # HW agents are named differently or rolled into
                # fboss_sw_agent. Confirm with Pavan/Rahul which HW-agent
                # service(s) to gate on for IcePack and add here.
            ],
        ),
    ]

    tc_postchecks = [
        create_systemctl_active_state_check(
            services=[
                hc_types.Service.WEDGE_AGENT,
                hc_types.Service.BGPD,
                hc_types.Service.QSFP_SERVICE,
                hc_types.Service.FSDB,
                hc_types.Service.FBOSS_SW_AGENT,
                # NOTE: IcePack does NOT have a `fboss_hw_agent_0` systemd
                # unit (verified live 2026-06-18 — `systemctl status
                # fboss_hw_agent_0` → "could not be found"). TH6 multi-ASIC
                # HW agents are named differently or rolled into
                # fboss_sw_agent. Confirm with Pavan/Rahul which HW-agent
                # service(s) to gate on for IcePack and add here.
            ],
        ),
        create_prefix_limit_check(prefix_limit=prefix_limit),
    ]

    tc_snapshot_checks = [
        create_core_dumps_snapshot_check(),
    ]

    def _add_tc_checks_to_playbook(pb: Playbook) -> Playbook:
        new_prechecks = tc_prechecks + list(pb.prechecks or [])
        new_postchecks = list(pb.postchecks or []) + tc_postchecks

        if pb.skip_test_config_snapshot_checks:
            new_snapshot_checks = list(pb.snapshot_checks or [])
        else:
            new_snapshot_checks = list(pb.snapshot_checks or []) + tc_snapshot_checks

        return pb(
            prechecks=new_prechecks,
            postchecks=new_postchecks,
            snapshot_checks=new_snapshot_checks,
            skip_test_config_snapshot_checks=False,
        )

    def _add_tc_checks_to_playbooks(playbooks: list[Playbook]) -> list[Playbook]:
        return [_add_tc_checks_to_playbook(pb) for pb in playbooks]

    endpoints = [
        taac_types.Endpoint(
            name=device_name,
            ixia_ports=[
                ixia_downlink_interface,
                ixia_rogue_interface,
                ixia_remote_interface,
            ],
            dut=True,
            mac_address=local_mac_address,
            direct_ixia_connections=(
                direct_ixia_connections if direct_ixia_connections else []
            ),
        ),
    ]

    return TestConfig(
        name=test_config_name,
        ixia_protocol_verification_timeout=10,
        skip_ixia_protocol_verification=True,
        # Opt out of the IXIA config cache. The cache key is
        # `<test_config_name>_<chassis_ip>.ixncfg` (content-blind), so a
        # cached session from a prior run will silently override any change
        # we make here (e.g., BGP `community_list`, peer-group policy
        # references). Same opt-out pattern as the CPU-queue testconfig.
        # Costs ~14 min of fresh IXIA setup per run; flip back to default
        # (cache enabled) once the testconfig stabilises.
        ixia_config_cache=taac_types.IxiaConfigCache(enabled=False),
        basset_pool=basset_pool,
        endpoints=endpoints,
        setup_tasks=[
            create_coop_unregister_patchers_task(device_name),
            # NEW (2026-06-23 refactor): disable all GTSW→STSW spine
            # interfaces so the silicon DLB super-group starts EMPTY (zero
            # fabric NHs) instead of containing the ~32 NHs from spine
            # peering. Without this, our 128-wide test pushes the
            # super-group past its 128-unique-NH cap and `syncFib` is
            # rejected (verified failure 2026-06-18 with shared NHs,
            # writeup P2385764705). Spine enumeration (2 STSWs × 16 ports
            # each via 4 modules × 4 ports) confirmed live via `fboss2
            # show lldp` on gtsw001.l1001.c085.ash6 — see
            # MEMORY.md/project_bqsb_*. Teardown re-enables via
            # create_coop_unregister_patchers_task.
            create_coop_register_patcher_task(
                hostname=device_name,
                config_name="agent",
                patcher_name="disable_gtsw_spine_interfaces",
                task_name="change_port_admin_state",
                patcher_args={
                    f"eth1/{module}/{port}": "disable"
                    for module in (3, 4, 7, 8, 11, 12, 15, 16)
                    for port in (1, 3, 5, 7)
                },
                py_func_name="change_port_admin_state",
            ),
        ]
        + get_gtsw_ixia_peer_group_tasks(device_name)
        + [
            create_coop_register_patcher_task(
                hostname=device_name,
                config_name="bgpcpp",
                patcher_name="add_bgp_peers_dut",
                task_name="add_bgp_peers",
                patcher_args={
                    "peer_configs": json.dumps(
                        [
                            # First iteration: ONLY the Gold (DLB) peer
                            # per handoff §3 (P2393046303). Silver/Rouge
                            # peers + ECMP-only DGs were dropped from
                            # this revision so we can validate the
                            # clean 128-NH DLB super-group end-to-end
                            # in isolation; they'll be added back once
                            # Gold's CSV-equivalent advertisement is
                            # programming silicon correctly.
                            {
                                "local_addr": f"{ixia_rogue_ic_parent_network_v6}::a",
                                "peer_addr": f"{ixia_rogue_ic_parent_network_v6}::b",
                                "peer_group_name": PEERGROUP_GTSW_IXIA_V6,
                                "remote_as_4_byte": str(remote_uplink_as_4byte),
                                "description": "ixia_session_gold",
                            },
                        ]
                    ),
                },
                py_func_name="add_bgp_peers",
            ),
            create_coop_apply_patchers_task(
                hostnames=[device_name],
                do_warmboot=True,
            ),
        ],
        teardown_tasks=[
            create_coop_unregister_patchers_task(device_name),
        ],
        basic_traffic_item_configs=[
            taac_types.BasicTrafficItemConfig(
                name=f"{ixia_downlink_interface.upper().replace('/', '_')}_TO_DLB_GOLDEN_TRAFFIC",
                src_endpoints=[
                    taac_types.TrafficEndpoint(
                        name=f"{device_name}:{ixia_downlink_interface}",
                        device_group_index=0,
                    ),
                ],
                dest_endpoints=[
                    taac_types.TrafficEndpoint(
                        name=f"{device_name}:{ixia_rogue_interface}",
                        device_group_index=0,
                        network_group_index=0,
                    ),
                ],
                bidirectional=False,
                merge_destinations=True,
                line_rate=10,
                frame_size_settings=ixia_types.FrameSize(
                    type=ixia_types.FrameSizeType.FIXED,
                    fixed_size=1024,
                ),
                src_dest_mesh=ixia_types.SrcDestMeshType.MANY_TO_MANY,
                traffic_type=ixia_types.TrafficType.IPV6,
                tracking_types=[ixia_types.TrafficStatsTrackingType.TRAFFIC_ITEM],
                # RDMA-IB headers (AR=1, RoCEv2/UDP 4791, TC2/DSCP 56) so
                # traffic is DLB-eligible.
                packet_headers=DSF_RDMA_IB_PACKET_HEADERS,
            ),
            # Silver + Rouge traffic items dropped in this first
            # iteration alongside their Silver/Rouge ECMP DGs. They'll
            # be re-added once the Gold DLB super-group programs
            # cleanly on gtsw001.
        ],
        basic_port_configs=[
            # Downlink port (no BGP, just L2/L3 connectivity for traffic source)
            taac_types.BasicPortConfig(
                l1_config=DSF_L1_CONFIG,
                endpoint=f"{device_name}:{ixia_downlink_interface}",
                device_group_configs=[
                    taac_types.DeviceGroupConfig(
                        device_group_index=0,
                        tag_name="DOWNLINK_L3_TRAFFIC",
                        multiplier=1,
                        v6_addresses_config=taac_types.IpAddressesConfig(
                            starting_ip=f"{ixia_downlink_ic_parent_network_v6}::b",
                            increment_ip="::",
                            gateway_starting_ip=f"{ixia_downlink_ic_parent_network_v6}::a",
                            gateway_increment_ip="::",
                            mask=64,
                        ),
                    ),
                ],
            ),
            # Rogue port: ONE Gold BGP session + NDP-supporting NH pool
            # (130 NHs). Per handoff §3 (P2393046303): a single DG with
            # multiplier=1 hosts the eBGP peer; a sibling DG of 130
            # multiplier emulates the NH addresses for NDP resolution.
            # The Gold advertisement is 1 prefix × 128 NHs — equivalent
            # to dlb_width_128.csv (the simplest DLB test) — formulaic
            # so we don't need configerator-side CSV round-trip yet.
            # Silver/Rouge ECMP DGs are dropped from this revision and
            # will be re-added once Gold validates end-to-end.
            taac_types.BasicPortConfig(
                l1_config=DSF_L1_CONFIG,
                endpoint=f"{device_name}:{ixia_rogue_interface}",
                device_group_configs=[
                    # DG 0: DLB resource (Gold) — single BGP peer, 1
                    # prefix × 128 NHs (full DLB super-group width).
                    taac_types.DeviceGroupConfig(
                        device_group_index=0,
                        tag_name="DLB_resource(Gold)",
                        enable=True,
                        multiplier=1,
                        v6_addresses_config=taac_types.IpAddressesConfig(
                            starting_ip=f"{ixia_rogue_ic_parent_network_v6}::b",
                            increment_ip="::",
                            gateway_starting_ip=f"{ixia_rogue_ic_parent_network_v6}::a",
                            gateway_increment_ip="::",
                            mask=64,
                        ),
                        v6_bgp_config=taac_types.BgpConfig(
                            local_as_4_bytes=remote_uplink_as_4byte,
                            local_as_increment=0,
                            enable_4_byte_local_as=True,
                            bgp_peer_type=ixia_types.BgpPeerType.EBGP,
                            is_confed=is_uplink_peer_confed == "True",
                            bgp_capabilities=[
                                ixia_types.BgpCapability.IpV6Unicast,
                                ixia_types.BgpCapability.Ipv6UnicastAddPath,
                            ],
                            # Formulaic prefix+NH expansion via
                            # CustomNetworkGroupConfig — the proven
                            # Wedge400 DSF DLB pattern. 1 prefix × 128
                            # NHs (the DLB super-group width on
                            # TH6/IcePack). The CSV
                            # ImportBgpRoutesParams path was tried
                            # extensively 2026-06-24 (Sent=2/Rcvd=1/
                            # Accepted=1, but IxNetwork silently
                            # defaulted to `3000:0:1:1::/64` instead
                            # of reading our 2-column CSV — IxNetwork's
                            # "Classic CSV" importer apparently
                            # expects more columns than just
                            # Address+NH). For the other 3 variants
                            # (members_128, fill_511, overflow_129)
                            # we'll either stack multiple CNG entries
                            # OR figure out the full Classic CSV
                            # column schema. CNG for width_128 first.
                            custom_network_group_configs=[
                                ixia_types.CustomNetworkGroupConfig(
                                    device_group_name="DLB_resource(Gold)",
                                    network_group_name="DLB_GOLD_PREFIX_POOL",
                                    # 2026-06-24 results matrix:
                                    # | mult | num_addrs | ecmp_w | Sent | Rcvd  | FIB  | Shape           |
                                    # |    1 |         1 |    128 |   2  |     1 |   1  | 1px / 1nh       |
                                    # |    1 |       128 |    128 |   2  |   128 | 128  | 128px / 1nh ea  |
                                    # |  128 |         1 |    128 |   2  |   128 |   1  | 1px / 1nh (no MP)|
                                    # |  128 |       511 |    128 |   2  | 65408 |   1  | 1px / 1nh (no MP)|
                                    # |    1 |       511 |      1 |   2  |   511 | 511  | 511px / 1nh ea ✓|
                                    #
                                    # KEY FINDING: FBOSS bgpd ALWAYS
                                    # installs only 1 best NH per
                                    # prefix regardless of add-path
                                    # count. No multipath knob found
                                    # in bgp_config_v2.thrift schema
                                    # (only `enable_eibgp_multipath`
                                    # for eBGP/iBGP equalization, not
                                    # install-N-as-ECMP). Need to
                                    # find the FBOSS bgpd multipath
                                    # config (likely outside this
                                    # repo) before DLB super-groups
                                    # can form on silicon.
                                    #
                                    # Trying back: 1 prefix × 128 NHs
                                    # via mult=128 — simplest possible
                                    # DLB shape. Will show 1 prefix
                                    # in FIB with 1 NH still — but
                                    # confirms wrapper config logic
                                    # for the next debug round.
                                    network_group_multiplier=128,
                                    prefix_start_value="5000:dd::",
                                    prefix_length=64,
                                    nexthop_start_value=ixia_nexthop_supporting_ndp_network,
                                    nexthop_increments="::1",
                                    ecmp_width=128,
                                    # 3 GTSW gating communities — without
                                    # these the PROPAGATE_GTSW_STSW_IN
                                    # policy denies. Verified failure
                                    # mode 2026-06-18.
                                    community_list=[
                                        "65446:30",
                                        "65441:323",
                                        "65456:323",
                                    ],
                                    network_group_index=0,
                                ),
                            ],
                        ),
                    ),
                    # DG 1: NDP-supporting nexthops (no BGP). Provides
                    # NDP resolution for the 130 NHs the Gold add-path
                    # advertisement points at (128 used + 2 spare for
                    # the overflow case once we re-enable that test).
                    taac_types.DeviceGroupConfig(
                        device_group_index=1,
                        tag_name="NDP_SUPPORTING_NEXTHOP",
                        multiplier=130,
                        v6_addresses_config=taac_types.IpAddressesConfig(
                            starting_ip=ixia_nexthop_supporting_ndp_network,
                            increment_ip="::1",
                            gateway_starting_ip=ixia_nexthop_supporting_ndp_gateway,
                            mask=64,
                        ),
                    ),
                ],
            ),
            # Remote port: secondary L3 traffic source for Silver+Rouge
            taac_types.BasicPortConfig(
                l1_config=DSF_L1_CONFIG,
                endpoint=f"{device_name}:{ixia_remote_interface}",
                device_group_configs=[
                    taac_types.DeviceGroupConfig(
                        device_group_index=0,
                        tag_name="REMOTE_L3_TRAFFIC",
                        enable=True,
                        multiplier=1,
                        v6_addresses_config=taac_types.IpAddressesConfig(
                            starting_ip=f"{ixia_remote_ic_parent_network_v6}::b",
                            increment_ip="::",
                            gateway_starting_ip=f"{ixia_remote_ic_parent_network_v6}::a",
                            gateway_increment_ip="::",
                            mask=64,
                        ),
                    ),
                ],
            ),
        ],
        playbooks=_add_tc_checks_to_playbooks(
            [
                # First-iteration smoke playbook — validates the topology
                # end-to-end (BGP up, NDP resolved, DLB super-group
                # programmed) without yet exercising the
                # disruption/churn loops the W400 factories run. Once
                # this passes cleanly on gtsw001 we'll re-introduce
                # `create_ecmp_groups_playbooks` /
                # `create_ecmp_members_playbooks` /
                # `create_spillover_testing_playbooks` once Silver+Rouge
                # endpoints are added back.
                create_dlb_topology_smoke_playbook(duration_s=120),
            ]
        ),
    )


# =============================================================================
# SECTION 7: TEST CONFIG INSTANCE
# =============================================================================

# IXIA chassis IP for ixia19.netcastle.ash6
IXIA19_CHASSIS_IP: str = "2401:db00:2066:31fb::3019"

# Test config for gtsw001.l1001.c085.ash6 (IcePack GTSW, TH6 / ICECUBE800BC).
# Live verified 2026-06-18:
#   MAC `02:00:00:00:0f:0c` (from fe80::ff:fe00:f0c on every IXIA-facing port).
#   eth1/1/1 -> ixia19 1/25 (Downlink/Source)     Gateway: 2401:db00:206a:c000::a/64 (VLAN 2001)
#   eth1/1/3 -> ixia19 1/27 (Rogue/BGP + ECMP)    Gateway: 2401:db00:206a:c002::a/64 (VLAN 2002)
#   eth1/1/5 -> ixia19 1/29 (Remote)              Gateway: 2401:db00:206a:c004::a/64 (VLAN 2003)
NPI_DVT_ICEPACK_GTSW__ECMP_RESOURCE_TESTING: TestConfig = (
    test_config_for_icepack_ecmp_resource_testing(
        test_config_name="NPI_DVT_ICEPACK_GTSW__ECMP_RESOURCE_TESTING",
        device_name="gtsw001.l1001.c085.ash6",
        local_mac_address="02:00:00:00:0f:0c",
        ixia_downlink_interface="eth1/1/1",
        ixia_rogue_interface="eth1/1/3",
        ixia_remote_interface="eth1/1/5",
        ixia_downlink_ic_parent_network_v6="2401:db00:206a:c000",
        ixia_rogue_ic_parent_network_v6="2401:db00:206a:c002",
        ixia_remote_ic_parent_network_v6="2401:db00:206a:c004",
        ixia_nexthop_supporting_ndp_network="2401:db00:206a:c002::a001",
        ixia_nexthop_supporting_ndp_gateway="2401:db00:206a:c002::a",
        # Matches the IXIA-side ASN used by mp3n_prefix_profiling on this
        # same DUT.
        remote_uplink_as_4byte=4200601902,
        is_uplink_peer_confed="False",
        prefix_limit="75000",
        basset_pool="taac_netcastle_ash6",
        direct_ixia_connections=[
            taac_types.DirectIxiaConnection(
                interface="eth1/1/1",
                ixia_chassis_ip=IXIA19_CHASSIS_IP,
                ixia_port="1/25",
            ),
            taac_types.DirectIxiaConnection(
                interface="eth1/1/3",
                ixia_chassis_ip=IXIA19_CHASSIS_IP,
                ixia_port="1/27",
            ),
            taac_types.DirectIxiaConnection(
                interface="eth1/1/5",
                ixia_chassis_ip=IXIA19_CHASSIS_IP,
                ixia_port="1/29",
            ),
        ],
    )
)
