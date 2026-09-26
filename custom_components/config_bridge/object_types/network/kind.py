"""Network: which adapters Home Assistant's discovery listens on.

Stored in `.storage/core.network` and set from Settings → System → Network.
Written through the same call that page makes. zeroconf and ssdp bind their
sockets during bootstrap, before the bridge runs, so a change here, and the
revert of a change made in the UI, takes effect at the next restart.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any, Final

from homeassistant.core import HomeAssistant

from ...lib.diff import FieldChange
from ...lib.kind import Kind, KindError
from ...lib.plan import Plan, Step
from .model import AdapterView, SelectorError, describe_adapters, resolve_adapters

STORE_VERSION: Final = 1
"""The `.storage/core.network` version this Kind was written against."""


async def _network(hass: HomeAssistant) -> Any:
    from homeassistant.components.network import const as network_const  # noqa: PLC0415
    from homeassistant.components.network.network import (  # noqa: PLC0415
        async_get_network,
    )

    if network_const.STORAGE_VERSION != STORE_VERSION:
        raise KindError(
            f"Home Assistant's network store is at version "
            f"{network_const.STORAGE_VERSION}; this bridge was written against "
            f"{STORE_VERSION}."
        )
    return await async_get_network(hass)


def _views(adapters: Iterable[dict[str, Any]]) -> list[AdapterView]:
    return [
        AdapterView(
            name=adapter["name"],
            addresses=tuple(
                f"{address['address']}/{address['network_prefix']}"
                for address in (*adapter["ipv4"], *adapter["ipv6"])
            ),
        )
        for adapter in adapters
    ]


def _shown(names: tuple[str, ...]) -> str:
    return ", ".join(names) if names else "auto-detect"


class NetworkKind(Kind):
    async def async_plan(self) -> Plan:
        network = await _network(self.hass)
        try:
            desired = resolve_adapters(
                self.settings["adapters"], _views(network.adapters)
            )
        except SelectorError as err:
            raise KindError(str(err)) from err
        live = tuple(sorted(network.configured_adapters))
        if desired == live:
            return Plan()
        return Plan(
            steps=(
                Step(
                    "Set the adapters discovery listens on",
                    (FieldChange("adapters", _shown(live), _shown(desired)),),
                ),
            ),
            note="Takes effect the next time Home Assistant restarts.",
            payload=desired,
        )

    async def async_apply(self, plan: Plan) -> None:
        network = await _network(self.hass)
        await network.async_reconfig({"configured_adapters": list(plan.payload)})

    async def async_verify(self, plan: Plan) -> None:
        network = await _network(self.hass)
        if tuple(sorted(network.configured_adapters)) != plan.payload:
            raise KindError("After the write, the configured adapters don't match.")

    @classmethod
    async def async_export(cls, hass: HomeAssistant) -> Any:
        network = await _network(hass)
        return {
            "adapters": sorted(network.configured_adapters),
            # Not part of the YAML: what there is to choose from.
            "available": describe_adapters(_views(network.adapters)),
        }
