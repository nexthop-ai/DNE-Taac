# pyre-unsafe

"""
OSS Test Status Enum

Defines the possible states of a test execution in the OSS environment.
"""

from enum import Enum


class OSSTestStatus(str, Enum):
    """
    Test execution status for OSS TAAC tests.

    This enum represents the final state of a test execution and is used
    to determine the exit code and reporting.
    """

    # Success states
    PASSED = "PASSED"  # Test completed successfully, all assertions passed

    # Failure states
    FAILED = "FAILED"  # Test completed but one or more assertions failed
    ERROR = "ERROR"  # Test encountered an unexpected error during execution

    # Infrastructure states
    SETUP_FAILED = "SETUP_FAILED"  # Test setup failed (IXIA, device connection, etc.)
    TEARDOWN_FAILED = "TEARDOWN_FAILED"  # Test teardown failed
    TIMEOUT = "TIMEOUT"  # Test exceeded maximum execution time

    # Skip states
    SKIPPED = "SKIPPED"  # Test was skipped (disabled playbook, etc.)
    NOT_RUN = "NOT_RUN"  # Test was not executed

    def is_success(self) -> bool:
        """Check if this status represents a successful test."""
        return self == OSSTestStatus.PASSED

    def is_failure(self) -> bool:
        """Check if this status represents a test failure."""
        return self in (
            OSSTestStatus.FAILED,
            OSSTestStatus.ERROR,
            OSSTestStatus.SETUP_FAILED,
            OSSTestStatus.TEARDOWN_FAILED,
            OSSTestStatus.TIMEOUT,
        )

    def is_skipped(self) -> bool:
        """Check if this status represents a skipped test."""
        return self in (OSSTestStatus.SKIPPED, OSSTestStatus.NOT_RUN)

    def __str__(self) -> str:
        """String representation of the status."""
        return self.value
