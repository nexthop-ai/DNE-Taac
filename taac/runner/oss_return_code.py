# pyre-unsafe

"""
OSS Return Code Enum

Defines the exit codes for the OSS TAAC entry point.
"""

from enum import IntEnum


class OSSReturnCode(IntEnum):
    """
    Exit codes for OSS TAAC CLI.

    These codes are returned to the shell and can be used by CI/CD systems
    to determine the outcome of test execution.
    """

    SUCCESS = 0  # All tests passed
    TEST_FAILURE = 1  # One or more tests failed
    CONFIG_ERROR = 2  # Configuration error (invalid test config, missing files, etc.)
    INFRASTRUCTURE_ERROR = 3  # Infrastructure error (IXIA, connectivity, device access)
    NO_TESTS_FOUND = 4  # No tests found to execute

    def __str__(self) -> str:
        """String representation of the return code."""
        return f"{self.name} ({self.value})"
