# pyre-unsafe

"""
OSS-Specific Exceptions

Custom exceptions for the OSS TAAC entry point.
"""


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
    """
    pass


class OSSTestbedError(OSSException):
    """
    Testbed error.

    Raised when there's an issue with the testbed setup or state,
    such as devices not in expected state, topology mismatch, etc.
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
