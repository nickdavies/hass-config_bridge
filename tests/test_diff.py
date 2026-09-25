from __future__ import annotations

from custom_components.config_bridge.model.diff import (
    ABSENT,
    REDACTED,
    FieldChange,
    diff_fields,
    show,
)
from custom_components.config_bridge.model.plan import Plan, Step, render_plan


def test_absent_and_none_are_different_values() -> None:
    # HA spells "no client id" by leaving the key out, and "no icon" as None;
    # swapping one for the other is still a write.
    assert diff_fields({"client_id": None}, {}) == (
        FieldChange("client_id", ABSENT, None),
    )


def test_changes_come_out_in_field_order() -> None:
    changes = diff_fields({"b": 2, "a": 1}, {"a": 0, "c": 3})
    assert [change.field for change in changes] == ["a", "b", "c"]


def test_secrets_are_never_rendered() -> None:
    [change] = diff_fields(
        {"password": "new"}, {"password": "old"}, secret_fields={"password"}
    )
    assert "new" not in change.describe()
    assert "old" not in change.describe()
    assert REDACTED in change.describe()


def test_secret_set_and_removed() -> None:
    assert FieldChange("password", ABSENT, "x", secret=True).describe() == (
        f"password: set ({REDACTED})"
    )
    assert FieldChange("password", "x", ABSENT, secret=True).describe() == (
        "password: removed"
    )


def test_show() -> None:
    assert show(ABSENT) == "unset"
    assert show(None) == "unset"
    assert show("") == '""'
    assert show("mdi:sofa") == "mdi:sofa"
    assert show(["10.244.0.0/16"]) == '["10.244.0.0/16"]'
    assert show({"b": 1, "a": 2}) == '{"a": 2, "b": 1}'


def test_render_plan() -> None:
    plan = Plan(
        steps=(Step("Update the thing", (FieldChange("port", 1883, 8883),)),),
        note="Takes effect later.",
    )
    assert render_plan(plan) == (
        "- Update the thing\n  - port: 1883 → 8883\n\nTakes effect later."
    )
    assert render_plan(Plan()) == "No changes."
