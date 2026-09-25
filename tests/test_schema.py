"""The YAML schema — what `check_config` refuses before anything ships."""

from __future__ import annotations

import pytest
import probatio as vol

from custom_components.config_bridge.model.schema import (
    AREAS_SCHEMA,
    BRIDGE_SCHEMA,
    HTTP_SCHEMA,
    MQTT_SCHEMA,
    NETWORK_SCHEMA,
)

# The hass-configs config, as it will be written.
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


def test_homelab_config_validates() -> None:
    validated = BRIDGE_SCHEMA(HOMELAB)
    assert validated["http"]["report_only"] is False
    assert validated["areas"]["items"]["kitchen"]["name"] == "Kitchen"


def test_empty_block_is_allowed() -> None:
    # `config_bridge:` on its own: loads the integration for its export service.
    assert BRIDGE_SCHEMA(None) == {}


def test_unknown_kind_is_a_typo() -> None:
    with pytest.raises(vol.Invalid):
        BRIDGE_SCHEMA({"htpp": {}})


def test_unknown_setting_is_a_typo() -> None:
    with pytest.raises(vol.Invalid):
        MQTT_SCHEMA({"broker": "x", "brokr": "y"})


# --- http ------------------------------------------------------------------


def test_trusted_proxies_must_be_networks_with_no_host_bits() -> None:
    # Strict like Home Assistant's own schema, so CI refuses what HA would.
    with pytest.raises(vol.Invalid):
        HTTP_SCHEMA({"trusted_proxies": ["10.244.0.1/16"]})
    with pytest.raises(vol.Invalid):
        HTTP_SCHEMA({"trusted_proxies": ["not-a-network"]})


def test_forwarded_for_needs_a_trusted_proxy() -> None:
    with pytest.raises(vol.Invalid, match="trusted proxy"):
        HTTP_SCHEMA({"use_x_forwarded_for": True})


def test_login_threshold_accepts_the_disabled_sentinel() -> None:
    assert (
        HTTP_SCHEMA({"login_attempts_threshold": -1})["login_attempts_threshold"] == -1
    )
    with pytest.raises(vol.Invalid):
        HTTP_SCHEMA({"login_attempts_threshold": -2})


# --- mqtt ------------------------------------------------------------------


@pytest.mark.parametrize(
    ("given", "stored"), [(5, "5"), ("3.1.1", "3.1.1"), (3.1, "3.1")]
)
def test_protocol_is_normalised_to_the_stored_string(given, stored) -> None:
    assert MQTT_SCHEMA({"broker": "x", "protocol": given})["protocol"] == stored


def test_numeric_password_is_a_string() -> None:
    assert MQTT_SCHEMA({"broker": "x", "password": 12345})["password"] == "12345"


def test_websocket_settings_need_websockets() -> None:
    with pytest.raises(vol.Invalid, match="websockets"):
        MQTT_SCHEMA({"broker": "x", "ws_path": "/mqtt"})
    MQTT_SCHEMA({"broker": "x", "transport": "websockets", "ws_path": "/mqtt"})


def test_client_cert_needs_its_key() -> None:
    with pytest.raises(vol.Invalid):
        MQTT_SCHEMA({"broker": "x", "client_cert": "PEM"})


def test_birth_message_needs_a_payload() -> None:
    with pytest.raises(vol.Invalid):
        MQTT_SCHEMA({"broker": "x", "birth_message": {"topic": "t"}})
    assert (
        MQTT_SCHEMA({"broker": "x", "birth_message": False})["birth_message"] is False
    )


# --- network ---------------------------------------------------------------


def test_adapters_are_required_and_may_be_empty() -> None:
    with pytest.raises(vol.Invalid):
        NETWORK_SCHEMA({})
    assert NETWORK_SCHEMA({"adapters": []})["adapters"] == []


def test_bad_network_selector() -> None:
    with pytest.raises(vol.Invalid):
        NETWORK_SCHEMA({"adapters": ["192.168.300.0/24"]})


# --- areas -----------------------------------------------------------------


def test_mode_is_required() -> None:
    with pytest.raises(vol.Invalid):
        AREAS_SCHEMA({"items": {}})


def test_area_ids_must_be_slugs() -> None:
    with pytest.raises(vol.Invalid) as err:
        AREAS_SCHEMA(
            {"mode": "owned", "items": {"Living Room": {"name": "Living Room"}}}
        )
    assert err.value.path == ["items", "Living Room"]


def test_errors_inside_an_area_point_at_it() -> None:
    with pytest.raises(vol.Invalid) as err:
        AREAS_SCHEMA(
            {"mode": "owned", "items": {"kitchen": {"name": "K", "icon": "stove"}}}
        )
    assert err.value.path[:3] == ["items", "kitchen", "icon"]


def test_duplicate_area_names() -> None:
    with pytest.raises(vol.Invalid, match="lounge"):
        AREAS_SCHEMA(
            {
                "mode": "owned",
                "items": {
                    "lounge": {"name": "Living Room"},
                    "living_room": {"name": "living room"},
                },
            }
        )


def test_area_references_are_ids() -> None:
    area = AREAS_SCHEMA(
        {
            "mode": "owned",
            "items": {
                "kitchen": {
                    "name": "Kitchen",
                    "floor_id": "ground",
                    "labels": "downstairs",
                    "temperature_entity_id": "sensor.Kitchen_Temperature",
                }
            },
        }
    )["items"]["kitchen"]
    assert area["labels"] == ["downstairs"]
    assert area["temperature_entity_id"] == "sensor.kitchen_temperature"
    with pytest.raises(vol.Invalid):
        AREAS_SCHEMA(
            {"mode": "owned", "items": {"k": {"name": "K", "floor_id": "Ground Floor"}}}
        )
