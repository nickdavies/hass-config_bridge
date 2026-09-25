"""Field-level differences between what the YAML asks for and what HA has.

Every kind flattens its object to a mapping of field to value before it gets
here, so one differ serves an MQTT entry, the HTTP config and an area alike.
What it adds over `!=` is what a report needs: which fields moved, and a
rendering that never prints a secret.
"""

from __future__ import annotations

import json
from collections.abc import Collection, Mapping
from dataclasses import dataclass
from typing import Any, Final


class _Absent:
    """A field the object does not have at all, as opposed to one set to None.

    Home Assistant spells "no client id" by leaving the key out of an entry's
    data, and "no icon" as `icon: None`. Both read as unset to a person, but
    turning one into the other is still a write the object would see, so the
    differ keeps them apart and only the rendering merges them.
    """

    _instance: _Absent | None = None

    def __new__(cls) -> _Absent:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __repr__(self) -> str:
        return "ABSENT"


ABSENT: Final = _Absent()

REDACTED: Final = "<redacted>"


@dataclass(frozen=True, slots=True)
class FieldChange:
    """One field that differs. `old` is what Home Assistant has now."""

    field: str
    old: Any
    new: Any
    secret: bool = False

    def describe(self) -> str:
        if self.secret:
            if _unset(self.old):
                return f"{self.field}: set ({REDACTED})"
            if _unset(self.new):
                return f"{self.field}: removed"
            return f"{self.field}: changed ({REDACTED})"
        return f"{self.field}: {show(self.old)} → {show(self.new)}"


def diff_fields(
    desired: Mapping[str, Any],
    live: Mapping[str, Any],
    *,
    secret_fields: Collection[str] = (),
) -> tuple[FieldChange, ...]:
    """Every field whose value differs, in field order.

    A key present on one side only compares against `ABSENT`, so a field the
    YAML drops is reported (and later removed) rather than silently kept.
    """
    changes: list[FieldChange] = []
    for field in sorted(set(desired) | set(live)):
        old = live.get(field, ABSENT)
        new = desired.get(field, ABSENT)
        if old == new:
            continue
        changes.append(FieldChange(field, old, new, secret=field in secret_fields))
    return tuple(changes)


def creation_fields(
    desired: Mapping[str, Any], *, secret_fields: Collection[str] = ()
) -> tuple[FieldChange, ...]:
    """What a newly created object will be set to, leaving out empty fields.

    Against an object that doesn't exist every field "changes", which buries
    the three that matter under a list of `unset → unset`.
    """
    return tuple(
        FieldChange(field, ABSENT, value, secret=field in secret_fields)
        for field, value in sorted(desired.items())
        if not _unset(value) and value not in ([], (), {})
    )


def show(value: Any) -> str:
    """A compact rendering for reports: strings bare, everything else as JSON."""
    if _unset(value):
        return "unset"
    if isinstance(value, str):
        return value if value else '""'
    return json.dumps(value, sort_keys=True, ensure_ascii=False, default=str)


def _unset(value: Any) -> bool:
    return value is ABSENT or value is None
