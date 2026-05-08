# pyre-unsafe

"""
OSS Test Result Dataclass

Represents the result of a single test execution.
"""

import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from taac.runner.oss_test_status import OSSTestStatus


@dataclass
class OSSTestResult:
    """
    Result of a single test execution.

    This dataclass captures all relevant information about a test run,
    including status, timing, errors, and metadata.
    """

    # Test identification
    test_config: str  # Name of the test configuration
    playbook: str  # Name of the playbook
    dut: str  # Device under test (hostname or IP)

    # Test outcome
    status: OSSTestStatus  # Final status of the test
    message: str = ""  # Human-readable message (error details, etc.)

    # Timing information
    start_time: float = field(default_factory=time.time)  # Unix timestamp
    end_time: Optional[float] = None  # Unix timestamp
    duration: Optional[float] = None  # Duration in seconds

    # Error information
    exception: Optional[Exception] = None  # Exception that caused failure (if any)
    traceback: Optional[str] = None  # Full traceback (if any)

    # Metadata
    metadata: Dict[str, str] = field(default_factory=dict)  # Additional metadata

    def mark_complete(self, status: OSSTestStatus, message: str = "") -> None:
        """
        Mark the test as complete with the given status.

        Args:
            status: Final status of the test
            message: Optional message describing the outcome
        """
        self.status = status
        self.message = message
        self.end_time = time.time()
        if self.end_time and self.start_time:
            self.duration = self.end_time - self.start_time

    def to_dict(self) -> Dict:
        """
        Convert the result to a dictionary for JSON serialization.

        Returns:
            Dictionary representation of the result
        """
        return {
            "test_config": self.test_config,
            "playbook": self.playbook,
            "dut": self.dut,
            "status": str(self.status),
            "message": self.message,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "duration": self.duration,
            "exception": str(self.exception) if self.exception else None,
            "traceback": self.traceback,
            "metadata": self.metadata,
        }

    def __str__(self) -> str:
        """String representation of the result."""
        duration_str = f"{self.duration:.2f}s" if self.duration else "N/A"
        return f"[{self.status}] {self.test_config}/{self.playbook} on {self.dut} ({duration_str})"
