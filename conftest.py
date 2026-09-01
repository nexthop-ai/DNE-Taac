# pyre-unsafe
"""Pytest collection configuration for OSS-compatible unit tests.

Many test files under taac/ depend on internal (non-OSS) modules such as
``neteng.*``, ``taac.internal``, or ``taac.health_check``.  These cannot
be collected in the open-source Docker image and are excluded below so
that ``python3 -m pytest`` exits cleanly.

When a test file is ported to work without internal dependencies, remove
its entry (or its parent directory) from the appropriate list.
"""

import os

# ---------------------------------------------------------------------------
# Directories where *every* test depends on non-OSS modules.
# ---------------------------------------------------------------------------
_NON_OSS_TEST_DIRS = [
    "taac/health_checks",
    "taac/ixia/tests",
    "taac/libs/fpf/tests",
    "taac/steps/tests",
    "taac/tasks",
]

# ---------------------------------------------------------------------------
# Individual files that are either non-OSS tests or non-test modules
# (production code whose ``test_`` prefix causes pytest to pick them up).
# ---------------------------------------------------------------------------
_NON_OSS_TEST_FILES = [
    # Non-test modules (production code with test_ prefix)
    "taac/test_configs.py",
    "taac/libs/test_setup_orchestrator.py",
    "taac/utils/test_config_utils.py",
]

<<<<<<< HEAD
=======
# ---------------------------------------------------------------------------
# Files inside a _NON_OSS_TEST_DIRS directory that DO run in the OSS image.
# The directory bans above are blanket ones -- most of taac/health_checks
# cannot even be imported here -- but a handful of files are OSS-clean, and
# ignoring them means a health-check change lands with no unit coverage at
# all. Each entry below is verified green in the OSS image; add one only
# after `run_tests.sh -- <path>` passes on its own.
# ---------------------------------------------------------------------------
_OSS_READY_TEST_FILES = [
    "taac/health_checks/device_health_checks/test_cpu_utilization_report_only.py",
    "taac/health_checks/device_health_checks/test_new_characterization_health_checks.py",
    "taac/health_checks/device_health_checks/tests/test_pfc_counter_health_checks.py",
    "taac/health_checks/tests/test_collector_max_summary.py",
    "taac/health_checks/ixia_health_checks/test_ixia_port_stats_health_check.py",
    "taac/health_checks/snapshot_health_checks/test_qos_queue_byte_counters.py",
    "taac/health_checks/tests/test_common_utils.py",
    "taac/health_checks/tests/test_convergence_observer.py",
]

>>>>>>> 11f6733 (NO-DEVX: print out CPU/Memory watermarks in checks (#273))
# Build absolute paths relative to this conftest's directory (repo root).
_HERE = os.path.dirname(__file__)

collect_ignore = [os.path.join(_HERE, f) for f in _NON_OSS_TEST_FILES]
collect_ignore_glob = [os.path.join(_HERE, d, "**") for d in _NON_OSS_TEST_DIRS]
