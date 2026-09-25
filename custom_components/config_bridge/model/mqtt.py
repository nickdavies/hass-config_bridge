"""The MQTT config entry, rendered from YAML.

The YAML is flat and uses the entry's own key names; which keys land in
`data` and which in `options` is decided here, the same way MQTT's config
and options flows split them. The rendering is the shape those flows store
— the options flow always writes all five option keys, so this does too —
because anything else would read as drift the first time someone opened the
options dialog and pressed submit.

Written against config entry version 2.1. The MQTT adapter refuses to write
to any other version.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Final

from .diff import REDACTED

ENTRY_VERSION: Final = (2, 1)

DEFAULT_PORT: Final = 1883
DEFAULT_PROTOCOL: Final = "5"
DEFAULT_TRANSPORT: Final = "tcp"
DEFAULT_DISCOVERY: Final = True
DEFAULT_PREFIX: Final = "homeassistant"
DEFAULT_QOS: Final = 0
DEFAULT_BIRTH: Final = {
    "topic": f"{DEFAULT_PREFIX}/status",
    "payload": "online",
    "qos": 0,
    "retain": False,
}
DEFAULT_WILL: Final = {
    "topic": f"{DEFAULT_PREFIX}/status",
    "payload": "offline",
    "qos": 0,
    "retain": False,
}

REQUIRED_DATA_KEYS: Final = ("broker", "port", "protocol", "transport")
OPTIONAL_DATA_KEYS: Final = (
    "username",
    "password",
    "client_id",
    "keepalive",
    "ws_path",
    "ws_headers",
    "certificate",
    "client_cert",
    "client_key",
    "tls_insecure",
)
DATA_KEYS: Final = frozenset((*REQUIRED_DATA_KEYS, *OPTIONAL_DATA_KEYS))
OPTION_KEYS: Final = frozenset(
    ("discovery", "discovery_prefix", "discovery_qos", "birth_message", "will_message")
)

SECRET_KEYS: Final = frozenset(("password", "client_key", "ws_headers"))
"""Never printed. `ws_headers` because it is where a bearer token would go."""


@dataclass(frozen=True, slots=True)
class RenderedEntry:
    title: str
    data: dict[str, Any]
    options: dict[str, Any]


def render_mqtt(conf: Mapping[str, Any]) -> RenderedEntry:
    """The entry the YAML describes. `conf` is the validated YAML section."""
    data: dict[str, Any] = {
        "broker": conf["broker"],
        "port": conf.get("port", DEFAULT_PORT),
        "protocol": conf.get("protocol", DEFAULT_PROTOCOL),
        "transport": conf.get("transport", DEFAULT_TRANSPORT),
    }
    for key in OPTIONAL_DATA_KEYS:
        if key in conf:
            data[key] = conf[key]
    options = {
        "discovery": conf.get("discovery", DEFAULT_DISCOVERY),
        "discovery_prefix": conf.get("discovery_prefix", DEFAULT_PREFIX),
        "discovery_qos": conf.get("discovery_qos", DEFAULT_QOS),
        "birth_message": _birth_will(conf.get("birth_message"), DEFAULT_BIRTH),
        "will_message": _birth_will(conf.get("will_message"), DEFAULT_WILL),
    }
    return RenderedEntry(title=conf["broker"], data=data, options=options)


def _birth_will(
    value: Mapping[str, Any] | bool | None, default: Mapping[str, Any]
) -> dict[str, Any]:
    """YAML `false` disables the message, which MQTT stores as `{}`."""
    if value is None:
        return dict(default)
    if value is False:
        return {}
    return dict(value)


def unknown_keys(data: Mapping[str, Any], options: Mapping[str, Any]) -> list[str]:
    """Keys in a live entry this rendering doesn't know about.

    The bridge replaces the whole entry, so an unknown key would be deleted.
    If Home Assistant has started storing something new, the right response
    is to stop and report, not to strip it.
    """
    return sorted(
        [f"data.{key}" for key in data if key not in DATA_KEYS]
        + [f"options.{key}" for key in options if key not in OPTION_KEYS]
    )


def export_mqtt(data: Mapping[str, Any], options: Mapping[str, Any]) -> dict[str, Any]:
    """A live entry as bridge YAML: defaults left out, secrets redacted."""
    defaults: dict[str, Any] = {
        "port": DEFAULT_PORT,
        "protocol": DEFAULT_PROTOCOL,
        "transport": DEFAULT_TRANSPORT,
        "discovery": DEFAULT_DISCOVERY,
        "discovery_prefix": DEFAULT_PREFIX,
        "discovery_qos": DEFAULT_QOS,
        "birth_message": DEFAULT_BIRTH,
        "will_message": DEFAULT_WILL,
    }
    exported: dict[str, Any] = {}
    for key, value in [*data.items(), *options.items()]:
        if key in defaults and defaults[key] == value:
            continue
        if key in ("birth_message", "will_message") and value == {}:
            value = False
        exported[key] = REDACTED if key in SECRET_KEYS else value
    return dict(sorted(exported.items()))
