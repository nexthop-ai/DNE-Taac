# Copyright (c) Meta Platforms, Inc. and affiliates.
# pyre-unsafe

"""Tests for the OSS coop patcher: the on-DUT mutation script (run for real
via subprocess) and the generated shell commands."""

import json
import subprocess
import sys

import pytest

from taac.driver import oss_coop_patcher as ocp


def run_script(tmp_path, base, patchers):
    (tmp_path / "base.conf").write_text(json.dumps(base))
    (tmp_path / "p.json").write_text(json.dumps(patchers))
    (tmp_path / "script.py").write_text(ocp._PATCH_SCRIPT)
    r = subprocess.run(
        [
            sys.executable,
            str(tmp_path / "script.py"),
            str(tmp_path / "base.conf"),
            str(tmp_path / "out.conf"),
            str(tmp_path / "p.json"),
        ],
        capture_output=True,
        text=True,
    )
    assert r.returncode == 0, r.stderr
    assert r.stdout.splitlines()[-1].startswith("OK ")
    return json.loads((tmp_path / "out.conf").read_text())


def patcher(name, func, args):
    return {"name": name, "py_func_name": func, "args": args}


def test_add_bgp_peers_both_shapes(tmp_path):
    concrete = [
        {
            "local_addr": "2001:db8:3::1",
            "peer_addr": "2001:db8:3::2",
            "peer_group_name": "PG1",
            "remote_as_4_byte": "65000",
            "description": "dl",
        },
        {
            "local_addr": "2001:db8:4::1",
            "peer_addr": "2001:db8:4::2",
            "peer_group_name": "PG1",
            "remote_as_4_byte": "65001",
            "description": "ul",
        },
    ]
    spec = [
        {
            "starting_ip": "10.0.0.0",
            "gateway_starting_ip": "10.0.0.1",
            "increment_ip": "0.0.0.2",
            "num_sessions": 2,
            "remote_as_4_byte": 65100,
            "remote_as_4_byte_step": 1,
            "peer_group_name": "PG1",
            "description": "spec",
        }
    ]
    out = run_script(
        tmp_path,
        {"peers": [{"peer_addr": "old"}]},
        [
            patcher("rm", "remove_bgp_peers", {"delete_all": "True"}),
            patcher("a", "add_bgp_peers", {"peer_configs": json.dumps(concrete)}),
            patcher("b", "add_bgp_peers", {"peer_configs": json.dumps(spec)}),
        ],
    )
    peers = out["peers"]
    assert [p["peer_addr"] for p in peers] == [
        "2001:db8:3::2",
        "2001:db8:4::2",
        "10.0.0.1",
        "10.0.0.3",
    ]
    # peer_id numbering restarts per description in the concrete branch
    assert peers[0]["peer_id"] == "dl:1"
    assert peers[1]["peer_id"] == "ul:1"
    assert [p["remote_as_4_byte"] for p in peers[2:]] == [65100, 65101]


def test_configure_vlans_merges_not_replaces(tmp_path):
    base = {
        "sw": {
            "interfaces": [{"vlanID": 2000, "ipAddresses": ["fd00::1/64"]}],
            "vlans": [{"id": 2000, "ipAddresses": ["fd00::1"]}],
        }
    }
    dl = {"vlan_id": 2000, "ip_addresses": ["fd00::1/64", "2001:db8:3::1/127"]}
    ul = {"vlan_id": 2000, "ip_addresses": ["fd00::1/64", "2001:db8:4::1/127"]}
    out = run_script(
        tmp_path,
        base,
        [
            patcher("dl", "configure_vlans", {"vlan2000": json.dumps(dl)}),
            patcher("ul", "configure_vlans", {"vlan2000": json.dumps(ul)}),
        ],
    )
    intf = out["sw"]["interfaces"][0]
    vlan = out["sw"]["vlans"][0]
    assert "2001:db8:3::1/127" in intf["ipAddresses"]
    assert "2001:db8:4::1/127" in intf["ipAddresses"]
    assert "2001:db8:3::1" in vlan["ipAddresses"]
    assert "2001:db8:4::1" in vlan["ipAddresses"]


def test_unknown_py_func_fails_loudly(tmp_path):
    with pytest.raises(NotImplementedError):
        ocp.register(
            "h1",
            "bgpcpp",
            ocp.OssPatcher(name="x", config_name="bgpcpp", py_func_name="nope"),
        )
    ocp.clear("h1")


def test_registry_register_replace_unregister():
    p = ocp.OssPatcher(name="a", config_name="bgpcpp", py_func_name="remove_bgp_peers")
    ocp.register("h2", "bgpcpp", p)
    ocp.register("h2", "bgpcpp_softdrain", p)  # ignored
    ocp.register("h2", "bgpcpp_drain", p)  # ignored
    ocp.register("h2", "bgpcpp", p)  # replaces, not duplicates
    assert ocp.pending_configs("h2") == ["bgpcpp"]
    assert len(ocp.list_patchers("h2", "bgpcpp")) == 1
    ocp.unregister("h2", "bgpcpp", "a")
    assert ocp.pending_configs("h2") == []
    ocp.clear("h2")


def test_build_commands():
    live, baseline, patched = ocp.variant_paths("bgpcpp")
    assert (live, baseline, patched) == (
        "/etc/coop/bgpcpp.conf",
        "/etc/coop/bgpcpp.baseline.conf",
        "/etc/coop/bgpcpp.patched.conf",
    )
    apply_cmd = ocp.build_apply_command(
        "bgpcpp",
        [ocp.OssPatcher(name="a", config_name="bgpcpp", py_func_name="remove_bgp_peers")],
    )
    # seeds the live path from the older-image sibling before snapshotting
    assert f"[ -e {live} ] || cp -a /etc/coop/bgpd.conf {live}" in apply_cmd
    assert f"[ -f {baseline} ] || cp -a {live} {baseline}" in apply_cmd
    activate = ocp.build_activate_command("bgpcpp")
    assert f"cp -a {patched} {live}" in activate
    assert activate.endswith("echo ACTIVATED")
    restore = ocp.build_restore_command("bgpcpp")
    assert f"cp -a {baseline} {live}" in restore


# ---------------------------------------------------------------------------
# add_bgp_policy_statement
#
# Splices a policy statement the baseline does not carry -- the mechanism the
# BGP-DC factory uses for its PROPAGATE_EVERYTHING_* policies, and the one an
# IXIA-mimic peer group needs when the DUT's production import policy rejects
# every mimic prefix.
# ---------------------------------------------------------------------------

_PERMIT_ALL_TERM = {
    "name": "RULE_ACCEPT_ALL",
    "description": "Unconditionally accept all prefixes",
    "policy_match_entries": {
        "name": "",
        "description": "",
        "match_logic_type": 1,
        "match_entries": [{"type": 20, "match_logic_type": 0}],  # 20 = ALWAYS
    },
}


def _add_policy_patcher(name="PROPAGATE_EVERYTHING_IN", description="accept all"):
    return patcher(
        f"a_add_bgp_policy_statement_{name}",
        "add_bgp_policy_statement",
        {
            "name": name,
            "description": description,
            "policy_entries": json.dumps([_PERMIT_ALL_TERM]),
        },
    )


def _stmts(cfg):
    return cfg["policies"]["bgp_policy_statements"]


def test_add_bgp_policy_statement_creates_statement(tmp_path):
    out = run_script(
        tmp_path,
        {"policies": {"bgp_policy_statements": []}},
        [_add_policy_patcher()],
    )
    stmts = _stmts(out)
    assert [s["name"] for s in stmts] == ["PROPAGATE_EVERYTHING_IN"]
    assert stmts[0]["description"] == "accept all"
    assert stmts[0]["policy_entries"] == [_PERMIT_ALL_TERM]


def test_add_bgp_policy_statement_defaults_to_accept(tmp_path):
    """result=2 is DENY. A permit-all policy defaulted to DENY would reject
    every prefix while looking correct -- every prefix received, none
    accepted, and no error anywhere. Neither caller passes result, so the
    default is load-bearing."""
    out = run_script(
        tmp_path,
        {"policies": {"bgp_policy_statements": []}},
        [_add_policy_patcher()],
    )
    assert _stmts(out)[0]["result"] == 1
    assert _stmts(out)[0]["policy_version"] == "1"


def test_add_bgp_policy_statement_replaces_same_name(tmp_path):
    out = run_script(
        tmp_path,
        {"policies": {"bgp_policy_statements": []}},
        [
            _add_policy_patcher(description="first"),
            _add_policy_patcher(description="second"),
        ],
    )
    stmts = _stmts(out)
    assert len(stmts) == 1
    assert stmts[0]["description"] == "second"


def test_add_bgp_policy_statement_keeps_existing_statements(tmp_path):
    out = run_script(
        tmp_path,
        {
            "policies": {
                "bgp_policy_statements": [
                    {"name": "PROPAGATE_RSW_SLB_IN", "result": 2},
                ]
            }
        },
        [_add_policy_patcher()],
    )
    assert [s["name"] for s in _stmts(out)] == [
        "PROPAGATE_RSW_SLB_IN",
        "PROPAGATE_EVERYTHING_IN",
    ]


def test_add_bgp_policy_statement_creates_policies_container(tmp_path):
    """A config with no policies section at all must not KeyError."""
    out = run_script(tmp_path, {}, [_add_policy_patcher()])
    assert [s["name"] for s in _stmts(out)] == ["PROPAGATE_EVERYTHING_IN"]


def test_add_bgp_policy_statement_is_registerable():
    """Registration gates on SUPPORTED_PY_FUNCS, a separate list from FUNCS in
    the on-DUT script -- porting one without the other raises here."""
    ocp.clear("h3")
    ocp.register(
        "h3",
        "bgpcpp",
        ocp.OssPatcher(
            name="a_add_bgp_policy_statement_PROPAGATE_EVERYTHING_IN",
            config_name="bgpcpp",
            py_func_name="add_bgp_policy_statement",
        ),
    )
    assert len(ocp.list_patchers("h3", "bgpcpp")) == 1
    ocp.clear("h3")


def test_remove_bgp_peers_targeted_keeps_the_rest(tmp_path):
    """`peer_addrs` mode drops only the named peers.

    Characterization test, not a red-green cycle: this mode predates the
    permissive-ingress work. It is covered because the fabric-intact CPU-queue
    variant relies on it to strip the passive listeners while leaving the 32
    fabric sessions in place -- `delete_all` would take the DUT out of the Clos.
    """
    base = {
        "peers": [
            {"peer_addr": "2401:db00:711c:402::/64", "type": "SHIV_FABRIC_V6"},
            {"peer_addr": "2401:db00:1ff:c100::/56", "type": "BGP_MONITOR"},
            {"peer_addr": "2401:db00:e718:101:1000::10",
             "peer_group_name": "PEERGROUP_RSW_FSW_V6"},
            {"peer_addr": "2401:db00:e718:101:1000::18",
             "peer_group_name": "PEERGROUP_RSW_FSW_V6"},
        ]
    }
    out = run_script(
        tmp_path,
        base,
        [
            patcher(
                "rm",
                "remove_bgp_peers",
                {
                    "peer_addrs": json.dumps(
                        ["2401:db00:711c:402::/64", "2401:db00:1ff:c100::/56"]
                    )
                },
            )
        ],
    )
    assert [p["peer_addr"] for p in out["peers"]] == [
        "2401:db00:e718:101:1000::10",
        "2401:db00:e718:101:1000::18",
    ]


# ---------------------------------------------------------------------------
# change_port_admin_state -- agent.conf. PortState from the FBOSS thrift enum:
# DOWN=0, DISABLED=1, ENABLED=2.
# ---------------------------------------------------------------------------


def _agent_with_ports():
    return {
        "sw": {
            "ports": [
                {"name": "eth1/32/1", "logicalID": 70, "state": 1},
                {"name": "eth1/32/5", "logicalID": 74, "state": 1},
                {"name": "eth1/1/1", "logicalID": 266, "state": 2},
            ]
        }
    }


def _states(cfg):
    return {p["name"]: p["state"] for p in cfg["sw"]["ports"]}


def test_change_port_admin_state_enables_and_disables(tmp_path):
    out = run_script(
        tmp_path,
        _agent_with_ports(),
        [
            patcher(
                "ports",
                "change_port_admin_state",
                {"eth1/32/1": "enable", "eth1/1/1": "disable"},
            )
        ],
    )
    assert _states(out) == {
        "eth1/32/1": 2,  # enabled
        "eth1/32/5": 1,  # untouched
        "eth1/1/1": 1,  # disabled
    }


def run_script_failing(tmp_path, base, patchers):
    """Run the on-DUT script expecting a non-zero exit; return stderr.

    `run_script` asserts rc==0, so a test using it to detect an expected
    failure passes on ANY failure -- including the patcher simply not being
    ported. Asserting on the message keeps that distinction.
    """
    (tmp_path / "base.conf").write_text(json.dumps(base))
    (tmp_path / "p.json").write_text(json.dumps(patchers))
    (tmp_path / "script.py").write_text(ocp._PATCH_SCRIPT)
    r = subprocess.run(
        [
            sys.executable,
            str(tmp_path / "script.py"),
            str(tmp_path / "base.conf"),
            str(tmp_path / "out.conf"),
            str(tmp_path / "p.json"),
        ],
        capture_output=True,
        text=True,
    )
    assert r.returncode != 0, f"expected failure, got rc=0: {r.stdout}"
    return r.stderr


def test_change_port_admin_state_rejects_unknown_port(tmp_path):
    """Silently skipping would let a run proceed with the port still down,
    which is the failure this module's NotImplementedError guard exists to
    prevent -- surface it instead."""
    err = run_script_failing(
        tmp_path,
        _agent_with_ports(),
        [patcher("ports", "change_port_admin_state", {"eth9/99/1": "enable"})],
    )
    assert "eth9/99/1" in err, err


# ---------------------------------------------------------------------------
# add_bgp_policy_match_prefix_to_propagate_routes
#
# Term shape matches generated patches that open a down-leg policy to an
# additional prefix range, confirmed working on hardware. Note the empty
# policy_action_entries: a term that matches permits by default
# (config_modifiers.build_propagate_policies, citing PolicyTerm.cpp).
# ---------------------------------------------------------------------------


def _policy_cfg():
    return {
        "policies": {
            "bgp_policy_statements": [
                {"name": "PROPAGATE_RSW_FSW_IN", "policy_entries": [{"name": "EXISTING"}]},
                {"name": "PROPAGATE_NOTHING", "policy_entries": []},
            ]
        }
    }


def _terms(cfg, stmt):
    s = next(x for x in cfg["policies"]["bgp_policy_statements"] if x["name"] == stmt)
    return s["policy_entries"]


def _match_prefix_patcher(in_stmt="PROPAGATE_RSW_FSW_IN", out_stmt="RANDOM",
                          prefix="5000::/16"):
    return patcher(
        f"add_bgp_policy_match_prefix_to_propagate_routes_{in_stmt}",
        "add_bgp_policy_match_prefix_to_propagate_routes",
        {"matching_prefix": prefix, "in_stmt_name": in_stmt, "out_stmt_name": out_stmt},
    )


def test_match_prefix_adds_a_permit_term(tmp_path):
    out = run_script(tmp_path, _policy_cfg(), [_match_prefix_patcher()])
    terms = _terms(out, "PROPAGATE_RSW_FSW_IN")
    assert len(terms) == 2, terms
    new = [t for t in terms if t.get("name") != "EXISTING"][0]
    pf = new["policy_match_entries"]["match_entries"][0]["prefix_filters"]
    assert pf["prefixes"][0]["base_prefix"] == "5000::/16"
    assert pf["prefixes"][0]["prefix_len_ranges"][0]["value"] == 16
    assert new["policy_action_entries"] == []


def test_match_prefix_permit_term_is_evaluated_first(tmp_path):
    """Prepended, not appended: an earlier reject term would otherwise win and
    the prefix would still not propagate, which is the whole point."""
    out = run_script(tmp_path, _policy_cfg(), [_match_prefix_patcher()])
    assert _terms(out, "PROPAGATE_RSW_FSW_IN")[-1]["name"] == "EXISTING"


def test_match_prefix_ignores_the_random_sentinel(tmp_path):
    """Callers pass out_stmt_name='RANDOM' to mean 'no egress statement', so
    that ONE name is skipped rather than erroring. No statement is created for
    it."""
    out = run_script(tmp_path, _policy_cfg(), [_match_prefix_patcher()])
    assert [s["name"] for s in out["policies"]["bgp_policy_statements"]] == [
        "PROPAGATE_RSW_FSW_IN",
        "PROPAGATE_NOTHING",
    ]


def test_match_prefix_raises_on_any_other_absent_statement(tmp_path):
    """Only the sentinel is skipped. Silently skipping a real-looking name
    drops the permit this patcher exists to add, and the config then reads as
    though the prefix had been allowed -- which is how a permissive-ingress
    alias turned an in_stmt_name of '<policy>_DRAIN' into a statement nothing
    splices, with no log line."""
    err = run_script_failing(
        tmp_path,
        _policy_cfg(),
        [_match_prefix_patcher(in_stmt="PROPAGATE_RSW_FSW_IN_DRAIN")],
    )
    assert "PROPAGATE_RSW_FSW_IN_DRAIN" in err
    assert "silently drop" in err.lower()


def test_match_prefix_applies_to_both_named_statements(tmp_path):
    out = run_script(
        tmp_path,
        _policy_cfg(),
        [_match_prefix_patcher(out_stmt="PROPAGATE_NOTHING")],
    )
    assert len(_terms(out, "PROPAGATE_RSW_FSW_IN")) == 2
    assert len(_terms(out, "PROPAGATE_NOTHING")) == 1


def test_match_prefix_parses_v4_prefix_length(tmp_path):
    out = run_script(
        tmp_path, _policy_cfg(), [_match_prefix_patcher(prefix="192.0.2.0/24")]
    )
    new = [t for t in _terms(out, "PROPAGATE_RSW_FSW_IN") if t.get("name") != "EXISTING"][0]
    pf = new["policy_match_entries"]["match_entries"][0]["prefix_filters"]
    assert pf["prefixes"][0]["prefix_len_ranges"][0]["value"] == 24


# ---------------------------------------------------------------------------
# configure_vlans: moving a port onto a dedicated vlan.
#
# Each IXIA port needs its own vlan + SVI (eth1/32/1 -> 2100 "ixia_downlink",
# eth1/32/5 -> 2101 "ixia_uplink") so downlink<->uplink traffic is ROUTED
# through the DUT. That is what DIRECTIONAL_TRAFFIC_BETWEEN_DOWNLINK_AND_UPLINK
# measures. With both ports sharing vlan2000 there is no routed path and the
# playbook fails its packet-loss precheck.
#
# Where a testbed baseline already ships that split, the move below is a
# no-op and configure_vlans only merges addresses. The move still has to
# work: it is the path for any testbed whose baseline does not pre-split, and
# shared-vlan input is what these cases pin.
# ---------------------------------------------------------------------------


def _agent_shared_vlan():
    """Two IXIA ports sharing one vlan, as an un-split baseline leaves them."""
    return {
        "sw": {
            "ports": [
                {"name": "eth1/32/1", "logicalID": 70, "ingressVlan": 2000, "state": 2},
                {"name": "eth1/32/5", "logicalID": 74, "ingressVlan": 2000, "state": 2},
                {"name": "eth1/1/1", "logicalID": 266, "ingressVlan": 4001, "state": 2},
            ],
            "vlans": [
                {"id": 2000, "name": "downlinks", "intfID": 2000,
                 "ipAddresses": ["2001:db8:3::1"], "recordStats": True, "routable": True}
            ],
            "vlanPorts": [
                {"vlanID": 2000, "logicalPort": 70, "spanningTreeState": 2, "emitTags": False},
                {"vlanID": 2000, "logicalPort": 74, "spanningTreeState": 2, "emitTags": False},
            ],
            "interfaces": [
                {"intfID": 2000, "vlanID": 2000, "name": "downlinks",
                 "ipAddresses": ["2001:db8:3::1/64"]}
            ],
        }
    }


def _move_patcher(vlan_name, vlan_id, port_id, addrs):
    return patcher(
        f"configure_vlans_{vlan_name}",
        "configure_vlans",
        {
            vlan_name: json.dumps(
                {
                    "vlan_id": vlan_id,
                    "ports": [port_id],
                    "ip_addresses": addrs,
                    "mtu": 9000,
                }
            )
        },
    )


def test_configure_vlans_moves_port_to_dedicated_vlan(tmp_path):
    out = run_script(
        tmp_path,
        _agent_shared_vlan(),
        [_move_patcher("ixia_downlink", 2100, 70, ["2001:db8:0:1108::10/127"])],
    )
    sw = out["sw"]
    port = next(p for p in sw["ports"] if p["logicalID"] == 70)
    assert port["ingressVlan"] == 2100, sw["ports"]
    # the other IXIA port must be left alone
    assert next(p for p in sw["ports"] if p["logicalID"] == 74)["ingressVlan"] == 2000


def test_configure_vlans_creates_vlan_and_svi_for_new_vlan(tmp_path):
    out = run_script(
        tmp_path,
        _agent_shared_vlan(),
        [_move_patcher("ixia_downlink", 2100, 70, ["2001:db8:0:1108::10/127"])],
    )
    sw = out["sw"]
    vlan = next(v for v in sw["vlans"] if v["id"] == 2100)
    assert vlan["name"] == "ixia_downlink"
    assert vlan["intfID"] == 2100
    assert "2001:db8:0:1108::10" in vlan["ipAddresses"]  # vlans carry bare IPs
    intf = next(i for i in sw["interfaces"] if i["vlanID"] == 2100)
    assert "2001:db8:0:1108::10/127" in intf["ipAddresses"]  # interfaces carry masks


def test_configure_vlans_reassigns_vlanport_membership(tmp_path):
    """The port must leave vlan2000, or it stays in two L2 domains."""
    out = run_script(
        tmp_path,
        _agent_shared_vlan(),
        [_move_patcher("ixia_downlink", 2100, 70, ["2001:db8:0:1108::10/127"])],
    )
    vps = {(x["vlanID"], x["logicalPort"]) for x in out["sw"]["vlanPorts"]}
    assert (2100, 70) in vps
    assert (2000, 70) not in vps
    assert (2000, 74) in vps  # untouched


def test_configure_vlans_two_ports_get_separate_vlans(tmp_path):
    out = run_script(
        tmp_path,
        _agent_shared_vlan(),
        [
            _move_patcher("ixia_downlink", 2100, 70, ["2001:db8:0:1108::10/127"]),
            _move_patcher("ixia_uplink", 2101, 74, ["2001:db8:0:1109::10/127"]),
        ],
    )
    sw = out["sw"]
    assert next(p for p in sw["ports"] if p["logicalID"] == 70)["ingressVlan"] == 2100
    assert next(p for p in sw["ports"] if p["logicalID"] == 74)["ingressVlan"] == 2101
    vps = {(x["vlanID"], x["logicalPort"]) for x in sw["vlanPorts"]}
    assert {(2100, 70), (2101, 74)} <= vps
    assert not {(2000, 70), (2000, 74)} & vps


# ---------------------------------------------------------------------------
# change_port_queue_config -- agent.conf.
#
# Why this patcher exists: a port's queue-config binding carries a rate
# shaper, not just queue names. Where every queue in that config sets
# portQueueRate.kbitsPerSec {min,max}, the port's egress is hard-capped at
# that rate, so a port bound to a config sized for a slower link forwards at
# the cap and drops the rest -- at a ratio fixed by cap/offered-rate, which
# reads as a large, perfectly steady packet-loss percentage rather than as any
# configuration error. Rebinding to a queue config that declares no
# portQueueRate is what removes the cap.
# ---------------------------------------------------------------------------


def _agent_with_queue_configs():
    return {
        "sw": {
            "ports": [
                {
                    "name": "eth1/32/1",
                    "logicalID": 70,
                    "portQueueConfigName": "downlink_queue_config",
                },
                {
                    "name": "eth1/32/5",
                    "logicalID": 74,
                    "portQueueConfigName": "downlink_queue_config",
                },
                {
                    "name": "eth1/1/1",
                    "logicalID": 266,
                    "portQueueConfigName": "uplink_sp_olympic",
                },
            ],
            "portQueueConfigs": {
                "downlink_queue_config": [{"id": 0, "name": "queue_per_host"}],
                "uplink_sp_olympic": [{"id": 0, "name": "ncnf"}],
            },
        }
    }


def _queue_names(cfg):
    return {p["name"]: p.get("portQueueConfigName") for p in cfg["sw"]["ports"]}


def test_change_port_queue_config_rebinds_named_ports(tmp_path):
    out = run_script(
        tmp_path,
        _agent_with_queue_configs(),
        [
            patcher(
                "queues",
                "change_port_queue_config",
                {"eth1/32/1": "uplink_sp_olympic", "eth1/32/5": "uplink_sp_olympic"},
            )
        ],
    )
    assert _queue_names(out) == {
        "eth1/32/1": "uplink_sp_olympic",
        "eth1/32/5": "uplink_sp_olympic",
        "eth1/1/1": "uplink_sp_olympic",  # untouched, already correct
    }


def test_change_port_queue_config_unknown_port_raises(tmp_path):
    """An unknown port name must fail loudly.

    Silently skipping would leave the port on a shaped queue config and the run
    would fail ~30 minutes later as unexplained packet loss -- which is exactly
    how long this took to find the first time.
    """
    err = run_script_failing(
        tmp_path,
        _agent_with_queue_configs(),
        [patcher("queues", "change_port_queue_config", {"eth9/9/9": "uplink_sp_olympic"})],
    )
    assert "eth9/9/9" in err


def test_change_port_queue_config_unknown_queue_config_raises(tmp_path):
    """Naming a queue config that does not exist must fail loudly too.

    FBOSS resolves portQueueConfigName against sw.portQueueConfigs; a typo
    would produce a config the agent rejects (or silently defaults), so catch
    it here where the message can name the available sets.
    """
    err = run_script_failing(
        tmp_path,
        _agent_with_queue_configs(),
        [patcher("queues", "change_port_queue_config", {"eth1/32/1": "no_such_config"})],
    )
    assert "no_such_config" in err
