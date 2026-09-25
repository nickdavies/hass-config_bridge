"""Validators the object types' schemas share.

Written with probatio alone rather than Home Assistant's
`config_validation`, so the schemas import no Home Assistant and the unit
tests run without it. Where a validator stands in for one of HA's, it says
which.
"""

from __future__ import annotations

import ipaddress
import re
from collections.abc import Callable, Mapping
from typing import Any, Final

import probatio as vol

Validator = Callable[[Any], Any]

SLUG_RE: Final = re.compile(r"^[a-z0-9]+(_[a-z0-9]+)*$")
"""What `slugify` can produce: Home Assistant's rule for area, floor and
label ids (`cv.slug` checks `slugify(value) == value`)."""

ENTITY_ID_RE: Final = re.compile(
    r"^(?!.+__)(?!_)[\da-z_]+(?<!_)\.(?!_)[\da-z_]+(?<!_)$"
)
"""`homeassistant.core.VALID_ENTITY_ID`."""


def string(value: Any) -> str:
    """`cv.string`: numbers become strings, anything else structured is refused.

    A YAML password of `12345` arrives as an int and should still work.
    """
    if isinstance(value, bool) or value is None:
        raise vol.Invalid("expected a string")
    if isinstance(value, (str, int, float)):
        return str(value)
    raise vol.Invalid("expected a string")


def ensure_list(value: Any) -> list[Any]:
    """`cv.ensure_list`: one value becomes a list of one, and None an empty list."""
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def slug(value: Any) -> str:
    """An id: `cv.slug`."""
    text = string(value)
    if not SLUG_RE.match(text):
        raise vol.Invalid(
            f"{text!r} is not a valid id: use lowercase letters and digits "
            "joined by single underscores"
        )
    return text


def entity_id(value: Any) -> str:
    """`cv.entity_id`: lowercased, then checked."""
    text = string(value).lower()
    if not ENTITY_ID_RE.match(text):
        raise vol.Invalid(f"{text!r} is not a valid entity id")
    return text


def icon(value: Any) -> str:
    """`cv.icon`."""
    text = string(value)
    if ":" not in text:
        raise vol.Invalid('icons are written as "prefix:name", e.g. mdi:sofa')
    return text


def ip_network(value: Any) -> str:
    """A network, read strictly: host bits are an error.

    `10.244.0.1/16` is refused, as Home Assistant's HTTP schema refuses it.
    """
    try:
        return str(ipaddress.ip_network(string(value)))
    except ValueError as err:
        raise vol.Invalid(str(err)) from err


port: Final = vol.All(vol.Coerce(int), vol.Range(min=1, max=65535))
"""`cv.port`."""


def keyed_by_slug(item_schema: Validator) -> Validator:
    """A mapping whose keys are ids: `cv.schema_with_slug_keys`, spelled out.

    Errors carry the key in their path, so a report points at the item.
    """

    def validate(value: Any) -> dict[str, Any]:
        if value is None:
            return {}
        if not isinstance(value, Mapping):
            raise vol.Invalid("expected a mapping of id to settings")
        validated: dict[str, Any] = {}
        for key, item in value.items():
            try:
                item_id = slug(key)
            except vol.Invalid as err:
                raise vol.Invalid(err.msg, path=[key]) from err
            try:
                validated[item_id] = item_schema(item)
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
