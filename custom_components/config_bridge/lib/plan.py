"""What one object type intends to do, in a form both the runner and a report
can use."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .diff import FieldChange


@dataclass(frozen=True, slots=True)
class Step:
    """One write, described for a person. `changes` are the fields it moves."""

    summary: str
    changes: tuple[FieldChange, ...] = ()


@dataclass(frozen=True, slots=True)
class Plan:
    """The difference between the YAML and Home Assistant, for one object type.

    `blocked` is set when something differs but the Kind has decided it must
    not act on it: HTTP refusing to re-stage a config HA could not bind, say.
    A blocked plan is reported exactly like a failed one: the steps show what
    would have happened, and nothing is written.

    `payload` is private to the Kind that produced the plan: whatever its
    `apply` needs, carried through the runner untouched.
    """

    steps: tuple[Step, ...] = ()
    blocked: str | None = None
    note: str | None = None
    payload: Any = None

    @property
    def in_sync(self) -> bool:
        return not self.steps and self.blocked is None


def render_plan(plan: Plan) -> str:
    """Markdown for logs and repair issues. Secrets are already redacted."""
    lines: list[str] = []
    for step in plan.steps:
        lines.append(f"- {step.summary}")
        lines.extend(f"  - {change.describe()}" for change in step.changes)
    if plan.note:
        lines.append("")
        lines.append(plan.note)
    return "\n".join(lines) if lines else "No changes."
