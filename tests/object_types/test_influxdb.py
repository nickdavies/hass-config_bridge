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


# --- the 1.x API ---------------------------------------------------------------

V1_YAML = {
    "url": "http://influxdb2.observability.svc.cluster.local:8086",
    "database": "homeassistant",
    "username": "homeassistant",
    "password": "hunter2",
}


def test_v1_renders_the_flows_v1_shape() -> None:
    entry = render_influxdb(SCHEMA(V1_YAML))
    assert entry.title == "homeassistant (influxdb2.observability.svc.cluster.local)"
    assert entry.data == {
        "api_version": "1",
        "host": "influxdb2.observability.svc.cluster.local",
        "port": 8086,
        "username": "homeassistant",
        "password": "hunter2",
        "database": "homeassistant",
        "ssl": False,
        "path": "/",
        "verify_ssl": True,
    }


@pytest.mark.parametrize(
    ("url", "host", "port", "ssl", "path"),
    [
        ("http://Influx.Example", "influx.example", 80, False, "/"),
        ("https://influx.example/influx/", "influx.example", 443, True, "/influx/"),
        ("http://influx.example:8086/a", "influx.example", 8086, False, "/a"),
    ],
)
def test_v1_splits_the_url_as_the_flow_does(url, host, port, ssl, path) -> None:
    data = render_influxdb({"url": url, "database": "db"}).data
    assert (data["host"], data["port"], data["ssl"], data["path"]) == (
        host,
        port,
        ssl,
        path,
    )


def test_v1_without_credentials_stores_none() -> None:
    data = render_influxdb({"url": "http://h:8086", "database": "db"}).data
    assert data["username"] is None
    assert data["password"] is None


def test_v1_export_round_trips_to_the_same_entry() -> None:
    entry = render_influxdb(V1_YAML)
    exported = export_influxdb(entry.data)
    assert exported == {**V1_YAML, "password": REDACTED}
    assert render_influxdb({**exported, "password": "hunter2"}) == entry


def test_v1_export_of_an_imported_entry() -> None:
    assert export_influxdb(V1_DATA) == {
        "url": "http://influx.example.com:8086",
        "database": "home_assistant",
        "username": "hass",
        "password": REDACTED,
    }


def test_v1_and_v2_keys_dont_mix() -> None:
    with pytest.raises(probatio.Invalid, match="one or the other"):
        SCHEMA({**MINIMAL, "database": "db"})


def test_v1_username_needs_its_password() -> None:
    with pytest.raises(probatio.Invalid, match="together"):
        SCHEMA({"url": "http://h", "database": "db", "username": "u"})


def test_an_api_has_to_be_chosen() -> None:
    with pytest.raises(probatio.Invalid, match="1.x API"):
        SCHEMA({"url": "http://h"})


# --- the YAML ----------------------------------------------------------------


@pytest.mark.parametrize("key", ["url", "token", "organization", "bucket"])
def test_v2_settings_are_required(key) -> None:
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
