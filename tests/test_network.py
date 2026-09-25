from __future__ import annotations

import pytest

from custom_components.config_bridge.model.network import (
    AdapterView,
    SelectorError,
    describe_adapters,
    resolve_adapters,
)

# The pod's shape: the pod network plus three multus attachments, named in
# annotation order.
ADAPTERS = [
    AdapterView("eth0", ("10.244.3.17/24", "fe80::1/64")),
    AdapterView("net1", ("192.168.20.9/24",)),
    AdapterView("net2", ("192.168.254.9/24",)),
    AdapterView("net3", ("192.168.30.9/24",)),
    AdapterView("lo", ("127.0.0.1/8",)),
]


def test_by_name() -> None:
    assert resolve_adapters(["net1", "eth0"], ADAPTERS) == ("eth0", "net1")


def test_by_network() -> None:
    assert resolve_adapters(["192.168.20.0/24"], ADAPTERS) == ("net1",)


def test_mixed_and_deduplicated() -> None:
    assert resolve_adapters(["net1", "192.168.20.0/24"], ADAPTERS) == ("net1",)


def test_a_wider_network_can_pick_several() -> None:
    assert resolve_adapters(["192.168.0.0/16"], ADAPTERS) == ("net1", "net2", "net3")


def test_ipv6_selector() -> None:
    assert resolve_adapters(["fe80::/64"], ADAPTERS) == ("eth0",)


def test_nothing_means_auto_detect() -> None:
    assert resolve_adapters([], ADAPTERS) == ()


@pytest.mark.parametrize("selector", ["net9", "172.16.0.0/12"])
def test_unmatched_selector_is_an_error_not_a_fallback(selector: str) -> None:
    # HA would silently fall back to auto-detection instead.
    with pytest.raises(SelectorError, match="Available: eth0"):
        resolve_adapters(["net1", selector], ADAPTERS)


def test_describe_adapters() -> None:
    assert describe_adapters(ADAPTERS)["eth0"] == ["10.244.3.0/24", "fe80::/64"]
    assert describe_adapters(ADAPTERS)["net1"] == ["192.168.20.0/24"]
