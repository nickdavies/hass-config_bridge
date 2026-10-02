"""InfluxDB: the YAML's schema, and the config entry it renders to.

Only the connection lives in the entry. Everything about what is written
(`include`/`exclude`, `tags`, `measurement_attr` and the rest) stays under
Home Assistant's own `influxdb:` key, which InfluxDB reads at setup; the
bridge doesn't touch it.

Both APIs are rendered, and the YAML's keys say which: `token`,
`organization` and `bucket` for the 2.x API, `database` (with `username` and
`password`) for the 1.x API. The 1.x API is also how InfluxDB 2.x is reached
with a v1 user, whose password, unlike a 2.x token, can be chosen.
Each rendering is the shape InfluxDB's `configure_v1` or `configure_v2` step
stores, so opening the reconfigure dialog and pressing submit changes
nothing. An entry on one API is replaced by the other when the YAML switches.

Written against config entry version 1.1. The Kind refuses to write to any
other version.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Final
from urllib.parse import urlsplit

import probatio

from ...lib.diff import REDACTED
from ...lib.validators import string

# --- the YAML ----------------------------------------------------------------

V2_ONLY: Final = ("token", "organization", "bucket")
V1_ONLY: Final = ("database", "username", "password")


def _url(value: Any) -> str:
    """The 2.x flow stores the URL as typed, so it is checked but not normalised."""
    text = string(value)
    if not text.startswith(("http://", "https://")):
        raise probatio.Invalid("url starts with http:// or https://")
    try:
        if not urlsplit(text).hostname:
            raise probatio.Invalid("url has no host")
        urlsplit(text).port  # noqa: B018 - raises on a bad port
    except ValueError as err:
        raise probatio.Invalid(f"url is not valid: {err}") from err
    return text


def _one_api(conf: dict[str, Any]) -> dict[str, Any]:
    """The keys pick the API; a mix of the two would be half ignored."""
    v2 = [key for key in V2_ONLY if key in conf]
    v1 = [key for key in V1_ONLY if key in conf]
    if v2 and v1:
        raise probatio.Invalid(
            f"{', '.join(v1)} belong to the 1.x API and {', '.join(v2)} to the "
            "2.x API; use one or the other"
        )
    if v2:
        missing = [key for key in V2_ONLY if key not in conf]
        if missing:
            raise probatio.Invalid(f"the 2.x API also needs {', '.join(missing)}")
    elif "database" not in conf:
        raise probatio.Invalid(
            "give token, organization and bucket (2.x API) or database (1.x API)"
        )
    elif ("username" in conf) != ("password" in conf):
        raise probatio.Invalid("username and password go together")
    return conf


SCHEMA: Final = probatio.All(
    probatio.Schema(
        {
            probatio.Required("url"): _url,
            probatio.Optional("token"): string,
            probatio.Optional("organization"): string,
            probatio.Optional("bucket"): string,
            probatio.Optional("database"): string,
            probatio.Optional("username"): string,
            probatio.Optional("password"): string,
            probatio.Optional("verify_ssl"): probatio.Boolean(),
            probatio.Optional("ssl_ca_cert"): string,
        }
    ),
    _one_api,
)

# --- the entry ---------------------------------------------------------------

ENTRY_VERSION: Final = (1, 1)

API_VERSION_1: Final = "1"
API_VERSION_2: Final = "2"
DEFAULT_VERIFY_SSL: Final = True
"""What InfluxDB's YAML import defaults to. The UI form's default is `False`;
the bridge takes the safer of the two."""

V2_KEYS: Final = frozenset(
    ("api_version", "url", "token", "organization", "bucket", "verify_ssl")
)
V1_KEYS: Final = frozenset(
    (
        "api_version",
        "host",
        "port",
        "username",
        "password",
        "database",
        "ssl",
        "path",
        "verify_ssl",
    )
)
DATA_KEYS: Final = frozenset((*V2_KEYS, *V1_KEYS, "ssl_ca_cert"))

SECRET_KEYS: Final = frozenset(("token", "password"))


@dataclass(frozen=True, slots=True)
class RenderedEntry:
    title: str
    data: dict[str, Any]


def render_influxdb(conf: Mapping[str, Any]) -> RenderedEntry:
    """The entry the YAML describes. `conf` is the validated YAML section."""
    if "database" in conf:
        rendered = _render_v1(conf)
    else:
        rendered = _render_v2(conf)
    # The flows store the key only when a certificate was given.
    if "ssl_ca_cert" in conf:
        rendered.data["ssl_ca_cert"] = conf["ssl_ca_cert"]
    return rendered


def _render_v2(conf: Mapping[str, Any]) -> RenderedEntry:
    data: dict[str, Any] = {
        "api_version": API_VERSION_2,
        "url": conf["url"],
        "token": conf["token"],
        "organization": conf["organization"],
        "bucket": conf["bucket"],
        "verify_ssl": conf.get("verify_ssl", DEFAULT_VERIFY_SSL),
    }
    return RenderedEntry(title=f"{conf['bucket']} ({conf['url']})", data=data)


def _render_v1(conf: Mapping[str, Any]) -> RenderedEntry:
    """The 1.x flow splits the URL up, as `yarl` reads it: the scheme's port
    when none is given, and `/` for no path."""
    url = urlsplit(conf["url"])
    https = url.scheme == "https"
    host = url.hostname
    data: dict[str, Any] = {
        "api_version": API_VERSION_1,
        "host": host,
        "port": url.port or (443 if https else 80),
        "username": conf.get("username"),
        "password": conf.get("password"),
        "database": conf["database"],
        "ssl": https,
        "path": url.path or "/",
        "verify_ssl": conf.get("verify_ssl", DEFAULT_VERIFY_SSL),
    }
    return RenderedEntry(title=f"{conf['database']} ({host})", data=data)


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
    if data.get("api_version") == API_VERSION_2:
        exported = {
            key: value
            for key, value in data.items()
            if key in ("url", "token", "organization", "bucket")
        }
    else:
        exported = {"url": _v1_url(data), "database": data.get("database")}
        for key in ("username", "password"):
            if data.get(key) is not None:
                exported[key] = data[key]
    if data.get("verify_ssl", DEFAULT_VERIFY_SSL) != DEFAULT_VERIFY_SSL:
        exported["verify_ssl"] = data["verify_ssl"]
    if data.get("ssl_ca_cert") is not None:
        exported["ssl_ca_cert"] = data["ssl_ca_cert"]
    return {
        key: REDACTED if key in SECRET_KEYS else value
        for key, value in sorted(exported.items())
    }


def _v1_url(data: Mapping[str, Any]) -> str:
    """The URL a 1.x entry's parts came from."""
    url = f"{'https' if data.get('ssl') else 'http'}://{data.get('host')}"
    if data.get("port") is not None:
        url += f":{data['port']}"
    if data.get("path") not in (None, "", "/"):
        url += data["path"]
    return url
