# pyre-unsafe

"""
OSS-Specific Exceptions

Custom exceptions for the OSS TAAC entry point.
Includes exception classification logic per VP1 spec.
"""

import unittest
from typing import Tuple, Type

# Import at module level to avoid circular dependency
# OSSTestStatus will be imported when needed
_OSSTestStatus = None


def _get_test_status():
    """Lazy import of OSSTestStatus to avoid circular dependency."""
    global _OSSTestStatus
    if _OSSTestStatus is None:
        from taac.runner.oss_test_status import OSSTestStatus
        _OSSTestStatus = OSSTestStatus
    return _OSSTestStatus


class OSSException(Exception):
    """Base exception for all OSS TAAC errors."""
    pass


class OSSConfigError(OSSException):
    """
    Configuration error.

    Raised when there's an issue with the test configuration,
    such as invalid test config file, missing required fields, etc.
    """
    pass


class OSSInfrastructureError(OSSException):
    """
    Infrastructure error.

    Raised when there's an issue with the test infrastructure,
    such as IXIA connection failure, device unreachable, etc.
    """
    pass


class OSSTransientError(OSSException):
    """
    Transient error that may succeed on retry.

    Raised for temporary failures that might be resolved by retrying,
    such as network timeouts, temporary device unavailability, etc.

    This is a base class for transient/retry-able errors.
    These indicate temporary issues that may succeed on retry.
    """
    pass


class OSSTestbedError(OSSException):
    """
    Testbed error.

    Raised when there's an issue with the testbed setup or state,
    such as devices not in expected state, topology mismatch, etc.

    Error related to testbed/device issues.
    Considered an infrastructure error.
    """
    pass


class OSSTestExecutionError(OSSException):
    """
    Test execution error.

    Raised when a test fails during execution (not setup/teardown).
    """
    pass


class OSSSetupError(OSSException):
    """
    Setup error.

    Raised when test setup fails.
    """
    pass


class OSSTeardownError(OSSException):
    """
    Teardown error.

    Raised when test teardown fails.
    """
    pass


class OSSConnectionError(OSSException):
    """
    Connection error.

    Raised when Thrift/network connection fails.
    Note: Named OSSConnectionError to avoid conflict with builtin ConnectionError.
    """
    pass


# Exception classification for test status determination
def get_exception_to_status_map():
    """Get the exception-to-status mapping dict."""
    OSSTestStatus = _get_test_status()
    return {
        AssertionError: OSSTestStatus.FAILED,
        unittest.SkipTest: OSSTestStatus.SKIPPED,
        TimeoutError: OSSTestStatus.TIMEOUT,
        OSSTestbedError: OSSTestStatus.ERROR,
        OSSTransientError: OSSTestStatus.ERROR,
        OSSConnectionError: OSSTestStatus.ERROR,
        OSSSetupError: OSSTestStatus.SETUP_FAILED,
        OSSTeardownError: OSSTestStatus.TEARDOWN_FAILED,
    }


def classify_exception(exc: Exception) -> Tuple[object, bool]:
    """
    Classify an exception into a test status.

    Args:
        exc: The exception to classify

    Returns:
        Tuple of (OSSTestStatus, is_transient)
    """
    OSSTestStatus = _get_test_status()
    is_transient = isinstance(exc, OSSTransientError)

    exception_to_status = get_exception_to_status_map()
    for exc_type, status in exception_to_status.items():
        if isinstance(exc, exc_type):
            return (status, is_transient)

    # Default: unknown exceptions are ERROR
    return (OSSTestStatus.ERROR, False)


def is_infra_error(exc: Exception) -> bool:
    """
    Determine if exception is an infrastructure error vs user error.

    Infrastructure errors:
    - OSSTestbedError (device issues)
    - OSSConnectionError (network issues)
    - OSSTransientError (temporary failures)
    - OSSInfrastructureError (general infra issues)

    User errors:
    - AssertionError (test logic failure)
    - ValueError, TypeError (bad test code)

    Args:
        exc: The exception to classify

    Returns:
        True if this is an infrastructure error, False otherwise
    """
    INFRA_EXCEPTIONS = (
        OSSTestbedError,
        OSSConnectionError,
        OSSTransientError,
        OSSInfrastructureError,
        OSSSetupError,
        OSSTeardownError,
        OSError,
        IOError,
    )
    return isinstance(exc, INFRA_EXCEPTIONS)
