"""InfluxDB: the YAML's schema, and the config entry it renders to.

Only the connection lives in the entry. Everything about what is written
(`include`/`exclude`, `tags`, `measurement_attr` and the rest) stays under
Home Assistant's own `influxdb:` key, which InfluxDB reads at setup; the
bridge doesn't touch it.

Only the 2.x API is rendered: InfluxDB 2.x, and 3.x through its 2.x
compatibility. The rendering is the shape InfluxDB's `configure_v2` step
stores, so opening the reconfigure dialog and pressing submit changes
nothing. A live 1.x entry is replaced by it, which is why the 1.x keys are
known here too.

Written against config entry version 1.1. The Kind refuses to write to any
other version.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Final

import probatio

from ...lib.diff import REDACTED
from ...lib.validators import string

# --- the YAML ----------------------------------------------------------------


def _url(value: Any) -> str:
    """The flow stores the URL as typed, so it is checked but not normalised."""
    text = string(value)
    if not text.startswith(("http://", "https://")):
        raise probatio.Invalid("url starts with http:// or https://")
    return text


SCHEMA: Final = probatio.Schema(
    {
        probatio.Required("url"): _url,
        probatio.Required("token"): string,
        probatio.Required("organization"): string,
        probatio.Required("bucket"): string,
        probatio.Optional("verify_ssl"): probatio.Boolean(),
        probatio.Optional("ssl_ca_cert"): string,
    }
)

# --- the entry ---------------------------------------------------------------

ENTRY_VERSION: Final = (1, 1)

API_VERSION_2: Final = "2"
DEFAULT_VERIFY_SSL: Final = True
"""What InfluxDB's YAML import defaults to. The UI form's default is `False`;
the bridge takes the safer of the two."""

V2_KEYS: Final = frozenset(
    ("api_version", "url", "token", "organization", "bucket", "verify_ssl")
)
V1_KEYS: Final = frozenset(
    ("host", "port", "username", "password", "database", "ssl", "path")
)
DATA_KEYS: Final = frozenset((*V2_KEYS, *V1_KEYS, "ssl_ca_cert"))

SECRET_KEYS: Final = frozenset(("token", "password"))


@dataclass(frozen=True, slots=True)
class RenderedEntry:
    title: str
    data: dict[str, Any]


def render_influxdb(conf: Mapping[str, Any]) -> RenderedEntry:
    """The entry the YAML describes. `conf` is the validated YAML section."""
    data: dict[str, Any] = {
        "api_version": API_VERSION_2,
        "url": conf["url"],
        "token": conf["token"],
        "organization": conf["organization"],
        "bucket": conf["bucket"],
        "verify_ssl": conf.get("verify_ssl", DEFAULT_VERIFY_SSL),
    }
    # The flow stores the key only when a certificate was given.
    if "ssl_ca_cert" in conf:
        data["ssl_ca_cert"] = conf["ssl_ca_cert"]
    return RenderedEntry(title=f"{conf['bucket']} ({conf['url']})", data=data)


def unknown_keys(data: Mapping[str, Any], options: Mapping[str, Any]) -> list[str]:
    """Keys in a live entry this rendering doesn't know about.

    The bridge replaces the whole entry, so an unknown key would be deleted.
    InfluxDB stores no options; any there are unknown.
    """
    return sorted(
        [f"data.{key}" for key in data if key not in DATA_KEYS]
        + [f"options.{key}" for key in options]
    )


def export_influxdb(data: Mapping[str, Any]) -> dict[str, Any]:
    """A live entry as bridge YAML: defaults left out, secrets redacted."""
    if data.get("api_version") != API_VERSION_2:
        raise ValueError(
            "The InfluxDB entry uses the 1.x API, which the bridge doesn't "
            "configure; it would replace it with a 2.x entry."
        )
    exported: dict[str, Any] = {}
    for key, value in data.items():
        if key == "api_version":
            continue
        if key == "verify_ssl" and value == DEFAULT_VERIFY_SSL:
            continue
        if key == "ssl_ca_cert" and value is None:
            continue
        exported[key] = REDACTED if key in SECRET_KEYS else value
    return dict(sorted(exported.items()))
