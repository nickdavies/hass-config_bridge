"""The `config_bridge:` YAML, validated without Home Assistant.

Every kind's section is checked here, as part of `CONFIG_SCHEMA`, so a typo
fails `check_config` in hass-configs CI rather than turning into a report at
boot. Nothing here leans on Home Assistant's own schemas. HA's rules are
applied later, inside each kind's own error boundary, because they are the
part that can change under us on an upgrade — and a failing `CONFIG_SCHEMA`
stops the whole integration, where a kind failing on its own only stops
itself.

Plain voluptuous rather than `config_validation`, for the same reason the
rest of `model/` avoids Home Assistant: the unit tests run without it. Where
a validator stands in for one of HA's, it says which.
"""

from __future__ import annotations

import ipaddress
import re
from collections.abc import Callable, Mapping
from typing import Any, Final

import voluptuous as vol

from ..const import CONF_REPORT_ONLY
from .areas import duplicate_names

SLUG_RE: Final = re.compile(r"^[a-z0-9]+(_[a-z0-9]+)*$")
"""What `slugify` can produce — Home Assistant's rule for area, floor and
label ids (`cv.slug` checks `slugify(value) == value`)."""

ENTITY_ID_RE: Final = re.compile(
    r"^(?!.+__)(?!_)[\da-z_]+(?<!_)\.(?!_)[\da-z_]+(?<!_)$"
)
"""`homeassistant.core.VALID_ENTITY_ID`."""


def _string(value: Any) -> str:
    """`cv.string`: numbers become strings, anything else structured is refused.

    A YAML password of `12345` arrives as an int and should still work.
    """
    if isinstance(value, bool) or value is None:
        raise vol.Invalid("expected a string")
    if isinstance(value, (str, int, float)):
        return str(value)
    raise vol.Invalid("expected a string")


def _ensure_list(value: Any) -> list[Any]:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def _slug(value: Any) -> str:
    text = _string(value)
    if not SLUG_RE.match(text):
        raise vol.Invalid(
            f"{text!r} is not a valid id: use lowercase letters and digits "
            "joined by single underscores"
        )
    return text


def _entity_id(value: Any) -> str:
    text = _string(value).lower()
    if not ENTITY_ID_RE.match(text):
        raise vol.Invalid(f"{text!r} is not a valid entity id")
    return text


def _icon(value: Any) -> str:
    """`cv.icon`."""
    text = _string(value)
    if ":" not in text:
        raise vol.Invalid('icons are written as "prefix:name", e.g. mdi:sofa')
    return text


def _ip_network(value: Any) -> str:
    """A network as HA's HTTP schema reads it: strict, so host bits are an error.

    `10.244.0.1/16` is refused, the same as Home Assistant would refuse it.
    """
    try:
        return str(ipaddress.ip_network(_string(value)))
    except ValueError as err:
        raise vol.Invalid(str(err)) from err


def _adapter_selector(value: Any) -> str:
    text = _string(value)
    if "/" in text:
        try:
            ipaddress.ip_network(text, strict=False)
        except ValueError as err:
            raise vol.Invalid(str(err)) from err
    return text


_port = vol.All(vol.Coerce(int), vol.Range(min=1, max=65535))
_qos = vol.All(vol.Coerce(int), vol.In([0, 1, 2]))
_report_only = vol.Optional(CONF_REPORT_ONLY, default=False)


def _keyed_by_slug(
    item_schema: Callable[[Any], Any],
) -> Callable[[Any], dict[str, Any]]:
    """A mapping whose keys are ids — `cv.schema_with_slug_keys`, spelled out."""

    def validate(value: Any) -> dict[str, Any]:
        if value is None:
            return {}
        if not isinstance(value, Mapping):
            raise vol.Invalid("expected a mapping of id to settings")
        validated: dict[str, Any] = {}
        for key, item in value.items():
            try:
                slug = _slug(key)
            except vol.Invalid as err:
                raise vol.Invalid(err.msg, path=[key]) from err
            try:
                validated[slug] = item_schema(item)
            except vol.MultipleInvalid as err:
                raise vol.MultipleInvalid(
                    [
                        vol.Invalid(error.msg, path=[key, *error.path])
                        for error in err.errors
                    ]
                ) from err
            except vol.Invalid as err:
                raise vol.Invalid(err.msg, path=[key, *err.path]) from err
        return validated

    return validate


# --- http ------------------------------------------------------------------


def _forwarded_for_needs_proxies(conf: dict[str, Any]) -> dict[str, Any]:
    """HA's settings page refuses this pair, and so would the store."""
    if conf.get("use_x_forwarded_for") and not conf.get("trusted_proxies"):
        raise vol.Invalid(
            "use_x_forwarded_for needs at least one trusted proxy",
            path=["trusted_proxies"],
        )
    return conf


HTTP_SCHEMA: Final = vol.All(
    vol.Schema(
        {
            _report_only: vol.Boolean(),
            vol.Optional("server_host"): vol.All(
                _ensure_list, vol.Length(min=1), [_string]
            ),
            vol.Optional("server_port"): _port,
            vol.Optional("ssl_certificate"): _string,
            vol.Optional("ssl_peer_certificate"): _string,
            vol.Optional("ssl_key"): _string,
            vol.Optional("cors_allowed_origins"): vol.All(_ensure_list, [_string]),
            vol.Optional("use_x_forwarded_for"): vol.Boolean(),
            vol.Optional("trusted_proxies"): vol.All(_ensure_list, [_ip_network]),
            vol.Optional("login_attempts_threshold"): vol.Any(
                vol.All(vol.Coerce(int), vol.Range(min=0)), -1
            ),
            vol.Optional("ip_ban_enabled"): vol.Boolean(),
            vol.Optional("ssl_profile"): vol.In(["intermediate", "modern"]),
            vol.Optional("use_x_frame_options"): vol.Boolean(),
        }
    ),
    _forwarded_for_needs_proxies,
)

# --- mqtt ------------------------------------------------------------------

_BIRTH_WILL = vol.Any(
    False,
    vol.Schema(
        {
            vol.Required("topic"): _string,
            vol.Required("payload"): _string,
            vol.Optional("qos", default=0): _qos,
            vol.Optional("retain", default=False): vol.Boolean(),
        }
    ),
)


def _websocket_settings_need_websockets(conf: dict[str, Any]) -> dict[str, Any]:
    """MQTT's flow drops these for TCP, so keeping them would be permanent drift."""
    if conf.get("transport", "tcp") != "websockets":
        for key in ("ws_path", "ws_headers"):
            if key in conf:
                raise vol.Invalid(
                    f"{key} only applies to transport: websockets", path=[key]
                )
    return conf


def _client_cert_and_key_together(conf: dict[str, Any]) -> dict[str, Any]:
    if ("client_cert" in conf) != ("client_key" in conf):
        raise vol.Invalid("client_cert and client_key go together")
    return conf


MQTT_SCHEMA: Final = vol.All(
    vol.Schema(
        {
            _report_only: vol.Boolean(),
            vol.Required("broker"): _string,
            vol.Optional("port"): _port,
            vol.Optional("protocol"): vol.All(_string, vol.In(["5", "3.1.1", "3.1"])),
            vol.Optional("username"): _string,
            vol.Optional("password"): _string,
            vol.Optional("client_id"): _string,
            vol.Optional("keepalive"): vol.All(vol.Coerce(int), vol.Range(min=15)),
            vol.Optional("transport"): vol.In(["tcp", "websockets"]),
            vol.Optional("ws_path"): _string,
            vol.Optional("ws_headers"): {str: str},
            vol.Optional("certificate"): _string,
            vol.Optional("client_cert"): _string,
            vol.Optional("client_key"): _string,
            vol.Optional("tls_insecure"): vol.Boolean(),
            vol.Optional("discovery"): vol.Boolean(),
            vol.Optional("discovery_prefix"): _string,
            vol.Optional("discovery_qos"): _qos,
            vol.Optional("birth_message"): _BIRTH_WILL,
            vol.Optional("will_message"): _BIRTH_WILL,
        }
    ),
    _websocket_settings_need_websockets,
    _client_cert_and_key_together,
)

# --- network ---------------------------------------------------------------

NETWORK_SCHEMA: Final = vol.Schema(
    {
        _report_only: vol.Boolean(),
        # An empty list is meaningful — auto-detection — so it is required
        # rather than defaulted: leaving it out is more likely a mistake.
        vol.Required("adapters"): vol.All(_ensure_list, [_adapter_selector]),
    }
)

# --- areas -----------------------------------------------------------------

AREA_SCHEMA: Final = vol.Schema(
    {
        vol.Required("name"): _string,
        vol.Optional("icon"): _icon,
        vol.Optional("floor_id"): _slug,
        vol.Optional("aliases"): vol.All(_ensure_list, [_string]),
        vol.Optional("labels"): vol.All(_ensure_list, [_slug]),
        vol.Optional("picture"): _string,
        vol.Optional("temperature_entity_id"): _entity_id,
        vol.Optional("humidity_entity_id"): _entity_id,
    }
)


def _area_names_unique(conf: dict[str, Any]) -> dict[str, Any]:
    if duplicates := duplicate_names(conf["items"]):
        pairs = "; ".join(f"{first} and {second}" for first, second in duplicates)
        raise vol.Invalid(
            f"areas with the same name (ignoring case and spaces): {pairs}",
            path=["items"],
        )
    return conf


AREAS_SCHEMA: Final = vol.All(
    vol.Schema(
        {
            _report_only: vol.Boolean(),
            # No default: whether areas the YAML doesn't list get deleted is
            # the one decision here that can't be undone, so it is written
            # down rather than assumed.
            vol.Required("mode"): vol.In(["exclusive", "owned"]),
            vol.Optional("items", default=dict): _keyed_by_slug(AREA_SCHEMA),
        }
    ),
    _area_names_unique,
)

# --- the whole block ---------------------------------------------------------

KIND_SCHEMAS: Final = {
    "http": HTTP_SCHEMA,
    "mqtt": MQTT_SCHEMA,
    "network": NETWORK_SCHEMA,
    "areas": AREAS_SCHEMA,
}

BRIDGE_SCHEMA: Final = vol.All(
    # A bare `config_bridge:` loads the integration with nothing to manage,
    # which is how you get at the export service before writing any YAML.
    lambda value: {} if value is None else value,
    vol.Schema({vol.Optional(name): schema for name, schema in KIND_SCHEMAS.items()}),
)
