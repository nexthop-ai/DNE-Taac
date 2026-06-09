# pyre-unsafe

"""
OSS Test Executor

Executes tests and maps exceptions to test statuses.
"""

import asyncio
import traceback
from typing import Optional

from taac.runner.oss_exceptions import (
    OSSConfigError,
    OSSInfrastructureError,
    OSSSetupError,
    OSSTeardownError,
    OSSTestExecutionError,
    OSSTestbedError,
    OSSTransientError,
)
from taac.runner.oss_test_result import OSSTestResult
from taac.runner.oss_test_status import OSSTestStatus


class OSSTestExecutor:
    """
    Executes tests and handles exception-to-status mapping.

    This class wraps test execution and converts exceptions into
    appropriate test statuses for reporting.
    """

    @staticmethod
    def map_exception_to_status(exception: Exception) -> OSSTestStatus:
        """
        Map an exception to a test status.

        Args:
            exception: The exception that was raised

        Returns:
            Appropriate test status for the exception
        """
        if isinstance(exception, OSSSetupError):
            return OSSTestStatus.SETUP_FAILED
        elif isinstance(exception, OSSTeardownError):
            return OSSTestStatus.TEARDOWN_FAILED
        elif isinstance(exception, (OSSInfrastructureError, OSSTestbedError)):
            return OSSTestStatus.SETUP_FAILED
        elif isinstance(exception, OSSConfigError):
            return OSSTestStatus.ERROR
        elif isinstance(exception, OSSTestExecutionError):
            return OSSTestStatus.FAILED
        elif isinstance(exception, asyncio.TimeoutError):
            return OSSTestStatus.TIMEOUT
        elif isinstance(exception, AssertionError):
            return OSSTestStatus.FAILED
        else:
            return OSSTestStatus.ERROR

    @staticmethod
    async def execute_with_exception_handling(
        result: OSSTestResult,
        coro,
        logger,
    ) -> OSSTestResult:
        """
        Execute a coroutine and handle exceptions.

        Args:
            result: Test result object to update
            coro: Coroutine to execute
            logger: Logger instance

        Returns:
            Updated test result
        """
        try:
            await coro
            result.mark_complete(OSSTestStatus.PASSED, "Test completed successfully")
        except Exception as e:
            status = OSSTestExecutor.map_exception_to_status(e)
            tb = traceback.format_exc()
            result.exception = e
            result.traceback = tb
            result.mark_complete(status, str(e))
            logger.error(f"Test failed with {status}: {e}")
            logger.debug(f"Traceback:\n{tb}")

        return result

    @staticmethod
    def execute_with_retry(
        func,
        max_retries: int = 0,
        logger = None,
    ):
        """
        Execute a function with retry logic for transient errors.

        Args:
            func: Function to execute
            max_retries: Maximum number of retries
            logger: Logger instance

        Returns:
            Result of the function

        Raises:
            The last exception if all retries fail
        """
        last_exception = None

        # Clamp negatives to 0 so a stray `--retry -1` doesn't fall
        # through `range(0)` straight into `raise last_exception` with
        # last_exception still None (which raises TypeError).
        max_retries = max(0, max_retries)
        for attempt in range(max_retries + 1):
            try:
                return func()
            except OSSTransientError as e:
                last_exception = e
                if attempt < max_retries:
                    if logger:
                        logger.warning(f"Transient error on attempt {attempt + 1}/{max_retries + 1}: {e}")
                        logger.info(f"Retrying...")
                else:
                    if logger:
                        logger.error(f"All {max_retries + 1} attempts failed")
            except Exception as e:
                # Non-transient errors should not be retried
                raise

        # If we get here, all retries failed
        raise last_exception
