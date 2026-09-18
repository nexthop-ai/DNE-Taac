"""Pin the resource-coverage contract the w800 TestConfigs now share.

``with_w800_resource_checks`` levels every w800 config up to memory pre/post +
CPU post. The two properties worth pinning are that it ADDS without replacing
-- an upstream factory's tuned ceiling must survive, because it was sized for
the disruption that playbook performs -- and that it is idempotent, since the
configs form a derivation chain (SERVICE_RESTART and BGP_LONGEVITY are built
from PLATFORM_HARDENING, NBR_UPLINK_FLAP from CLUSTER_TRAFFIC) and a config can
be wrapped more than once.
"""

import json
import unittest

from taac.health_checks.healthcheck_definitions import (
    create_cpu_utilization_check,
    create_memory_utilization_check,
)
from taac.health_check.health_check import types as hc_types
from taac.test_as_a_config import types as taac_types
from taac.testconfigs.ai_bb import w800_prefix_profiling_config
from taac.testconfigs.npi import w800_ecmp_resource_testing_config
from taac.testconfigs.npi import w800_resource_checks as rc
from taac.testconfigs.npi import wedge800_npi_test_config as w800cfg
from taac.testconfigs.npi.w800_resource_checks import with_w800_resource_checks
from taac.testconfigs.oss import w800_cluster_traffic_config


MEM = hc_types.CheckName.MEMORY_UTILIZATION_CHECK
CPU = hc_types.CheckName.CPU_UTILIZATION_CHECK

# Every module that defines a w800 TestConfig, so the sweeps below cover the
# whole set rather than whichever config someone remembered to name.
_W800_CONFIG_MODULES = (
    w800cfg,
    w800_ecmp_resource_testing_config,
    w800_cluster_traffic_config,
    w800_prefix_profiling_config,
)

# Deliberately unwrapped: a standalone single-DUT snake soak on its own basset
# pool that no 4-DUT wrapper selects. See w800_resource_checks' module docstring.
_OUT_OF_SCOPE = {"W800_LONGEVITY_TEST_CONFIG"}


def _w800_configs():
    seen = {}
    for module in _W800_CONFIG_MODULES:
        for attr in dir(module):
            if not attr.endswith("_TEST_CONFIG") or attr in _OUT_OF_SCOPE:
                continue
            config = getattr(module, attr)
            if getattr(config, "playbooks", None) is not None:
                seen[attr] = config
    return seen


def _names(checks):
    return [c.name for c in (checks or [])]


def _params(check) -> dict:
    cp = getattr(check, "check_params", None)
    if cp is None or not getattr(cp, "json_params", None):
        return {}
    return json.loads(cp.json_params)


def _config(playbooks):
    return taac_types.TestConfig(
        name="T", playbooks=playbooks, endpoints=[], host_os_type_map={}
    )


def _playbook(name="pb", prechecks=None, postchecks=None):
    return taac_types.Playbook(
        name=name, stages=[], prechecks=prechecks or [], postchecks=postchecks or []
    )


class TestWithW800ResourceChecks(unittest.TestCase):
    def test_bare_playbook_gains_memory_pre_post_and_cpu_post(self) -> None:
        out = with_w800_resource_checks(_config([_playbook()]))
        pb = out.playbooks[0]
        self.assertEqual(_names(pb.prechecks), [MEM])
        self.assertEqual(_names(pb.postchecks), [MEM, CPU])

    def test_cpu_is_not_added_as_a_precheck(self) -> None:
        """No call site in the repo uses one, and a sample taken right after
        setUp measures setup churn rather than the playbook."""
        out = with_w800_resource_checks(_config([_playbook()]))
        self.assertNotIn(CPU, _names(out.playbooks[0].prechecks))

    def test_idempotent(self) -> None:
        once = with_w800_resource_checks(_config([_playbook()]))
        twice = with_w800_resource_checks(once)
        self.assertEqual(_names(twice.playbooks[0].prechecks), [MEM])
        self.assertEqual(_names(twice.playbooks[0].postchecks), [MEM, CPU])

    def test_existing_tuned_check_is_kept_not_replaced(self) -> None:
        tuned = create_memory_utilization_check(
            threshold=9 * (1024**3), threshold_by_service={"fsdb": 3 * (1024**3)}
        )
        out = with_w800_resource_checks(_config([_playbook(postchecks=[tuned])]))
        mem = [c for c in out.playbooks[0].postchecks if c.name == MEM]
        self.assertEqual(len(mem), 1)
        self.assertEqual(_params(mem[0])["threshold"], 9 * (1024**3))

    def test_existing_cpu_postcheck_is_kept(self) -> None:
        tuned = create_cpu_utilization_check(threshold=123.0)
        out = with_w800_resource_checks(_config([_playbook(postchecks=[tuned])]))
        cpu = [c for c in out.playbooks[0].postchecks if c.name == CPU]
        self.assertEqual(len(cpu), 1)
        self.assertEqual(_params(cpu[0])["threshold"], 123.0)

    def test_source_config_is_not_mutated(self) -> None:
        src = _config([_playbook()])
        with_w800_resource_checks(src)
        self.assertEqual(_names(src.playbooks[0].prechecks), [])

    def test_added_checks_are_report_only_by_default(self) -> None:
        """Ceilings here are borrowed from the BGP-DC lineage, not measured for
        the families this newly covers, so the added checks record rather than
        gate until a baseline exists."""
        self.assertFalse(rc.W800_GATE_ADDED_RESOURCE_CHECKS)
        pb = with_w800_resource_checks(_config([_playbook()])).playbooks[0]
        for check in list(pb.prechecks) + list(pb.postchecks):
            params = _params(check)
            self.assertEqual(params.get("threshold"), 0.0)
            self.assertFalse(params.get("threshold_by_service"))


class TestW800ConfigsAreCovered(unittest.TestCase):
    """Integration: the real configs, as oss_entry_point loads them."""

    def test_every_in_scope_config_is_covered(self) -> None:
        """The PR's central claim, as a regression guard: a new w800 config, or
        one that stops being wrapped, fails here."""
        configs = _w800_configs()
        self.assertGreaterEqual(len(configs), 17, sorted(configs))
        for name, config in sorted(configs.items()):
            for pb in config.playbooks or []:
                self.assertIn(MEM, _names(pb.prechecks), f"{name}/{pb.name}")
                self.assertIn(MEM, _names(pb.postchecks), f"{name}/{pb.name}")
                self.assertIn(CPU, _names(pb.postchecks), f"{name}/{pb.name}")

    def test_out_of_scope_config_is_a_real_config(self) -> None:
        """Keeps the exclusion honest: if the snake config is renamed or
        removed, the skip silently stops meaning anything."""
        self.assertTrue(
            all(hasattr(w800cfg, name) for name in _OUT_OF_SCOPE), _OUT_OF_SCOPE
        )

    def test_bgp_hardening_ceilings_are_6gib_except_bgpd(self) -> None:
        """One 6 GiB ceiling for every service in both stages, bgpd the sole
        exception. Reintroducing a per-service entry -- or letting the two
        stages drift apart again, as the old fsdb 7/5 split did -- fails here."""
        for pb in w800cfg.W800_BGP_HARDENING_TEST_CONFIG.playbooks:
            pre = [c for c in pb.prechecks if c.name == MEM]
            post = [c for c in pb.postchecks if c.name == MEM]
            self.assertEqual((len(pre), len(post)), (1, 1), pb.name)
            for stage, check in (("prechecks", pre[0]), ("postchecks", post[0])):
                params = _params(check)
                self.assertEqual(
                    params["threshold"], 6 * (1024**3), f"{pb.name}/{stage}"
                )
                self.assertEqual(
                    params["threshold_by_service"],
                    {"bgpd": 4.5 * (1024**3)},
                    f"{pb.name}/{stage}",
                )

    def test_no_stage_carries_a_duplicate_resource_check(self) -> None:
        """The runner dedups same-named checks last-wins, so a duplicate would
        silently decide which ceiling applies."""
        for name, config in sorted(_w800_configs().items()):
            for pb in config.playbooks or []:
                for stage in (pb.prechecks, pb.postchecks):
                    for check in (MEM, CPU):
                        self.assertLessEqual(
                            _names(stage).count(check), 1, f"{name}/{pb.name}"
                        )


if __name__ == "__main__":
    unittest.main()
