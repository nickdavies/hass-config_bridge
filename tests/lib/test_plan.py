from __future__ import annotations

from custom_components.config_bridge.lib.diff import FieldChange
from custom_components.config_bridge.lib.plan import Plan, Step, render_plan


def test_render_plan() -> None:
    plan = Plan(
        steps=(Step("Update the thing", (FieldChange("port", 1883, 8883),)),),
        note="Takes effect at the next restart.",
    )
    assert render_plan(plan) == (
        "- Update the thing\n  - port: 1883 → 8883\n\nTakes effect at the next restart."
    )
    assert render_plan(Plan()) == "No changes."


def test_in_sync_means_no_steps_and_not_blocked() -> None:
    assert Plan().in_sync
    assert not Plan(steps=(Step("Do it"),)).in_sync
    assert not Plan(blocked="No.").in_sync
