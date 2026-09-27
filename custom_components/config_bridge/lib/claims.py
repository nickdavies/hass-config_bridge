"""Items other integrations add to an object type, next to the YAML's own.

An integration claims items in the shape of an object type's YAML `items`,
under its own name as the owner (`config_bridge.claims` is what it calls).
The claims live in `hass.data`, per object type and owner, until the object
type's Kind merges them with the YAML's items when it plans.

Every item has exactly one owner. An item the YAML and a claim both list, or
two claims, is a conflict, even with the same settings: which of them
releases it when the other stops listing it would be arbitrary.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, MutableMapping
from typing import Any, Final

import probatio

CLAIMS: Final = "config_bridge_claims"
"""The `hass.data` key: object type, to owner, to its validated items."""

YAML_OWNER: Final = "the YAML"
"""How the YAML's own items are named next to integrations' claims."""


def record_claim(
    data: MutableMapping[str, Any],
    object_type: str,
    owner: str,
    items: Any,
    schema: Callable[[Any], dict[str, Any]],
) -> None:
    """Validate `items` and make them `owner`'s whole claim on `object_type`.

    A bad claim is a bug in the integration making it, so it is raised to
    that integration straight away (as `ValueError`) rather than reported at
    boot, and nothing is recorded.
    """
    if owner == YAML_OWNER:
        raise ValueError(f"{owner!r} is the name the YAML's own items go by")
    try:
        validated = schema(items)
    except probatio.Invalid as err:
        raise ValueError(
            f"{owner} claimed {object_type} the bridge can't pin: {err}"
        ) from err
    data.setdefault(CLAIMS, {}).setdefault(object_type, {})[owner] = validated


def claims_for(data: Mapping[str, Any], object_type: str) -> dict[str, Any]:
    """Every owner's claim on `object_type`."""
    return dict(data.get(CLAIMS, {}).get(object_type, {}))


def merge_claims[T](
    yaml_items: Mapping[str, Any],
    claims: Mapping[str, Mapping[str, Any]],
    render: Callable[[Any], T],
) -> tuple[dict[str, tuple[str, T]], list[str]]:
    """Every listed key with its owner and rendered item, and any conflicts."""
    owners: dict[str, list[str]] = {}
    items: dict[str, Any] = {}
    for owner, owned_items in [(YAML_OWNER, yaml_items), *sorted(claims.items())]:
        for key, item in owned_items.items():
            owners.setdefault(key, []).append(owner)
            items[key] = item
    conflicts = [
        f"{key} is listed by {' and '.join(names)}"
        for key, names in sorted(owners.items())
        if len(names) > 1
    ]
    merged = {
        key: (names[0], render(items[key]))
        for key, names in owners.items()
        if len(names) == 1
    }
    return merged, conflicts


def claimed_by(owner: str) -> str:
    """A suffix naming who claimed an item, for reports; empty for the YAML."""
    return "" if owner == YAML_OWNER else f" (claimed by {owner})"
