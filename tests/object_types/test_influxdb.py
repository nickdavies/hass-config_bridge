"""InfluxDB's model: the YAML's schema, and the config entry it renders to."""

from __future__ import annotations

import probatio
import pytest

from custom_components.config_bridge.lib.diff import REDACTED
from custom_components.config_bridge.object_types.influxdb.model import (
    SCHEMA,
    export_influxdb,
    render_influxdb,
    unknown_keys,
)

URL = "http://influxdb.observability.svc.cluster.local:8086"
MINIMAL = {
    "url": URL,
    "token": "hunter2",
    "organization": "0123456789abcdef",
    "bucket": "homeassistant",
}

# What InfluxDB's YAML import stores for 1.x connection keys.
V1_DATA = {
    "api_version": "1",
    "host": "influx.example.com",
    "port": 8086,
    "username": "hass",
    "password": "old",
    "database": "home_assistant",
    "ssl": False,
    "path": None,
    "verify_ssl": True,
    "ssl_ca_cert": None,
}


def test_minimal_renders_the_flows_v2_shape() -> None:
    entry = render_influxdb(SCHEMA(MINIMAL))
    assert entry.title == f"homeassistant ({URL})"
    assert entry.data == {
        "api_version": "2",
        "url": URL,
        "token": "hunter2",
        "organization": "0123456789abcdef",
        "bucket": "homeassistant",
        "verify_ssl": True,
    }


def test_ca_cert_is_stored_only_when_given() -> None:
    entry = render_influxdb({**MINIMAL, "ssl_ca_cert": "/config/influx.pem"})
    assert entry.data["ssl_ca_cert"] == "/config/influx.pem"


def test_unknown_keys() -> None:
    assert unknown_keys(render_influxdb(MINIMAL).data, {}) == []
    # A 1.x entry is replaced, not reported: its keys are known.
    assert unknown_keys(V1_DATA, {}) == []
    assert unknown_keys({**V1_DATA, "timeout": 5}, {"x": 1}) == [
        "data.timeout",
        "options.x",
    ]


def test_export_round_trips_to_the_same_entry() -> None:
    conf = {**MINIMAL, "verify_ssl": False}
    entry = render_influxdb(conf)
    exported = export_influxdb(entry.data)
    assert exported == {**conf, "token": REDACTED}
    assert render_influxdb({**exported, "token": "hunter2"}) == entry


def test_export_drops_an_imported_entrys_empty_ca_cert() -> None:
    data = {**render_influxdb(MINIMAL).data, "ssl_ca_cert": None}
    assert "ssl_ca_cert" not in export_influxdb(data)


def test_export_refuses_a_v1_entry() -> None:
    with pytest.raises(ValueError, match="1.x"):
        export_influxdb(V1_DATA)


# --- the YAML ----------------------------------------------------------------


@pytest.mark.parametrize("key", ["url", "token", "organization", "bucket"])
def test_connection_settings_are_required(key) -> None:
    with pytest.raises(probatio.Invalid):
        SCHEMA({k: v for k, v in MINIMAL.items() if k != key})


def test_url_needs_a_scheme() -> None:
    with pytest.raises(probatio.Invalid, match="http"):
        SCHEMA({**MINIMAL, "url": "influxdb:8086"})


def test_numeric_organization_is_a_string() -> None:
    assert SCHEMA({**MINIMAL, "organization": 1234})["organization"] == "1234"


def test_unknown_setting_is_a_typo() -> None:
    # The filters belong under Home Assistant's own `influxdb:` key.
    with pytest.raises(probatio.Invalid):
        SCHEMA({**MINIMAL, "exclude": {"domains": ["update"]}})
