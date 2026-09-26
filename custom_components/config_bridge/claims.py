"""Other integrations pinning their own entities through the bridge.

An integration that creates entities with unique ids gets registry entries a
person can edit in the UI: rename, move to another area, hide. To keep those
in git as well, it claims them at setup, in the shape of the `entities`
object type's items:

    from custom_components.config_bridge import claim_entities

    claim_entities(hass, DOMAIN, {
        "switch.kitchen_killswitch": {"area_id": "kitchen"},
    })

From then on the bridge treats them exactly as if the YAML listed them: at
every boot, once Home Assistant has started, each is put back to what its
claim says, with anything the claim leaves out put back to the integration's
own value. An entity the YAML lists too, or another integration claims, is
reported rather than pinned.

Claiming again replaces the integration's previous claim; an entity it no
longer claims is released at the next boot. Claims are read once Home
Assistant has started, so one made after that applies at the next boot.

This module needs neither the bridge set up nor Home Assistant imported, so
it can be called whether or not the bridge is configured. It only records
the claim; the bridge applies it if it is set up. An integration that wants
to know can list `config_bridge` in its manifest's `after_dependencies` and
check `"config_bridge" in hass.config.components` at setup.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

from .lib.claims import record_claim
from .object_types.entities.model import ITEMS_SCHEMA as ENTITY_ITEMS

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant


def claim_entities(
    hass: HomeAssistant, owner: str, entities: Mapping[str, Mapping[str, Any] | None]
) -> None:
    """Pin `entities`, by entity id, for `owner` (the claiming integration's domain).

    Raises `ValueError` if an item isn't valid; nothing is recorded then.
    """
    record_claim(hass.data, "entities", owner, entities, ENTITY_ITEMS)
