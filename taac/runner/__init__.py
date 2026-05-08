# pyre-unsafe

"""
OSS Entry Point Package

This package provides the standalone CLI entry point for running TAAC tests
without Netcastle orchestration. It is designed for external users and vendors
who need to run TAAC tests in non-Meta environments.

Main Components:
- oss_entry_point.py: Main CLI entry point
- oss_cli.py: Argument parsing
- oss_test_status.py: Test status enum
- oss_return_code.py: Exit code enum
- oss_test_result.py: Test result dataclass
- oss_result_aggregator.py: Result collection and summarization
- oss_test_executor.py: Exception → Status mapping
- oss_exceptions.py: OSS-specific exceptions
"""

__all__ = [
    "oss_entry_point",
    "oss_cli",
    "oss_test_status",
    "oss_return_code",
    "oss_test_result",
    "oss_result_aggregator",
    "oss_test_executor",
    "oss_exceptions",
]
