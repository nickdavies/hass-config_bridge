"""Running the kinds, each inside its own error boundary.

A kind ends every run in one of three places:

- **in sync** — nothing to do;
- **applied** — the writes were made and re-reading confirmed them;
- **reported** — nothing was written, and a repair issue says why and what
  would have changed.

Reported covers `report_only: true`, a plan the kind blocked itself, and
anything at all going wrong while planning, applying or verifying. That last
part is the point: the bridge leans on Home Assistant internals that will
move, and when one does, that kind should go quiet and say so while the rest
carry on — never take down the others, and never fail Home Assistant's setup.

An apply that fails partway may leave some writes made. The report says the
apply failed; the next boot plans from whatever is there and finishes the job
or reports again.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
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

from .const import DOMAIN, ISSUE_REPORT, SERVICE_EXPORT
from .kinds import KINDS
from .kinds.base import Kind, KindError, RunAt
from .ledger import Ledger
from .model.plan import Plan, render_plan

_LOGGER = logging.getLogger(__name__)


class Outcome(StrEnum):
    IN_SYNC = "in_sync"
    APPLIED = "applied"
    REPORTED = "reported"


async def async_setup_bridge(hass: HomeAssistant, conf: Mapping[str, Any]) -> None:
    ledger = Ledger(hass)
    await ledger.async_load()

    for name, kind_conf in conf.items():
        kind = KINDS[name](hass, kind_conf, ledger)
        if kind.run_at is RunAt.SETUP:
            await async_run_kind(hass, kind)
        else:
            async_at_started(hass, _runner_for(kind))

    # Kinds that aren't configured are cleared too, so taking one out of the
    # YAML doesn't leave its last report behind forever.
    for name in KINDS.keys() - conf.keys():
        ir.async_delete_issue(hass, DOMAIN, _issue_id(name))

    async_register_admin_service(
        hass,
        DOMAIN,
        SERVICE_EXPORT,
        _async_export,
        supports_response=SupportsResponse.ONLY,
    )


def _runner_for(kind: Kind):
    async def run(hass: HomeAssistant) -> None:
        await async_run_kind(hass, kind)

    return run


async def async_run_kind(hass: HomeAssistant, kind: Kind) -> Outcome:
    """Plan, then apply and verify unless that's not allowed. Never raises."""
    try:
        plan = await kind.async_plan()
    except Exception as err:  # noqa: BLE001 - the boundary is the point
        return _report(hass, kind, _reason(err, _PLANNING))

    if plan.blocked is not None:
        return _report(hass, kind, plan.blocked, plan)

    if plan.in_sync:
        if not kind.report_only:
            try:
                await kind.async_remember(plan)
            except Exception as err:  # noqa: BLE001
                return _report(hass, kind, _reason(err, _RECORDING))
        _LOGGER.debug("%s: in sync", kind.name)
        _clear(hass, kind)
        return Outcome.IN_SYNC

    if kind.report_only:
        return _report(
            hass, kind, "`report_only` is set, so these changes were not applied.", plan
        )

    try:
        await kind.async_apply(plan)
        await kind.async_verify(plan)
        await kind.async_remember(plan)
    except Exception as err:  # noqa: BLE001
        return _report(hass, kind, _reason(err, _APPLYING), plan)

    _LOGGER.info("%s: applied\n%s", kind.name, render_plan(plan))
    _clear(hass, kind)
    return Outcome.APPLIED


_PLANNING = "while reading Home Assistant"
_RECORDING = "while recording what the bridge owns"
_APPLYING = "while applying, so some of these changes may already have been made"


def _reason(err: Exception, phase: str) -> str:
    """The report's opening line.

    A `KindError` is the adapter explaining itself, and while planning it is
    the whole story. Anything else is unexpected: the traceback goes to the
    log and the type into the report, because "KeyError: 'stable'" says far
    more than "'stable'".
    """
    if isinstance(err, KindError):
        return str(err) if phase is _PLANNING else f"Failed {phase}: {err}"
    _LOGGER.exception("Unexpected error in the config bridge")
    return f"Unexpected error {phase}: {type(err).__name__}: {err}"


def _report(
    hass: HomeAssistant, kind: Kind, reason: str, plan: Plan | None = None
) -> Outcome:
    changes = (
        render_plan(plan)
        if plan is not None
        else "Unknown — the plan could not be made."
    )
    _LOGGER.warning("%s: not applied. %s\n%s", kind.name, reason, changes)
    ir.async_create_issue(
        hass,
        DOMAIN,
        _issue_id(kind.name),
        is_fixable=False,
        severity=ir.IssueSeverity.WARNING,
        translation_key=ISSUE_REPORT,
        translation_placeholders={
            "kind": kind.name,
            "reason": reason,
            "changes": changes,
        },
    )
    return Outcome.REPORTED


def _clear(hass: HomeAssistant, kind: Kind) -> None:
    ir.async_delete_issue(hass, DOMAIN, _issue_id(kind.name))


def _issue_id(kind_name: str) -> str:
    return f"{ISSUE_REPORT}_{kind_name}"


async def _async_export(call: ServiceCall) -> ServiceResponse:
    """What Home Assistant has now, per kind, in the shape of the YAML.

    For writing the YAML in the first place: call it from Developer Tools →
    Actions, and paste. Each kind is exported on its own, so one that can't
    be read still leaves the others' output intact.
    """
    exported: dict[str, Any] = {}
    for name, kind in KINDS.items():
        try:
            exported[name] = await kind.async_export(call.hass)
        except Exception as err:  # noqa: BLE001
            _LOGGER.exception("Couldn't export %s", name)
            exported[name] = {"error": f"{type(err).__name__}: {err}"}
    return exported
