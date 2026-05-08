#!/usr/bin/env python3
# pyre-unsafe

"""
Quick test to verify VP1 implementation matches requirements.
"""

import argparse
import json
import os
import tempfile
import xml.etree.ElementTree as ET
from datetime import datetime
from unittest import TestCase

from taac.runner.cli_parser import create_argument_parser
from taac.runner.oss_return_code import OSSReturnCode
from taac.runner.oss_test_result import OSSTestResult
from taac.runner.oss_test_status import OSSTestStatus
from taac.runner.result_formatter import OSSResultAggregator


class TestVP1Compliance(TestCase):
    """Test VP1 implementation against requirements."""

    def test_cli_arguments_exist(self):
        """Test that all required CLI arguments exist."""
        parser = create_argument_parser()

        # Parse with minimal required args
        args = parser.parse_args([
            "--test-configs", "test_config",
            "--dut", "device1",
        ])

        # Check all required arguments from spec exist
        self.assertTrue(hasattr(args, "test_configs"))
        self.assertTrue(hasattr(args, "duts"))
        self.assertTrue(hasattr(args, "ixia_api_server"))
        self.assertTrue(hasattr(args, "ixia_session_id"))
        self.assertTrue(hasattr(args, "skip_ixia_setup"))
        self.assertTrue(hasattr(args, "skip_ixia_cleanup"))
        self.assertTrue(hasattr(args, "skip_testbed_isolation"))
        self.assertTrue(hasattr(args, "skip_setup_tasks"))
        self.assertTrue(hasattr(args, "skip_teardown_tasks"))
        self.assertTrue(hasattr(args, "log_level"))
        self.assertTrue(hasattr(args, "log_file"))
        self.assertTrue(hasattr(args, "dry_run"))
        self.assertTrue(hasattr(args, "output_format"))

    def test_output_format_argument(self):
        """Test --output-format argument."""
        parser = create_argument_parser()

        # Test json format
        args = parser.parse_args(["--test-configs", "test", "--dut", "dev1", "--output-format", "json"])
        self.assertEqual(args.output_format, "json")

        # Test junit format
        args = parser.parse_args(["--test-configs", "test", "--dut", "dev1", "--output-format", "junit"])
        self.assertEqual(args.output_format, "junit")

        # Test text format (default)
        args = parser.parse_args(["--test-configs", "test", "--dut", "dev1"])
        self.assertEqual(args.output_format, "text")

    def test_exit_codes_match_spec(self):
        """Test that exit codes match the specification."""
        # SUCCESS = 0
        self.assertEqual(OSSReturnCode.SUCCESS, 0)
        # TEST_FAILURE = 1
        self.assertEqual(OSSReturnCode.TEST_FAILURE, 1)
        # CONFIG_ERROR = 2
        self.assertEqual(OSSReturnCode.CONFIG_ERROR, 2)
        # INFRASTRUCTURE_ERROR = 3
        self.assertEqual(OSSReturnCode.INFRASTRUCTURE_ERROR, 3)

    def test_json_output_format(self):
        """Test JSON output format generation."""
        aggregator = OSSResultAggregator()

        # Add a test result
        result = OSSTestResult(
            test_config="test_config",
            playbook="playbook1",
            dut="device1",
            status=OSSTestStatus.PASSED,
        )
        result.mark_complete(OSSTestStatus.PASSED, "Test passed")
        aggregator.add_result(result)

        # Write to temporary file
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json_path = f.name

        try:
            aggregator.to_json(json_path)

            # Verify JSON is valid and contains expected fields
            with open(json_path, "r") as f:
                data = json.load(f)

            self.assertIn("summary", data)
            self.assertIn("results", data)
            self.assertEqual(len(data["results"]), 1)
            self.assertEqual(data["summary"]["total"], 1)
            self.assertEqual(data["summary"]["passed"], 1)
        finally:
            if os.path.exists(json_path):
                os.unlink(json_path)

    def test_junit_xml_output_format(self):
        """Test JUnit XML output format generation."""
        aggregator = OSSResultAggregator()

        # Add a passed test result
        result1 = OSSTestResult(
            test_config="test_config",
            playbook="playbook1",
            dut="device1",
            status=OSSTestStatus.PASSED,
        )
        result1.mark_complete(OSSTestStatus.PASSED, "Test passed")
        aggregator.add_result(result1)

        # Add a failed test result
        result2 = OSSTestResult(
            test_config="test_config",
            playbook="playbook2",
            dut="device2",
            status=OSSTestStatus.FAILED,
        )
        result2.mark_complete(OSSTestStatus.FAILED, "Test failed")
        result2.traceback = "Traceback (most recent call last):\n  File test.py, line 1\n    raise Exception('test')"
        aggregator.add_result(result2)

        # Write to temporary file
        with tempfile.NamedTemporaryFile(mode="w", suffix=".xml", delete=False) as f:
            junit_path = f.name

        try:
            aggregator.to_junit_xml(junit_path)

            # Verify XML is valid and contains expected structure
            tree = ET.parse(junit_path)
            root = tree.getroot()

            self.assertEqual(root.tag, "testsuites")
            self.assertEqual(root.get("tests"), "2")
            self.assertEqual(root.get("failures"), "1")

            # Check testsuite
            testsuite = root.find("testsuite")
            self.assertIsNotNone(testsuite)
            self.assertEqual(testsuite.get("name"), "TAAC_OSS_Tests")

            # Check testcases
            testcases = testsuite.findall("testcase")
            self.assertEqual(len(testcases), 2)

            # Check failure element exists for failed test
            failures = testsuite.findall(".//failure")
            self.assertEqual(len(failures), 1)
        finally:
            if os.path.exists(junit_path):
                os.unlink(junit_path)


if __name__ == "__main__":
    import unittest
    unittest.main()
