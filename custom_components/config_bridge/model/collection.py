"""Planning a keyed collection: areas today, other registries later.

The two modes differ only in what may be deleted.

`exclusive`: the YAML is the whole collection. Anything Home Assistant has
that the YAML doesn't list is removed, whoever made it.

`owned`: the YAML is the bridge's share of the collection. Things the bridge
manages are removed when they leave the YAML; things it never managed are left
alone. "Manages" has to survive a restart — the YAML no longer lists an item
once it has been removed from it — so the caller passes in the owned set it
remembered and gets back the one to remember next.

Listing an item that already exists adopts it in either mode: it is updated
to match, and from then on it is owned.
"""

from __future__ import annotations

from collections.abc import Collection, Mapping, Set
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from .diff import FieldChange, creation_fields, diff_fields


class Mode(StrEnum):
    EXCLUSIVE = "exclusive"
    OWNED = "owned"


@dataclass(frozen=True, slots=True)
class ItemChange:
    key: str
    changes: tuple[FieldChange, ...] = ()


@dataclass(frozen=True, slots=True)
class CollectionPlan:
    creates: tuple[ItemChange, ...]
    updates: tuple[ItemChange, ...]
    deletes: tuple[ItemChange, ...]
    owned_after: frozenset[str]
    """What the bridge owns once this plan is applied: exactly what the YAML
    lists. Recorded in both modes, so switching exclusive → owned later
    still knows what the bridge put there."""

    @property
    def is_empty(self) -> bool:
        return not (self.creates or self.updates or self.deletes)


def plan_collection(
    desired: Mapping[str, Mapping[str, Any]],
    live: Mapping[str, Mapping[str, Any]],
    *,
    mode: Mode,
    owned: Set[str],
    secret_fields: Collection[str] = (),
) -> CollectionPlan:
    creates = tuple(
        ItemChange(key, creation_fields(desired[key], secret_fields=secret_fields))
        for key in sorted(desired)
        if key not in live
    )
    updates = tuple(
        ItemChange(key, changes)
        for key in sorted(desired)
        if key in live
        and (
            changes := diff_fields(desired[key], live[key], secret_fields=secret_fields)
        )
    )
    if mode is Mode.EXCLUSIVE:
        doomed = [key for key in live if key not in desired]
    else:
        doomed = [key for key in live if key in owned and key not in desired]
    return CollectionPlan(
        creates=creates,
        updates=updates,
        deletes=tuple(ItemChange(key) for key in sorted(doomed)),
        owned_after=frozenset(desired),
    )
