# pyre-unsafe

"""
Result Formatter

Collects and summarizes test results, formats output as JSON, JUnit XML, or text.
"""

import json
import xml.etree.ElementTree as ET
from datetime import datetime
from typing import Dict, List

from taac.runner.oss_return_code import OSSReturnCode
from taac.runner.oss_test_result import OSSTestResult
from taac.runner.oss_test_status import OSSTestStatus


class OSSResultAggregator:
    """
    Aggregates and summarizes test results.

    Collects results from multiple test executions and provides
    summary statistics and exit code determination.
    """

    def __init__(self) -> None:
        """Initialize the result aggregator."""
        self.results: List[OSSTestResult] = []

    def add_result(self, result: OSSTestResult) -> None:
        """
        Add a test result to the aggregator.

        Args:
            result: Test result to add
        """
        self.results.append(result)

    def get_summary(self) -> Dict[str, int]:
        """
        Get summary statistics of all results.

        Returns:
            Dictionary with counts for each status
        """
        summary = {
            "total": len(self.results),
            "passed": 0,
            "failed": 0,
            "error": 0,
            "skipped": 0,
            "setup_failed": 0,
            "teardown_failed": 0,
            "timeout": 0,
        }

        for result in self.results:
            if result.status == OSSTestStatus.PASSED:
                summary["passed"] += 1
            elif result.status == OSSTestStatus.FAILED:
                summary["failed"] += 1
            elif result.status == OSSTestStatus.ERROR:
                summary["error"] += 1
            elif result.status == OSSTestStatus.SETUP_FAILED:
                summary["setup_failed"] += 1
            elif result.status == OSSTestStatus.TEARDOWN_FAILED:
                summary["teardown_failed"] += 1
            elif result.status == OSSTestStatus.TIMEOUT:
                summary["timeout"] += 1
            elif result.status.is_skipped():
                summary["skipped"] += 1

        return summary

    def get_exit_code(self) -> OSSReturnCode:
        """
        Determine the appropriate exit code based on results.

        Returns:
            Exit code for the CLI
        """
        if not self.results:
            return OSSReturnCode.NO_TESTS_FOUND

        # Check for infrastructure errors
        if any(result.status == OSSTestStatus.SETUP_FAILED for result in self.results):
            return OSSReturnCode.INFRASTRUCTURE_ERROR

        # Check for test failures
        if any(result.status.is_failure() for result in self.results):
            return OSSReturnCode.TEST_FAILURE

        # All tests passed or skipped
        return OSSReturnCode.SUCCESS

    def to_json(self, filepath: str) -> None:
        """
        Write results to a JSON file.

        Args:
            filepath: Path to the output JSON file
        """
        data = {
            "summary": self.get_summary(),
            "results": [result.to_dict() for result in self.results],
        }

        with open(filepath, "w") as f:
            json.dump(data, f, indent=2)

    def to_junit_xml(self, filepath: str) -> None:
        """
        Write results to a JUnit XML file.

        Args:
            filepath: Path to the output JUnit XML file
        """
        summary = self.get_summary()

        # Create root testsuites element
        testsuites = ET.Element("testsuites")
        testsuites.set("tests", str(summary["total"]))
        testsuites.set("failures", str(summary["failed"]))
        testsuites.set("errors", str(summary["error"] + summary["setup_failed"] + summary["teardown_failed"]))
        testsuites.set("skipped", str(summary["skipped"]))

        # Create a testsuite element
        testsuite = ET.SubElement(testsuites, "testsuite")
        testsuite.set("name", "TAAC_OSS_Tests")
        testsuite.set("tests", str(summary["total"]))
        testsuite.set("failures", str(summary["failed"]))
        testsuite.set("errors", str(summary["error"] + summary["setup_failed"] + summary["teardown_failed"]))
        testsuite.set("skipped", str(summary["skipped"]))
        testsuite.set("timestamp", datetime.now().isoformat())

        # Add testcase elements for each result
        for result in self.results:
            testcase = ET.SubElement(testsuite, "testcase")
            testcase.set("name", f"{result.playbook}_{result.dut}")
            testcase.set("classname", result.test_config)

            if result.duration:
                testcase.set("time", f"{result.duration:.3f}")

            # Add failure/error/skipped elements based on status
            if result.status == OSSTestStatus.FAILED:
                failure = ET.SubElement(testcase, "failure")
                failure.set("message", result.message or "Test failed")
                if result.traceback:
                    failure.text = result.traceback
            elif result.status in (OSSTestStatus.ERROR, OSSTestStatus.SETUP_FAILED, OSSTestStatus.TEARDOWN_FAILED):
                error = ET.SubElement(testcase, "error")
                error.set("message", result.message or "Test error")
                if result.traceback:
                    error.text = result.traceback
            elif result.status.is_skipped():
                skipped = ET.SubElement(testcase, "skipped")
                skipped.set("message", result.message or "Test skipped")

        # Write to file
        tree = ET.ElementTree(testsuites)
        ET.indent(tree, space="  ")  # Pretty-print
        tree.write(filepath, encoding="utf-8", xml_declaration=True)

    def print_summary(self, logger) -> None:
        """
        Print a summary of results to the logger.

        Args:
            logger: Logger instance to use for output
        """
        summary = self.get_summary()

        logger.info("=" * 60)
        logger.info("TEST SUMMARY")
        logger.info("=" * 60)
        logger.info(f"Total Tests: {summary['total']}")
        logger.info(f"Passed: {summary['passed']}")
        logger.info(f"Failed: {summary['failed']}")
        logger.info(f"Error: {summary['error']}")
        logger.info(f"Setup Failed: {summary['setup_failed']}")
        logger.info(f"Teardown Failed: {summary['teardown_failed']}")
        logger.info(f"Timeout: {summary['timeout']}")
        logger.info(f"Skipped: {summary['skipped']}")
        logger.info("=" * 60)

        # Print individual results
        for result in self.results:
            logger.info(str(result))
