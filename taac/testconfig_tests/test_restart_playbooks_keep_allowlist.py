# Copyright (c) Meta Platforms, Inc. and affiliates.

# pyre-unsafe
"""Every playbook that interrupts a service must end up with a SERVICE_RESTART_CHECK
whose allowlist covers the interrupted units, after the runner's last-wins collapse."""

import json
import unittest

from taac.health_check.health_check import types as hc_types
from taac.testconfigs.npi import wedge800_npi_test_config as w800


def _surviving_restart_check(playbook):
    # Mirrors TaacRunner.get_checks_to_run: same-named checks without a check_id, last wins.
    by_name = {c.name: c for c in (playbook.postchecks or []) if not c.check_id}
    return by_name.get(hc_types.CheckName.SERVICE_RESTART_CHECK)


class RestartPlaybooksKeepAllowlistTest(unittest.TestCase):
    def test_platform_hardening(self):
        for playbook in w800.W800_PLATFORM_HARDENING_TEST_CONFIG.playbooks:
            derived = w800._w800_derived_service_check(playbook)  # None: interrupts nothing
            if derived is None:
                continue
            units = set(json.loads(derived.check_params.json_params)["expected_restarted_services"])
            with self.subTest(playbook=playbook.name):
                check = _surviving_restart_check(playbook)
                self.assertIsNotNone(check)
                params = json.loads(check.check_params.json_params or "{}")
                allowed = set(params.get("expected_restarted_services", []))
                self.assertTrue(units <= allowed, f"{playbook.name}: {sorted(units - allowed)} not allowlisted")
                # Recovery is judged from the collector's last 5 s sample; without retries it races the restart.
                self.assertGreater(params.get("retry_count", 0), 0, playbook.name)
