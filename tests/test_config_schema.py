"""`CONFIG_SCHEMA` with every object type wired in, as `check_config` runs it."""

from __future__ import annotations

import probatio
import pytest

from custom_components.config_bridge import CONFIG_SCHEMA, OBJECT_TYPES

# The shape of the hass-configs config.
HOMELAB = {
    "http": {
        "use_x_forwarded_for": True,
        "trusted_proxies": ["10.244.0.0/16", "10.96.0.0/12"],
    },
    "mqtt": {
        "broker": "mosquitto.automation.svc.cluster.local",
        "username": "hass",
        "password": "secret",
    },
    "network": {"adapters": ["eth0", "192.168.20.0/24"]},
    "areas": {
        "mode": "exclusive",
        "items": {"kitchen": {"name": "Kitchen", "icon": "mdi:stove"}},
    },
}


def validate(block: object) -> dict:
    return CONFIG_SCHEMA({"config_bridge": block})["config_bridge"]


def test_every_object_type_is_registered() -> None:
    assert list(OBJECT_TYPES) == ["http", "mqtt", "network", "areas"]


def test_homelab_config_validates() -> None:
    validated = validate(HOMELAB)
    assert set(validated) == set(HOMELAB)
    assert all(conf["report_only"] is False for conf in validated.values())
    assert validated["areas"]["items"]["kitchen"]["name"] == "Kitchen"


def test_empty_block_is_allowed() -> None:
    # `config_bridge:` on its own loads the integration for its export action.
    assert validate(None) == {}


def test_unknown_object_type_is_a_typo() -> None:
    with pytest.raises(probatio.Invalid):
        validate({"htpp": {}})


def test_unknown_setting_is_a_typo() -> None:
    with pytest.raises(probatio.Invalid):
        validate({"mqtt": {"broker": "x", "brokr": "y"}})


def test_other_integrations_are_left_alone() -> None:
    config = CONFIG_SCHEMA({"config_bridge": {}, "http": {"server_port": 8123}})
    assert config["http"] == {"server_port": 8123}
