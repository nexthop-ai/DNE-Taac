# pyre-unsafe

"""Regression tests for OSS-mode import drift.

OSS-mode entry-point modules in taac/tasks/, taac/libs/, taac/runner/,
etc. may transitively import Meta-internal packages — taac.internal.*,
taac.policy_generator, neteng.*, etc. When such a transitive import
lives at module top level (i.e., NOT inside `if t.TYPE_CHECKING or
not TAAC_OSS:`), importing the gating module in OSS mode raises
ModuleNotFoundError before any real work happens.

Each test method below imports an OSS-mode entry point and asserts it
loads cleanly. A regression that adds an ungated Meta-internal import
to any of these modules will cause its corresponding test to fail with
a focused traceback pointing at the offending file.

To extend coverage for a new OSS-mode entry-point module, add a test
method that imports it. Keep the imports inside the test methods (not
at file top-level) so a regression in one module doesn't break pytest
collection for the rest of the file.
"""

import importlib
import unittest


class TestOssImportDrift(unittest.TestCase):
    """Each test imports an OSS-mode entry point. Uses importlib.import_module
    rather than a plain `import` statement so a previously-cached failed
    import is re-attempted (and re-raised) instead of silently passing."""

    def test_taac_tasks_registry_imports_in_oss_mode(self):
        importlib.import_module("taac.tasks.registry")

    def test_taac_libs_taac_runner_imports_in_oss_mode(self):
        importlib.import_module("taac.libs.taac_runner")

    def test_taac_libs_test_setup_orchestrator_imports_in_oss_mode(self):
        importlib.import_module("taac.libs.test_setup_orchestrator")

    def test_taac_runner_oss_entry_point_imports_in_oss_mode(self):
        importlib.import_module("taac.runner.oss_entry_point")
