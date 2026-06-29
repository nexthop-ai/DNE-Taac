#!/usr/bin/env python3
# pyre-unsafe
"""
Client Factory Interface - Protocol for Thrift client creation

This module defines the protocol (interface) that all client factories must implement.
Both OSS and Internal factories implement this protocol.

Port defaults and timeout values live in driver_constants — concrete factories
import them from there so there is a single source of truth.
"""

from typing import AsyncContextManager, ContextManager, Protocol, runtime_checkable


@runtime_checkable
class ThriftClientFactory(Protocol):
    """
    Protocol defining the interface for creating Thrift clients.

    Both OSSClientFactory and InternalClientFactory implement this protocol.
    FbossSwitch receives a factory via dependency injection and uses it
    without knowing which implementation it is.

    This enables the same FbossSwitch driver code to work in both:
    - OSS environments (direct TCP connections)
    - Meta environments (ServiceRouter connections)
    """

    def get_agent_client(
        self,
        hostname: str,
        port: int = ...,
        timeout: float = ...,
    ) -> ContextManager:
        ...

    def get_async_agent_client(
        self,
        hostname: str,
        port: int = ...,
        timeout: float = ...,
    ) -> AsyncContextManager:
        ...

    def get_hw_agent_client(
        self,
        hostname: str,
        switch_index: int,
        timeout: float = ...,
    ) -> AsyncContextManager:
        ...

    def get_qsfp_client(
        self,
        hostname: str,
        port: int = ...,
        timeout: float = ...,
    ) -> AsyncContextManager:
        ...

    def get_bgp_client(
        self,
        hostname: str,
        port: int = ...,
        timeout: float = ...,
    ) -> AsyncContextManager:
        ...

    def get_fsdb_client(
        self,
        hostname: str,
        port: int = ...,
        timeout: float = ...,
    ) -> AsyncContextManager:
        ...
