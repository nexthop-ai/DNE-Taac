#!/usr/bin/env python3
# pyre-unsafe

"""
Unit tests for OSS Entry Point CLI

Tests the command-line interface and basic functionality of the OSS Entry Point.
"""

import json
import os
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest import TestCase

from taac.runner.cli_parser import create_argument_parser
from taac.runner.oss_return_code import OSSReturnCode
from taac.runner.oss_test_result import OSSTestResult
from taac.runner.oss_test_status import OSSTestStatus
from taac.runner.result_formatter import OSSResultAggregator


class TestCLIParser(TestCase):
    """Test CLI argument parsing."""

    def test_required_arguments(self):
        """Test that required arguments are present."""
        parser = create_argument_parser()

        # Test with all required args
        args = parser.parse_args(
            [
                "--test-configs",
                "test1.py",
                "test2.py",
                "--dut",
                "device1",
                "--ixia-api-server",
                "10.0.0.1",
            ]
        )

        self.assertEqual(args.test_configs, ["test1.py", "test2.py"])
        self.assertEqual(args.duts, ["device1"])
        self.assertEqual(args.ixia_api_server, "10.0.0.1")

    def test_output_format_argument(self):
        """Test --output-format argument."""
        parser = create_argument_parser()

        # Test json format
        args = parser.parse_args(
            [
                "--test-configs",
                "test.py",
                "--dut",
                "dev1",
                "--ixia-api-server",
                "10.0.0.1",
                "--output-format",
                "json",
            ]
        )
        self.assertEqual(args.output_format, "json")

        # Test junit format
        args = parser.parse_args(
            [
                "--test-configs",
                "test.py",
                "--dut",
                "dev1",
                "--ixia-api-server",
                "10.0.0.1",
                "--output-format",
                "junit",
            ]
        )
        self.assertEqual(args.output_format, "junit")

        # Test default (text)
        args = parser.parse_args(
            [
                "--test-configs",
                "test.py",
                "--dut",
                "dev1",
                "--ixia-api-server",
                "10.0.0.1",
            ]
        )
        self.assertEqual(args.output_format, "text")

    def test_all_specified_arguments_exist(self):
        """Test that all arguments from spec exist."""
        parser = create_argument_parser()

        args = parser.parse_args(
            [
                "--test-configs",
                "test.py",
                "--dut",
                "device1",
                "--ixia-api-server",
                "10.0.0.1",
            ]
        )

        # Verify all required attributes exist
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
        self.assertTrue(hasattr(args, "json_output"))
        self.assertTrue(hasattr(args, "junit_output"))


class TestExitCodes(TestCase):
    """Test that exit codes match specification."""

    def test_exit_codes_match_spec(self):
        """Verify exit codes match specification."""
        self.assertEqual(OSSReturnCode.SUCCESS, 0)
        self.assertEqual(OSSReturnCode.TEST_FAILURE, 1)
        self.assertEqual(OSSReturnCode.CONFIG_ERROR, 2)
        self.assertEqual(OSSReturnCode.INFRASTRUCTURE_ERROR, 3)


class TestResultFormatter(TestCase):
    """Test result formatting (JSON and JUnit XML)."""

    def test_json_output_format(self):
        """Test JSON output format generation."""
        aggregator = OSSResultAggregator()

        # Add test results
        result = OSSTestResult(
            test_config="test_config.py",
            playbook="playbook1",
            dut="device1",
            status=OSSTestStatus.PASSED,
        )
        result.mark_complete(OSSTestStatus.PASSED, "Test passed")
        aggregator.add_result(result)

        # Write to temporary file
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as f:
            json_path = f.name

        try:
            aggregator.to_json(json_path)

            # Verify JSON is valid
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

        # Add passed and failed test results
        result1 = OSSTestResult(
            test_config="test_config.py",
            playbook="playbook1",
            dut="device1",
            status=OSSTestStatus.PASSED,
        )
        result1.mark_complete(OSSTestStatus.PASSED, "Test passed")
        aggregator.add_result(result1)

        result2 = OSSTestResult(
            test_config="test_config.py",
            playbook="playbook2",
            dut="device2",
            status=OSSTestStatus.FAILED,
        )
        result2.mark_complete(OSSTestStatus.FAILED, "Test failed")
        result2.traceback = "Error traceback"
        aggregator.add_result(result2)

        # Write to temporary file
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".xml", delete=False
        ) as f:
            junit_path = f.name

        try:
            aggregator.to_junit_xml(junit_path)

            # Verify XML is valid
            tree = ET.parse(junit_path)
            root = tree.getroot()

            self.assertEqual(root.tag, "testsuites")
            self.assertEqual(root.get("tests"), "2")
            self.assertEqual(root.get("failures"), "1")

            # Check testsuite structure
            testsuite = root.find("testsuite")
            self.assertIsNotNone(testsuite)
            self.assertEqual(testsuite.get("name"), "TAAC_OSS_Tests")

            # Check testcases
            testcases = testsuite.findall("testcase")
            self.assertEqual(len(testcases), 2)

            # Verify failure element exists
            failures = testsuite.findall(".//failure")
            self.assertEqual(len(failures), 1)
        finally:
            if os.path.exists(junit_path):
                os.unlink(junit_path)


if __name__ == "__main__":
    import unittest

    unittest.main()
