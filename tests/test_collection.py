"""The two modes, which differ only in what they may delete."""

from __future__ import annotations

from custom_components.config_bridge.model.collection import Mode, plan_collection
from custom_components.config_bridge.model.diff import ABSENT, FieldChange

KITCHEN = {"name": "Kitchen", "icon": None}
LOUNGE = {"name": "Lounge", "icon": "mdi:sofa"}


def keys(items) -> list[str]:
    return [item.key for item in items]


def test_creates_updates_and_leaves_matching_alone() -> None:
    plan = plan_collection(
        {"kitchen": KITCHEN, "lounge": LOUNGE, "office": {"name": "Office"}},
        {"kitchen": KITCHEN, "lounge": {"name": "Lounge", "icon": None}},
        mode=Mode.OWNED,
        owned=frozenset(),
    )
    assert keys(plan.creates) == ["office"]
    assert keys(plan.updates) == ["lounge"]
    assert plan.updates[0].changes == (FieldChange("icon", None, "mdi:sofa"),)
    assert plan.deletes == ()


def test_exclusive_deletes_everything_unlisted() -> None:
    plan = plan_collection(
        {"kitchen": KITCHEN},
        {"kitchen": KITCHEN, "garage": {"name": "Garage"}, "shed": {"name": "Shed"}},
        mode=Mode.EXCLUSIVE,
        owned=frozenset(),
    )
    assert keys(plan.deletes) == ["garage", "shed"]


def test_owned_deletes_only_what_it_owned() -> None:
    plan = plan_collection(
        {"kitchen": KITCHEN},
        {"kitchen": KITCHEN, "garage": {"name": "Garage"}, "shed": {"name": "Shed"}},
        mode=Mode.OWNED,
        # garage was listed last time and has been removed from the YAML; shed
        # was made in the UI and never listed.
        owned=frozenset({"kitchen", "garage"}),
    )
    assert keys(plan.deletes) == ["garage"]


def test_owned_ignores_owned_items_already_gone() -> None:
    plan = plan_collection(
        {}, {}, mode=Mode.OWNED, owned=frozenset({"deleted_in_the_ui"})
    )
    assert plan.is_empty
    assert plan.owned_after == frozenset()


def test_listing_adopts() -> None:
    plan = plan_collection(
        {"kitchen": KITCHEN},
        {"kitchen": KITCHEN},
        mode=Mode.OWNED,
        owned=frozenset(),
    )
    assert plan.is_empty
    assert plan.owned_after == {"kitchen"}


def test_creation_changes_skip_empty_fields() -> None:
    plan = plan_collection(
        {"office": {"name": "Office", "icon": None, "aliases": []}},
        {},
        mode=Mode.OWNED,
        owned=frozenset(),
    )
    assert plan.creates[0].changes == (FieldChange("name", ABSENT, "Office"),)
