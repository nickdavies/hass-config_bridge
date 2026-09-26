"""Runs each object type inside its own error boundary.

An object type ends every run in one of three places:

- **in sync**: nothing to do;
- **applied**: the writes were made and re-reading confirmed them;
- **reported**: nothing was written, and a repair issue says why and what
  would have changed.

Reported covers `report_only: true`, a plan the Kind blocked itself, and
anything at all going wrong while importing the Kind, planning, applying or
verifying. Kinds read and write Home Assistant internals; when one of those
isn't what a Kind was written against, that object type reports and the
others carry on. Nothing here fails Home Assistant's setup.

An apply that fails partway may leave some writes made. The report says the
apply failed; the next boot plans from whatever is there and finishes the
job or reports again.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable, Mapping
from enum import StrEnum
from typing import Any

from homeassistant.core import (
    HomeAssistant,
    ServiceCall,
    ServiceResponse,
    SupportsResponse,
)
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.service import async_register_admin_service
from homeassistant.helpers.start import async_at_started

from ..const import CONF_REPORT_ONLY, DOMAIN, ISSUE_REPORT, SERVICE_EXPORT
from .kind import Kind, KindError, RunAt
from .ledger import Ledger
from .object_type import ObjectType
from .plan import Plan, render_plan

_LOGGER = logging.getLogger(__name__)


class Outcome(StrEnum):
    IN_SYNC = "in_sync"
    APPLIED = "applied"
    REPORTED = "reported"


async def async_setup_bridge(
    hass: HomeAssistant,
    conf: Mapping[str, Any],
    object_types: Mapping[str, ObjectType],
) -> None:
    """Run each configured object type, now or once Home Assistant has started."""
    ledger = Ledger(hass)
    await ledger.async_load()

    for name, type_conf in conf.items():
        report_only = bool(type_conf[CONF_REPORT_ONLY])
        settings = {
            key: value for key, value in type_conf.items() if key != CONF_REPORT_ONLY
        }
        try:
            kind_class = object_types[name].load_kind()
            kind = kind_class(hass, settings, ledger.scope(name))
        except Exception as err:  # noqa: BLE001 - the boundary is the point
            _report(hass, name, _reason(err, _LOADING))
            continue
        if kind.run_at is RunAt.SETUP:
            await async_run_kind(hass, name, kind, report_only=report_only)
        else:
            async_at_started(hass, _runner_for(name, kind, report_only))

    # Object types that aren't configured are cleared too, so taking one out
    # of the YAML doesn't leave its last report behind.
    for name in object_types.keys() - conf.keys():
        ir.async_delete_issue(hass, DOMAIN, _issue_id(name))

    async def export(call: ServiceCall) -> ServiceResponse:
        return await _async_export(call.hass, object_types)

    async_register_admin_service(
        hass,
        DOMAIN,
        SERVICE_EXPORT,
        export,
        supports_response=SupportsResponse.ONLY,
    )


def _runner_for(
    name: str, kind: Kind, report_only: bool
) -> Callable[[HomeAssistant], Awaitable[None]]:
    async def run(hass: HomeAssistant) -> None:
        await async_run_kind(hass, name, kind, report_only=report_only)

    return run


async def async_run_kind(
    hass: HomeAssistant, name: str, kind: Kind, *, report_only: bool
) -> Outcome:
    """Plan, then apply and verify unless that's not allowed. Never raises."""
    try:
        plan = await kind.async_plan()
    except Exception as err:  # noqa: BLE001
        return _report(hass, name, _reason(err, _PLANNING))

    if plan.blocked is not None:
        return _report(hass, name, plan.blocked, plan)

    if plan.in_sync:
        if not report_only:
            try:
                await kind.async_remember(plan)
            except Exception as err:  # noqa: BLE001
                return _report(hass, name, _reason(err, _RECORDING))
        _LOGGER.debug("%s: in sync", name)
        _clear(hass, name)
        return Outcome.IN_SYNC

    if report_only:
        return _report(
            hass, name, "`report_only` is set, so these changes were not applied.", plan
        )

    try:
        await kind.async_apply(plan)
        await kind.async_verify(plan)
        await kind.async_remember(plan)
    except Exception as err:  # noqa: BLE001
        return _report(hass, name, _reason(err, _APPLYING), plan)

    _LOGGER.info("%s: applied\n%s", name, render_plan(plan))
    _clear(hass, name)
    return Outcome.APPLIED


_LOADING = "while importing its Kind"
_PLANNING = "while reading Home Assistant"
_RECORDING = "while recording its state for the next boot"
_APPLYING = "while applying, so some of these changes may already have been made"


def _reason(err: Exception, phase: str) -> str:
    """The report's opening line.

    A `KindError` is the Kind explaining itself, and while planning it is
    the whole story. Anything else is unexpected: the traceback goes to the
    log and the type into the report, because "KeyError: 'stable'" says far
    more than "'stable'".
    """
    if isinstance(err, KindError):
        return str(err) if phase is _PLANNING else f"Failed {phase}: {err}"
    _LOGGER.exception("Unexpected error in the config bridge")
    return f"Unexpected error {phase}: {type(err).__name__}: {err}"


def _report(
    hass: HomeAssistant, name: str, reason: str, plan: Plan | None = None
) -> Outcome:
    changes = (
        render_plan(plan)
        if plan is not None
        else "Unknown: the plan could not be made."
    )
    _LOGGER.warning("%s: not applied. %s\n%s", name, reason, changes)
    ir.async_create_issue(
        hass,
        DOMAIN,
        _issue_id(name),
        is_fixable=False,
        severity=ir.IssueSeverity.WARNING,
        translation_key=ISSUE_REPORT,
        translation_placeholders={
            "object_type": name,
            "reason": reason,
            "changes": changes,
        },
    )
    return Outcome.REPORTED


def _clear(hass: HomeAssistant, name: str) -> None:
    ir.async_delete_issue(hass, DOMAIN, _issue_id(name))


def _issue_id(name: str) -> str:
    return f"{ISSUE_REPORT}_{name}"


async def _async_export(
    hass: HomeAssistant, object_types: Mapping[str, ObjectType]
) -> ServiceResponse:
    """What Home Assistant has, per object type, in the shape of the YAML.

    For writing the YAML in the first place: call it from Developer Tools →
    Actions, and paste. Each object type is exported on its own, so one that
    can't be read still leaves the others' output intact.
    """
    exported: dict[str, Any] = {}
    for name, object_type in object_types.items():
        try:
            exported[name] = await object_type.load_kind().async_export(hass)
        except Exception as err:  # noqa: BLE001
            _LOGGER.exception("Couldn't export %s", name)
            exported[name] = {"error": f"{type(err).__name__}: {err}"}
    return exported
