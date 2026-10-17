"""Energy: the energy dashboard's preferences, in `.storage/energy`.

Set from Settings → Dashboards → Energy, and written here through the same
call that page's save makes, so energy's listeners (the cost sensors it
makes for a price) see the change on this boot. Home Assistant's own schemas
for the preferences are applied to the rendered YAML first, so a rule only
it knows (a meter used by two grid connections, say) reports rather than
writes.

Runs once Home Assistant has started, after `entities`: an entity id that
`entities` renames back is the one the preferences refer to.
"""

from __future__ import annotations

from typing import Any, Final

import probatio
from homeassistant.core import HomeAssistant

from ...lib.diff import creation_fields, diff_fields
from ...lib.kind import Kind, KindError, RunAt
from ...lib.plan import Plan, Step
from . import model

ENERGY_DOMAIN: Final = "energy"


def _check_store_version() -> None:
    from homeassistant.components.energy import data  # noqa: PLC0415

    current = (data.STORAGE_VERSION, data.STORAGE_MINOR_VERSION)
    if current != model.STORE_VERSION:
        raise KindError(
            f"Home Assistant's energy store is at version {current[0]}."
            f"{current[1]}; this bridge was written against "
            f"{model.STORE_VERSION[0]}.{model.STORE_VERSION[1]}."
        )


async def _manager(hass: HomeAssistant) -> Any:
    _check_store_version()
    from homeassistant.components.energy.data import (  # noqa: PLC0415
        async_get_manager,
    )

    return await async_get_manager(hass)


def _live(manager: Any) -> dict[str, Any]:
    """The preferences, or the defaults when nothing has been saved yet."""
    return dict(manager.data or manager.default_preferences())


def _render(settings: Any) -> dict[str, list[dict[str, Any]]]:
    """The YAML as Home Assistant would store it, once its own schemas pass it."""
    from homeassistant.components.energy.data import (  # noqa: PLC0415
        DEVICE_CONSUMPTION_SCHEMA,
        ENERGY_SOURCE_SCHEMA,
    )
    from homeassistant.components.energy.helpers import (  # noqa: PLC0415
        generate_power_sensor_entity_id,
    )

    rendered = model.render_energy(settings, generate_power_sensor_entity_id)
    try:
        ENERGY_SOURCE_SCHEMA(rendered["energy_sources"])
        for devices in model.LISTS[1:]:
            probatio.Schema([DEVICE_CONSUMPTION_SCHEMA])(rendered[devices])
    except probatio.Invalid as err:
        raise KindError(
            f"Home Assistant's energy schema refuses the YAML: {err}"
        ) from err
    return rendered


class EnergyKind(Kind):
    run_at = RunAt.STARTED

    async def async_plan(self) -> Plan:
        if ENERGY_DOMAIN not in self.hass.config.components:
            raise KindError(
                "The energy integration isn't loaded, so nothing would read "
                "these preferences. It is part of `default_config:`."
            )
        manager = await _manager(self.hass)
        desired = _render(self.settings)
        live = _live(manager)
        if unknown := model.unknown_keys(live):
            raise KindError(
                "The energy preferences have settings the bridge doesn't know, "
                f"and replacing them would delete them: {', '.join(unknown)}."
            )
        if manager.data is None:
            if desired == manager.default_preferences():
                return Plan()
            changes = creation_fields(model.flatten(desired))
        else:
            changes = diff_fields(model.flatten(desired), model.flatten(live))
        if not changes:
            return Plan()
        return Plan(
            steps=(Step("Set the energy dashboard's preferences", changes),),
            payload=desired,
        )

    async def async_apply(self, plan: Plan) -> None:
        manager = await _manager(self.hass)
        # Copies, so the manager never shares a list with the plan and verify
        # compares what Home Assistant holds rather than the plan to itself.
        await manager.async_update(
            {name: [dict(item) for item in plan.payload[name]] for name in model.LISTS}
        )

    async def async_verify(self, plan: Plan) -> None:
        manager = await _manager(self.hass)
        if diff_fields(model.flatten(plan.payload), model.flatten(_live(manager))):
            raise KindError(
                "After the write, the energy preferences don't match the YAML."
            )

    @classmethod
    async def async_export(cls, hass: HomeAssistant) -> Any:
        return model.export_energy(_live(await _manager(hass)))
