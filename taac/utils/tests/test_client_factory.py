# pyre-unsafe
"""
Unit tests for Client Factory implementations

Tests the Protocol-based dependency injection architecture for Thrift client creation.
Designed to run inside the Docker build environment (fboss-taac) where all
Thrift-generated types, fbthrift, and FBOSS packages are available.
"""

import os
import unittest
from unittest import mock

from taac.utils.client_factory_interface import (
    ThriftClientFactory,
)
from taac.utils.oss_client_factory import OSSClientFactory


class TestClientFactoryInterface(unittest.TestCase):
    """Test the ThriftClientFactory Protocol."""

    def test_oss_factory_implements_protocol(self):
        """OSSClientFactory structurally satisfies ThriftClientFactory.

        OSSClientFactory does NOT inherit from ThriftClientFactory — this
        isinstance check works via @runtime_checkable structural matching,
        proving the methods actually match the contract.
        """
        factory = OSSClientFactory()
        self.assertIsInstance(factory, ThriftClientFactory)

    def test_protocol_has_required_methods(self):
        """Test that the protocol defines all required methods."""
        required_methods = [
            "get_agent_client",
            "get_async_agent_client",
            "get_hw_agent_client",
            "get_qsfp_client",
            "get_bgp_client",
            "get_fsdb_client",
        ]
        for method_name in required_methods:
            self.assertTrue(
                hasattr(ThriftClientFactory, method_name),
                f"Protocol missing method: {method_name}",
            )


class TestOSSClientFactoryAgentSync(unittest.TestCase):
    """Test get_agent_client (synchronous context manager)."""

    @mock.patch("taac.utils.oss_client_factory.FbossCtrl", new=mock.MagicMock())
    @mock.patch("taac.utils.oss_client_factory.get_sync_client")
    def test_get_agent_client(self, mock_get_sync_client):
        """Test get_agent_client uses get_sync_client with FbossCtrl."""
        mock_client = mock.MagicMock()
        mock_ctx = mock.MagicMock()
        mock_ctx.__enter__ = mock.MagicMock(return_value=mock_client)
        mock_ctx.__exit__ = mock.MagicMock(return_value=False)
        mock_get_sync_client.return_value = mock_ctx

        factory = OSSClientFactory()

        with factory.get_agent_client(
            hostname="switch1.example.com",
            port=5909,
            timeout=120,
        ) as client:
            self.assertIsNotNone(client)
            self.assertEqual(client, mock_client)

        mock_get_sync_client.assert_called_once_with(
            mock.ANY,  # FbossCtrl class
            host="switch1.example.com",
            port=5909,
            timeout=120,
        )

    @mock.patch("taac.utils.oss_client_factory.FbossCtrl", new=mock.MagicMock())
    @mock.patch("taac.utils.oss_client_factory.get_sync_client")
    def test_get_agent_client_default_port(self, mock_get_sync_client):
        """Test get_agent_client uses default port 5909."""
        mock_ctx = mock.MagicMock()
        mock_ctx.__enter__ = mock.MagicMock(return_value=mock.MagicMock())
        mock_ctx.__exit__ = mock.MagicMock(return_value=False)
        mock_get_sync_client.return_value = mock_ctx

        factory = OSSClientFactory()

        with factory.get_agent_client(hostname="switch1.example.com") as client:
            self.assertIsNotNone(client)

        call_kwargs = mock_get_sync_client.call_args
        self.assertEqual(call_kwargs.kwargs.get("port"), 5909)

class TestOSSClientFactoryAsync(unittest.IsolatedAsyncioTestCase):
    """Test async client methods."""

    @mock.patch("taac.utils.oss_client_factory.get_client")
    async def test_get_async_agent_client(self, mock_get_client):
        """Test get_async_agent_client connects using FbossCtrl on default port 5909."""
        mock_client = mock.AsyncMock()
        mock_get_client.return_value.__aenter__ = mock.AsyncMock(return_value=mock_client)
        mock_get_client.return_value.__aexit__ = mock.AsyncMock(return_value=False)

        factory = OSSClientFactory()
        async with factory.get_async_agent_client(hostname="switch1.example.com") as client:
            self.assertIsNotNone(client)
            self.assertEqual(client, mock_client)

        call_kwargs = mock_get_client.call_args
        self.assertEqual(call_kwargs.kwargs.get("port"), 5909)

    @mock.patch("taac.utils.oss_client_factory.get_client")
    async def test_get_hw_agent_client_port_calculation(self, mock_get_client):
        """Test get_hw_agent_client calculates correct port from switch_index."""
        mock_client = mock.AsyncMock()
        mock_get_client.return_value.__aenter__ = mock.AsyncMock(
            return_value=mock_client
        )
        mock_get_client.return_value.__aexit__ = mock.AsyncMock(return_value=False)

        factory = OSSClientFactory()

        async with factory.get_hw_agent_client(
            hostname="switch1.example.com",
            switch_index=2,
            timeout=120,
        ):
            pass

        # Verify port calculation: HW_AGENT_BASE_PORT (5931) + switch_index (2) = 5933
        call_kwargs = mock_get_client.call_args
        self.assertEqual(call_kwargs.kwargs.get("port"), 5933)

    @mock.patch("taac.utils.oss_client_factory.get_client")
    async def test_get_qsfp_client(self, mock_get_client):
        """Test get_qsfp_client connects using QsfpService on default port 5910."""
        mock_client = mock.AsyncMock()
        mock_get_client.return_value.__aenter__ = mock.AsyncMock(return_value=mock_client)
        mock_get_client.return_value.__aexit__ = mock.AsyncMock(return_value=False)

        factory = OSSClientFactory()
        async with factory.get_qsfp_client(hostname="switch1.example.com") as client:
            self.assertIsNotNone(client)

        call_kwargs = mock_get_client.call_args
        self.assertEqual(call_kwargs.kwargs.get("port"), 5910)

    @mock.patch("taac.utils.oss_client_factory.get_client")
    async def test_get_bgp_client(self, mock_get_client):
        """Test get_bgp_client connects using TBgpService."""
        mock_client = mock.AsyncMock()
        mock_get_client.return_value.__aenter__ = mock.AsyncMock(return_value=mock_client)
        mock_get_client.return_value.__aexit__ = mock.AsyncMock(return_value=False)

        factory = OSSClientFactory()
        async with factory.get_bgp_client(hostname="switch1.example.com") as client:
            self.assertIsNotNone(client)

        call_kwargs = mock_get_client.call_args
        self.assertEqual(call_kwargs.kwargs.get("port"), 6909)

    @mock.patch("taac.utils.oss_client_factory.get_client")
    async def test_get_fsdb_client(self, mock_get_client):
        """Test get_fsdb_client connects using FsdbService."""
        mock_client = mock.AsyncMock()
        mock_get_client.return_value.__aenter__ = mock.AsyncMock(return_value=mock_client)
        mock_get_client.return_value.__aexit__ = mock.AsyncMock(return_value=False)

        factory = OSSClientFactory()
        async with factory.get_fsdb_client(hostname="switch1.example.com") as client:
            self.assertIsNotNone(client)

        call_kwargs = mock_get_client.call_args
        self.assertEqual(call_kwargs.kwargs.get("port"), 5908)


class TestFbossSwitchDIWiring(unittest.TestCase):
    """Test the DI wiring contracts — requires full build env (docker/getdeps)."""

    @mock.patch.dict(os.environ, {"TAAC_OSS": "1"})
    def test_fboss_switch_raises_without_provider_in_oss(self):
        """FbossSwitch._get_fboss_agent_client raises RuntimeError in OSS without a factory."""
        # Re-import to pick up the patched TAAC_OSS env var
        import importlib
        import taac.driver.fboss_switch as fboss_mod
        importlib.reload(fboss_mod)

        logger = mock.MagicMock()
        switch = fboss_mod.FbossSwitch("switch1.example.com", logger=logger)
        with self.assertRaises(RuntimeError, msg="client_provider is required"):
            switch._get_fboss_agent_client()

    def test_fboss_switch_uses_factory_when_provided(self):
        """FbossSwitch._get_fboss_agent_client delegates to the injected factory."""
        from taac.driver.fboss_switch import FbossSwitch

        mock_factory = mock.MagicMock(spec=OSSClientFactory)
        mock_factory.get_agent_client.return_value = mock.MagicMock()
        logger = mock.MagicMock()

        switch = FbossSwitch("switch1.example.com", logger=logger, client_provider=mock_factory)
        switch._get_fboss_agent_client()

        mock_factory.get_agent_client.assert_called_once()

    def test_async_agent_client_delegates_to_factory(self):
        """async_agent_client property routes through factory.get_async_agent_client."""
        from taac.driver.fboss_switch import FbossSwitch

        mock_factory = mock.MagicMock(spec=OSSClientFactory)
        mock_factory.get_async_agent_client.return_value = mock.MagicMock()
        logger = mock.MagicMock()

        switch = FbossSwitch("switch1.example.com", logger=logger, client_provider=mock_factory)
        switch.async_agent_client

        mock_factory.get_async_agent_client.assert_called_once()

    @mock.patch.dict(os.environ, {"TAAC_OSS": "1"})
    def test_client_accessors_raise_runtime_error_without_provider(self):
        """Each refactored client accessor must raise RuntimeError (not NotImplementedError)
        when client_provider is absent in OSS mode.
        """
        import importlib
        import taac.driver.fboss_switch as fboss_mod
        importlib.reload(fboss_mod)

        logger = mock.MagicMock()
        switch = fboss_mod.FbossSwitch("switch1.example.com", logger=logger)

        import asyncio

        for method_name in (
            "async_get_qsfp_client",
            "_get_bgp_client",
            "get_hw_agent_client",
            "async_get_fsdb_client",
        ):
            with self.subTest(method=method_name):
                with self.assertRaises(RuntimeError, msg=f"{method_name} should raise RuntimeError"):
                    asyncio.run(getattr(switch, method_name)())

    @mock.patch.dict(os.environ, {"TAAC_OSS": "1"})
    def test_no_fboss_agent_client_wrapper_in_oss_mode(self):
        """FbossAgentClientWrapper must not exist in OSS mode."""
        import importlib
        import taac.driver.fboss_switch as fboss_mod
        importlib.reload(fboss_mod)

        self.assertFalse(
            hasattr(fboss_mod, "FbossAgentClientWrapper"),
            "FbossAgentClientWrapper should not exist in OSS mode — the stub-based "
            "approach was replaced by ThriftClientFactory injection (PR #46). "
            "An upstream sync may have resurrected the old stubs.",
        )


    def test_no_fboss_agent_client_wrapper_in_internal_mode(self):
        """FbossAgentClientWrapper must not exist even in internal (non-OSS) mode."""
        from taac.driver import fboss_switch as fboss_mod

        self.assertFalse(
            hasattr(fboss_mod, "FbossAgentClientWrapper"),
            "FbossAgentClientWrapper was removed entirely by PR #46 — including the "
            "`if not TAAC_OSS` import from fboss.fb_thrift_clients. "
            "An upstream sync may have resurrected it.",
        )

class TestDriverFactoryDIWiring(unittest.IsolatedAsyncioTestCase):
    """Test that driver_factory injects OSSClientFactory — requires full build env."""

    @mock.patch.dict(os.environ, {"TAAC_OSS": "1"})
    async def test_oss_mode_injects_client_factory(self):
        """async_get_device_driver passes OSSClientFactory for FBOSS in OSS."""
        import importlib
        import taac.test_as_a_config.types as taac_types
        import taac.utils.driver_factory as df_mod
        importlib.reload(df_mod)

        mock_driver_cls = mock.MagicMock()
        df_mod.DEVICE_OS_DRIVER_CLASS_MAP[taac_types.DeviceOsType.FBOSS] = mock_driver_cls
        df_mod.HOST_TO_DEVICE_OS_TYPE_MAP["test-factory-switch"] = (
            taac_types.DeviceOsType.FBOSS
        )

        await df_mod.async_get_device_driver("test-factory-switch")

        _, kwargs = mock_driver_cls.call_args
        self.assertIn("client_provider", kwargs)
        self.assertIsInstance(kwargs["client_provider"], OSSClientFactory)


if __name__ == "__main__":
    unittest.main()
