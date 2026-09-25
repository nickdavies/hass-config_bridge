"""MQTT's model: the YAML's schema, and the config entry it renders to."""

from __future__ import annotations

import probatio as vol
import pytest

from custom_components.config_bridge.lib.diff import REDACTED
from custom_components.config_bridge.object_types.mqtt.model import (
    DEFAULT_BIRTH,
    DEFAULT_WILL,
    SCHEMA,
    export_mqtt,
    render_mqtt,
    unknown_keys,
)

MINIMAL = {"broker": "mosquitto.automation.svc.cluster.local"}


def test_minimal_renders_the_flows_canonical_shape() -> None:
    entry = render_mqtt(MINIMAL)
    assert entry.title == "mosquitto.automation.svc.cluster.local"
    assert entry.data == {
        "broker": "mosquitto.automation.svc.cluster.local",
        "port": 1883,
        "protocol": "5",
        "transport": "tcp",
    }
    # The options flow always stores all five, so the rendering does too.
    assert entry.options == {
        "discovery": True,
        "discovery_prefix": "homeassistant",
        "discovery_qos": 0,
        "birth_message": DEFAULT_BIRTH,
        "will_message": DEFAULT_WILL,
    }


def test_optional_settings_go_to_data_only_when_given() -> None:
    entry = render_mqtt(
        {**MINIMAL, "username": "hass", "password": "pw", "keepalive": 30}
    )
    assert entry.data["username"] == "hass"
    assert entry.data["password"] == "pw"
    assert entry.data["keepalive"] == 30
    assert "client_id" not in entry.data


def test_false_disables_birth_and_will() -> None:
    entry = render_mqtt({**MINIMAL, "birth_message": False, "will_message": False})
    assert entry.options["birth_message"] == {}
    assert entry.options["will_message"] == {}


def test_defaults_are_copies() -> None:
    render_mqtt(MINIMAL).options["birth_message"]["payload"] = "changed"
    assert DEFAULT_BIRTH["payload"] == "online"


def test_unknown_keys() -> None:
    assert unknown_keys({"broker": "x", "tls_version": "1.2"}, {"discovery": True}) == [
        "data.tls_version"
    ]
    assert unknown_keys({"broker": "x"}, {"new_option": 1}) == ["options.new_option"]
    assert unknown_keys(render_mqtt(MINIMAL).data, render_mqtt(MINIMAL).options) == []


def test_export_round_trips_to_the_same_entry() -> None:
    conf = {**MINIMAL, "port": 8883, "username": "hass", "discovery_prefix": "ha"}
    entry = render_mqtt(conf)
    exported = export_mqtt(entry.data, entry.options)
    assert exported == {
        "broker": "mosquitto.automation.svc.cluster.local",
        "discovery_prefix": "ha",
        "port": 8883,
        "username": "hass",
    }
    assert render_mqtt(exported) == entry


def test_export_redacts_secrets() -> None:
    entry = render_mqtt({**MINIMAL, "password": "hunter2"})
    assert export_mqtt(entry.data, entry.options)["password"] == REDACTED


def test_export_turns_a_disabled_message_back_into_false() -> None:
    entry = render_mqtt({**MINIMAL, "will_message": False})
    assert export_mqtt(entry.data, entry.options)["will_message"] is False


# --- the YAML ----------------------------------------------------------------


@pytest.mark.parametrize(
    ("given", "stored"), [(5, "5"), ("3.1.1", "3.1.1"), (3.1, "3.1")]
)
def test_protocol_is_normalised_to_the_stored_string(given, stored) -> None:
    assert SCHEMA({"broker": "x", "protocol": given})["protocol"] == stored


def test_numeric_password_is_a_string() -> None:
    assert SCHEMA({"broker": "x", "password": 12345})["password"] == "12345"


def test_websocket_settings_need_websockets() -> None:
    with pytest.raises(vol.Invalid, match="websockets"):
        SCHEMA({"broker": "x", "ws_path": "/mqtt"})
    SCHEMA({"broker": "x", "transport": "websockets", "ws_path": "/mqtt"})


def test_client_cert_needs_its_key() -> None:
    with pytest.raises(vol.Invalid):
        SCHEMA({"broker": "x", "client_cert": "PEM"})


def test_birth_message_needs_a_payload() -> None:
    with pytest.raises(vol.Invalid):
        SCHEMA({"broker": "x", "birth_message": {"topic": "t"}})
    assert SCHEMA({"broker": "x", "birth_message": False})["birth_message"] is False


def test_unknown_setting_is_a_typo() -> None:
    with pytest.raises(vol.Invalid):
        SCHEMA({"broker": "x", "brokr": "y"})
