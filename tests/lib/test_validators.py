"""The shared validators, which stand in for Home Assistant's `cv` ones."""

from __future__ import annotations

import probatio as vol
import pytest

from custom_components.config_bridge.lib.validators import (
    ensure_list,
    entity_id,
    icon,
    ip_network,
    keyed_by_slug,
    port,
    slug,
    string,
)


def test_string_accepts_numbers_and_refuses_structure() -> None:
    # A YAML password of 12345 arrives as an int.
    assert string(12345) == "12345"
    assert string(3.1) == "3.1"
    for bad in (None, True, [], {}):
        with pytest.raises(vol.Invalid):
            string(bad)


def test_ensure_list() -> None:
    assert ensure_list(None) == []
    assert ensure_list("a") == ["a"]
    assert ensure_list(["a"]) == ["a"]


@pytest.mark.parametrize("good", ["kitchen", "guest_1", "a1_b2"])
def test_slug_accepts_ids(good: str) -> None:
    assert slug(good) == good


@pytest.mark.parametrize(
    "bad", ["Kitchen", "living room", "_kitchen", "a__b", "a-b", ""]
)
def test_slug_refuses_what_slugify_would_change(bad: str) -> None:
    with pytest.raises(vol.Invalid):
        slug(bad)


def test_entity_id_is_lowercased_then_checked() -> None:
    assert entity_id("sensor.Kitchen_Temperature") == "sensor.kitchen_temperature"
    with pytest.raises(vol.Invalid):
        entity_id("kitchen_temperature")


def test_icon_needs_a_prefix() -> None:
    assert icon("mdi:sofa") == "mdi:sofa"
    with pytest.raises(vol.Invalid):
        icon("sofa")


def test_ip_network_refuses_host_bits() -> None:
    assert ip_network("10.244.0.0/16") == "10.244.0.0/16"
    with pytest.raises(vol.Invalid):
        ip_network("10.244.0.1/16")
    with pytest.raises(vol.Invalid):
        ip_network("not-a-network")


def test_port() -> None:
    assert port("8123") == 8123
    with pytest.raises(vol.Invalid):
        port(70000)


ITEMS = keyed_by_slug(vol.Schema({vol.Required("name"): string}))


def test_keyed_by_slug() -> None:
    assert ITEMS(None) == {}
    assert ITEMS({"kitchen": {"name": "Kitchen"}}) == {"kitchen": {"name": "Kitchen"}}


def test_keyed_by_slug_points_at_a_bad_key() -> None:
    with pytest.raises(vol.Invalid) as err:
        ITEMS({"Living Room": {"name": "Living Room"}})
    assert err.value.path == ["Living Room"]


def test_keyed_by_slug_points_inside_an_item() -> None:
    with pytest.raises(vol.Invalid) as err:
        ITEMS({"kitchen": {}})
    assert err.value.path == ["kitchen", "name"]
