"""Network against Home Assistant's real network store and adapter loading."""

from __future__ import annotations

from collections.abc import Generator
from typing import Any
from unittest.mock import Mock, patch

import pytest
from homeassistant.components.network.network import async_get_network
from homeassistant.core import HomeAssistant

from ..conftest import SetupBridge, report


def _ifaddr(name: str, ip: str, prefix: int, index: int) -> Mock:
    return Mock(
        nice_name=name,
        ips=[Mock(is_IPv6=False, ip=ip, network_prefix=prefix)],
        index=index,
    )


@pytest.fixture(autouse=True)
def pod_adapters() -> Generator[None]:
    """The pod's interfaces: the pod network and the multus VLANs."""
    with patch(
        "homeassistant.components.network.util.ifaddr.get_adapters",
        return_value=[
            _ifaddr("eth0", "10.244.3.17", 24, 1),
            _ifaddr("net1", "192.168.20.9", 24, 2),
            _ifaddr("net2", "192.168.254.9", 24, 3),
            _ifaddr("net3", "192.168.30.9", 24, 4),
        ],
    ):
        yield


async def test_selects_by_subnet_and_by_name(
    hass: HomeAssistant, setup_bridge: SetupBridge, hass_storage: dict[str, Any]
) -> None:
    await setup_bridge({"network": {"adapters": ["eth0", "192.168.20.0/24"]}})

    network = await async_get_network(hass)
    assert network.configured_adapters == ["eth0", "net1"]
    assert hass_storage["core.network"]["data"]["configured_adapters"] == [
        "eth0",
        "net1",
    ]
    assert report(hass, "network") is None


async def test_empty_list_means_auto_detect(
    hass: HomeAssistant, setup_bridge: SetupBridge
) -> None:
    network = await async_get_network(hass)
    await network.async_reconfig({"configured_adapters": ["net2"]})

    await setup_bridge({"network": {"adapters": []}})

    assert network.configured_adapters == []


async def test_order_in_ha_is_not_drift(
    hass: HomeAssistant, setup_bridge: SetupBridge
) -> None:
    network = await async_get_network(hass)
    await network.async_reconfig({"configured_adapters": ["net1", "eth0"]})

    await setup_bridge({"network": {"adapters": ["eth0", "net1"]}})

    # Left exactly as it was: nothing to write.
    assert network.configured_adapters == ["net1", "eth0"]


async def test_unknown_adapter_is_reported_not_auto_detected(
    hass: HomeAssistant, setup_bridge: SetupBridge
) -> None:
    network = await async_get_network(hass)
    await network.async_reconfig({"configured_adapters": ["net1"]})

    await setup_bridge({"network": {"adapters": ["net9"]}})

    assert network.configured_adapters == ["net1"]
    reason = report(hass, "network").translation_placeholders["reason"]
    assert "net9" in reason
    assert "net1 (192.168.20.0/24)" in reason
