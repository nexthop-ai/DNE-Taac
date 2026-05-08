#!/usr/bin/env python3
# pyre-unsafe

"""
OSS TAAC Entry Point

Main entry point for running TAAC tests under TAAC_OSS=1. Calls
TaacRunner directly.

Usage:
    python -m taac.runner.oss_entry_point \\
        --test-configs <config> --dut <device> [options]

Examples:
    # Run all tests in a config against a single DUT
    python -m taac.runner.oss_entry_point \\
        --test-configs my_config --dut switch1.example.com

    # Run specific playbooks against multiple DUTs
    python -m taac.runner.oss_entry_point \\
        --test-configs my_config --dut switch1 switch2 \\
        --playbook test_bgp test_agent

    # Enable debug logging
    python -m taac.runner.oss_entry_point \\
        --test-configs my_config --dut switch1 --debug
"""

import asyncio
import importlib.util
import logging
import os
import sys
from pathlib import Path
from typing import List, Optional

from taac.runner.cli_parser import parse_args
from taac.runner.oss_exceptions import (
    OSSConfigError,
    OSSInfrastructureError,
)
from taac.runner.oss_return_code import OSSReturnCode
from taac.runner.oss_test_executor import OSSTestExecutor
from taac.runner.oss_test_result import OSSTestResult
from taac.runner.oss_test_status import OSSTestStatus
from taac.runner.result_formatter import OSSResultAggregator


def load_test_config(config_path: str):
    """
    Load a test configuration from a Python file.

    Args:
        config_path: Path to the Python test config file

    Returns:
        TestConfig object

    Raises:
        OSSConfigError: If the config cannot be loaded
    """
    try:
        # Convert to Path object
        path = Path(config_path)

        # Check if file exists
        if not path.exists():
            raise OSSConfigError(f"Test config file not found: {config_path}")

        if not path.is_file():
            raise OSSConfigError(f"Test config path is not a file: {config_path}")

        if path.suffix != '.py':
            raise OSSConfigError(f"Test config file must be a .py file: {config_path}")

        # Load the module from file
        spec = importlib.util.spec_from_file_location(path.stem, path)
        if spec is None or spec.loader is None:
            raise OSSConfigError(f"Failed to load module spec from: {config_path}")

        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        # Look for a TestConfig object or a function that returns one.
        # Try common naming conventions.
        #
        # IMPORTANT: gate the "call as factory" branch on
        # `not isinstance(config, TestConfig)`, not on bare callable().
        # thrift-python structs (taac.test_as_a_config.thrift_types) are
        # themselves callable — invoking an instance with kwargs returns
        # a copy with those fields replaced (immutable copy-with-override).
        # A naive callable(config) check therefore matches both a
        # module-level `test_config = TestConfig(...)` value *and* a
        # `def test_config(): ...` factory. A TestConfig instance called
        # with no kwargs returns a no-arg copy of itself, so this used
        # to be a silent no-op — but the next code reader who expects
        # their module-level value not to be invoked would be surprised.
        # Exclude instances explicitly so only real factories get called.
        #
        # Check both binding flavors: thrift_types (thrift-python, the
        # callable copy-with-override variant) and types (legacy
        # thrift-py3, used by Meta-internal configs).
        from taac.test_as_a_config import thrift_types as _taac_thrift_types
        from taac.test_as_a_config import types as _taac_types
        _testconfig_classes = (_taac_thrift_types.TestConfig, _taac_types.TestConfig)
        for attr_name in ['test_config', 'TEST_CONFIG', 'config', 'CONFIG']:
            if hasattr(module, attr_name):
                config = getattr(module, attr_name)
                if callable(config) and not isinstance(config, _testconfig_classes):
                    config = config()
                return config

        # If no config found, raise error
        raise OSSConfigError(
            f"No test config found in {config_path}. "
            f"Expected one of: test_config, TEST_CONFIG, config, CONFIG"
        )

    except OSSConfigError:
        raise
    except Exception as e:
        raise OSSConfigError(f"Failed to load test config from '{config_path}': {e}")


def filter_playbooks(config, playbook_names: Optional[List[str]] = None):
    """
    Filter playbooks from a test config.

    Args:
        config: TestConfig object
        playbook_names: List of playbook names to include (None = all enabled)

    Returns:
        List of playbooks to execute
    """
    playbooks = config.playbooks if hasattr(config, "playbooks") else []

    if playbook_names:
        # Filter by name, but only return enabled playbooks (mirrors the else
        # branch — a disabled playbook whose name matches shouldn't run).
        filtered = [pb for pb in playbooks if pb.name in playbook_names and pb.enabled]
        return filtered
    else:
        # Return all enabled playbooks
        return [pb for pb in playbooks if pb.enabled]


# TODO: delete this free function. It's a placeholder — nothing calls
# it in this PR (main() bails at the "Test execution is not implemented"
# branch before reaching execution). The OSS test executor (landing in
# a follow-up PR) replaces it with OSSTestExecutor.execute_playbook(),
# and this free version becomes redundant. Remove together with the new
# OSSTestExecutor wiring so the dead version never ships.
async def execute_playbook(
    taac_runner,
    playbook,
    dut: str,
    test_config_name: str,
    logger,
) -> OSSTestResult:
    """
    Execute a single playbook against a single DUT.

    Args:
        taac_runner: TaacRunner instance
        playbook: Playbook to execute
        dut: Device under test
        test_config_name: Name of the test configuration
        logger: Logger instance

    Returns:
        Test result
    """
    result = OSSTestResult(
        test_config=test_config_name,
        playbook=playbook.name,
        dut=dut,
        status=OSSTestStatus.NOT_RUN,
    )

    logger.info(f"Executing playbook '{playbook.name}' on DUT '{dut}'")

    # TODO: Implement actual playbook execution via TaacRunner
    # This is a placeholder that will be replaced with actual implementation
    try:
        # await taac_runner.run_playbook(playbook, dut)
        result.mark_complete(OSSTestStatus.PASSED, "Playbook executed successfully")
    except Exception as e:
        status = OSSTestExecutor.map_exception_to_status(e)
        result.mark_complete(status, str(e))
        result.exception = e

    return result


def main(argv: Optional[List[str]] = None) -> int:
    """
    Main entry point for OSS TAAC.

    Args:
        argv: Command line arguments (default: sys.argv)

    Returns:
        Exit code (0 for success, non-zero for failure)
    """
    # Set OSS mode environment variable
    os.environ["TAAC_OSS"] = "1"

    # Parse arguments
    args = parse_args(argv)

    # Wire --device-info-csv / --circuit-info-csv to the topology loader's
    # env vars BEFORE any taac.* import. The OSS topology loader
    # @memoize_forever-caches its lookups on first read, so a late export
    # leaves stale data behind for the rest of the process.
    if args.device_info_csv:
        os.environ["TAAC_DEVICE_INFO_PATH"] = os.path.abspath(args.device_info_csv)
    if args.circuit_info_csv:
        os.environ["TAAC_CIRCUIT_INFO_PATH"] = os.path.abspath(args.circuit_info_csv)

    # Setup logger (stdlib; structured-logger integration is a follow-up)
    log_level = logging.DEBUG if args.debug else getattr(logging, args.log_level)
    handlers: List[logging.Handler] = [logging.StreamHandler()]
    if args.log_file:
        handlers.append(logging.FileHandler(args.log_file))
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=handlers,
    )
    logger = logging.getLogger("taac.oss")

    logger.info("=" * 60)
    logger.info("OSS TAAC Test Runner")
    logger.info("=" * 60)
    logger.info(f"Test Configs: {args.test_configs}")
    logger.info(f"DUTs: {args.duts}")
    if args.log_file:
        logger.info(f"Log File: {args.log_file}")

    # Create result aggregator
    aggregator = OSSResultAggregator()

    try:
        # Load all test configs
        configs = []
        for config_path in args.test_configs:
            logger.info(f"Loading test config from: {config_path}")
            config = load_test_config(config_path)
            configs.append((config_path, config))

        # Process each test config
        all_playbooks = []
        for config_path, config in configs:
            playbooks = filter_playbooks(config, args.playbooks)
            if playbooks:
                all_playbooks.extend([(config_path, config, pb) for pb in playbooks])

        if not all_playbooks:
            logger.error("No playbooks found to execute")
            return OSSReturnCode.NO_TESTS_FOUND

        logger.info(f"Total playbooks to execute: {len(all_playbooks)}")

        # List tests mode
        if args.list_tests:
            logger.info("\nAvailable Tests:")
            for config_path, config, pb in all_playbooks:
                logger.info(f"  - {Path(config_path).name}: {pb.name}")
            return OSSReturnCode.SUCCESS

        # Dry-run mode
        if args.dry_run:
            logger.info("Dry-run mode: All configurations validated successfully")
            return OSSReturnCode.SUCCESS

        # Test execution wiring (TaacRunner instantiation + per-playbook
        # invocation) lands in a follow-up PR. This foundation only supports
        # --dry-run / --list-tests; bail out cleanly rather than silently
        # falling through to a stub that fabricates PASSED.
        logger.error(
            "Test execution is not implemented in this build. "
            "Pass --dry-run to validate the config or --list-tests to list "
            "available tests."
        )
        return OSSReturnCode.CONFIG_ERROR

        # Print summary
        aggregator.print_summary(logger)

        # Write output files based on format
        if args.output_format == "json" or args.json_output:
            json_path = args.json_output or "taac_results.json"
            aggregator.to_json(json_path)
            logger.info(f"JSON results written to {json_path}")

        if args.output_format == "junit" or args.junit_output:
            junit_path = args.junit_output or "taac_results.xml"
            aggregator.to_junit_xml(junit_path)
            logger.info(f"JUnit XML results written to {junit_path}")

        # Determine exit code
        exit_code = aggregator.get_exit_code()
        logger.info(f"Exit code: {exit_code}")

        return exit_code

    except OSSConfigError as e:
        logger.error(f"Configuration error: {e}")
        return OSSReturnCode.CONFIG_ERROR
    except OSSInfrastructureError as e:
        logger.error(f"Infrastructure error: {e}")
        return OSSReturnCode.INFRA_ERROR
    except Exception as e:
        # User-caused errors (bad config / bad args) are already caught by
        # the OSSConfigError / OSSInfrastructureError handlers above, so an
        # unhandled exception this far down is more likely an infra problem
        # than a config error.
        logger.error(f"Unexpected error: {e}")
        logger.debug("Traceback:", exc_info=True)
        return OSSReturnCode.INFRA_ERROR


if __name__ == "__main__":
    sys.exit(main())
