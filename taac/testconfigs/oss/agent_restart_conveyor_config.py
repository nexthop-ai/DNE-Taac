"""Service-restart smoke routed through Meta's conveyor TestConfig factory.

Calls ``test_config_for_bgp_and_fboss_platform_hardening_in_conveyor()``
with values resolved from the OSS topology CSVs
(``taac/oss_topology_info/{device_info,circuit_info}.csv``) and passes
``playbooks=[<4 agent-restart playbooks>]`` to opt out of the factory's
default playbook bundle. Playbooks included:

  - TEST_FBOSS_SW_AGENT_WARMBOOT_PLAYBOOK   (Service.FBOSS_SW_AGENT)
  - TEST_FBOSS_SW_AGENT_CRASH_PLAYBOOK      (Service.FBOSS_SW_AGENT)
  - TEST_FBOSS_HW_AGENT_0_RESTART_PLAYBOOK  (Service.FBOSS_HW_AGENT_0)
  - TEST_FBOSS_HW_AGENT_0_CRASH_PLAYBOOK    (Service.FBOSS_HW_AGENT_0)

The two Service.AGENT-keyed playbooks (TEST_AGENT_WARMBOOT_PLAYBOOK,
TEST_AGENT_CRASH_PLAYBOOK) were originally included but had to be
dropped after PR #61's service-rename was reverted on origin/main.
Service.AGENT now maps back to "wedge_agent", which doesn't exist as
a systemd unit on the current FBOSS DUT image — only fboss_sw_agent
and fboss_hw_agent@0 do. Add them back when the upstream enum
mapping is sorted out.

DUT is picked from the ``TAAC_DUT`` env var (matching the
oss_entry_point CLI's ``--dut`` value if set via the wrapper);
``get_mac_from_hostname_oss`` and ``get_circuits_for_hostname_oss``
then resolve MAC + ixia interfaces from the CSV fixtures. The
first two ixia ports become ``ixia_downlink_interface`` and
``ixia_uplink_interface`` respectively — the conveyor factory
requires both, but our restart playbooks don't actually push any
ixia traffic.

The remaining 54 BGP-topology params (peer-group names, route
maps, prefix counts, etc.) are required positional args of the
factory but are only consumed by the default playbook chain
(replaced by our explicit ``playbooks=[...]`` list) and by the
BGP-specific ``tc_prechecks``/``tc_postchecks`` the factory merges
into each playbook (which we strip after the factory returns) —
so all 54 are passed as ``None``. Validated by a sweep that None'd
each kwarg individually + all together (build succeeded in every
case) and by a live 4-playbook run against fboss101.

Depends on ``taac.playbooks.playbook_definitions``,
``taac.stages.stage_definitions``, and
``taac.routing.dc_routing.bgp_dc.shared_constants`` — the conveyor
factory imports symbols from those modules at load time. These were
compat stubs earlier in the OSS effort; PR #96 replaced them with the
real upstream files at their real paths.

Live runs need ``--skip-ixia-setup --skip-setup-tasks`` so the
factory's BGP-peering setup_tasks don't try to peer against an
un-BGP-configured DUT.
"""

import os

from taac.playbooks.playbook_definitions import (
    TEST_FBOSS_HW_AGENT_0_CRASH_PLAYBOOK,
    TEST_FBOSS_HW_AGENT_0_RESTART_PLAYBOOK,
    TEST_FBOSS_SW_AGENT_CRASH_PLAYBOOK,
    TEST_FBOSS_SW_AGENT_WARMBOOT_PLAYBOOK,
)
from taac.oss_topology_info.circuit_info_loader import ixia_interfaces_from_csv
from taac.oss_topology_info.device_info_loader import get_mac_from_hostname_oss
from taac.testconfigs.fboss_solution_tests.fboss_bgp_and_platform_hardening_conveyor import (
    test_config_for_bgp_and_fboss_platform_hardening_in_conveyor,
)


def test_config():
    # DUT picked from TAAC_DUT env (the oss_entry_point CLI propagates
    # --dut here via the wrapper script). Downstream framework errors
    # are clear enough that an explicit "TAAC_DUT not set" check would
    # be redundant; same for missing ixia circuits in circuit_info.csv
    # — unpacking ixia_interfaces[:2] fails with a clear ValueError.
    dut_name = os.environ.get("TAAC_DUT")
    local_mac_address = get_mac_from_hostname_oss(dut_name)
    ixia_downlink_interface, ixia_uplink_interface = ixia_interfaces_from_csv(
        dut_name
    )[:2]

    tc = test_config_for_bgp_and_fboss_platform_hardening_in_conveyor(
        test_config_name="IXIA_RESTART_CONVEYOR",
        device_name=dut_name,
        local_mac_address=local_mac_address,
        ixia_downlink_interface=ixia_downlink_interface,
        ixia_uplink_interface=ixia_uplink_interface,
        # The 54 BGP-topology kwargs below are required positional args of
        # the factory but are only consumed by the default playbook chain
        # and the BGP-specific tc_pre/postchecks — both replaced/stripped
        # for our agent-restart smoke, so all 54 are passed as ``None``.
        peergroup_uplink_mimic_v6=None,
        peergroup_uplink_mimic_v4=None,
        peergroup_downlink_mimic_v6=None,
        peergroup_downlink_mimic_v4=None,
        peergroup_rogue_mimic_v6=None,
        peergroup_rogue_mimic_v4=None,
        route_map_uplink_ingress=None,
        route_map_uplink_egress=None,
        route_map_downlink_ingress=None,
        route_map_downlink_egress=None,
        route_map_rogue_ingress=None,
        route_map_rogue_egress=None,
        ixia_downlink_ic_parent_network_v6=None,
        ixia_uplink_ic_parent_network_v6=None,
        ixia_rogue_ic_parent_network_v6=None,
        ixia_downlink_ic_parent_network_v4=None,
        ixia_uplink_ic_parent_network_v4=None,
        ixia_rogue_ic_parent_network_v4=None,
        good_ndp_entry_network_v6=None,
        rogue_ndp_entry_network_v6=None,
        good_arp_entry_network_v4=None,
        rogue_arp_entry_network_v4=None,
        prefix_limit=None,
        per_peer_max_route_limit=None,
        downlink_peer_count=None,
        uplink_peer_count=None,
        rogue_peer_count=None,
        remote_downlink_as_4byte=None,
        remote_uplink_as_4byte=None,
        remote_rogue_as_4byte=None,
        is_uplink_peer_confed=None,
        is_downlink_peer_confed=None,
        is_rogue_peer_confed=None,
        ixia_downlink_prefix_count_v6=None,
        ixia_uplink_prefix_count_v6=None,
        ixia_rogue_prefix_count_v6=None,
        ixia_downlink_prefix_count_v4=None,
        ixia_uplink_prefix_count_v4=None,
        ixia_rogue_prefix_count_v4=None,
        ixia_uplink_good_ndp_network=None,
        ixia_downlink_good_ndp_network=None,
        ixia_downlink_communities=None,
        ixia_uplink_communities=None,
        downlink_peer_tag=None,
        uplink_peer_tag=None,
        ecmp_group_limit=None,
        good_ndp_entries_uplink=None,
        good_ndp_entries_downlink=None,
        rogue_ndp_entries=None,
        good_arp_entries=None,
        rogue_arp_entries=None,
        good_mac_entry_count=None,
        rogue_mac_entry_count=None,
        bgp_induced_ecmp_group_count=None,
        # WARMBOOT + RESTART ship ``enabled=False`` in
        # playbook_definitions.py, so we call them ``(enabled=True)`` to
        # flip them on. The two CRASH playbooks don't set ``enabled`` and
        # inherit the thrift default ``enabled = true`` (see
        # test_as_a_config.thrift), so they're passed bare.
        playbooks=[
            TEST_FBOSS_SW_AGENT_WARMBOOT_PLAYBOOK(enabled=True),
            TEST_FBOSS_SW_AGENT_CRASH_PLAYBOOK,
            TEST_FBOSS_HW_AGENT_0_RESTART_PLAYBOOK(enabled=True),
            TEST_FBOSS_HW_AGENT_0_CRASH_PLAYBOOK,
        ],
        basset_pool="",
    )
    return tc(
        playbooks=[pb(prechecks=[], postchecks=[]) for pb in tc.playbooks],
    )
