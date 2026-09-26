"""State the object types keep between boots, in `.storage/config_bridge`.

Each object type has its own slice, under its name, through `KindState`.
None of it is a source of truth (the YAML is), so losing the file may only
cost something in the safe direction. Each Kind that keeps state says what
it keeps and what losing it costs.
"""

from __future__ import annotations

import logging
from typing import Any, Final

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from ..const import DOMAIN

_LOGGER = logging.getLogger(__name__)

STORAGE_KEY: Final = DOMAIN
STORAGE_VERSION: Final = 1


class Ledger:
    """The whole store. The runner loads it once and hands out slices."""

    def __init__(self, hass: HomeAssistant) -> None:
        self._store: Store[dict[str, Any]] = Store(
            hass, STORAGE_VERSION, STORAGE_KEY, atomic_writes=True
        )
        self._data: dict[str, Any] = {}

    async def async_load(self) -> None:
        """Load, or start empty. An unreadable ledger must not stop anything.

        Starting empty is the safe failure described above, so it is logged
        and carried on from rather than raised.
        """
        try:
            self._data = await self._store.async_load() or {}
        except Exception:
            _LOGGER.exception("Could not load the config bridge ledger; starting empty")
            self._data = {}

    def scope(self, name: str) -> KindState:
        """The slice for the object type called `name`."""
        return KindState(self, name)

    def _get(self, name: str, key: str, default: Any) -> Any:
        return self._data.get(name, {}).get(key, default)

    async def _async_set(self, name: str, key: str, value: Any) -> None:
        section = self._data.get(name, {})
        if section.get(key) == value:
            return
        if value is None:
            section.pop(key, None)
        else:
            section[key] = value
        if section:
            self._data[name] = section
        else:
            self._data.pop(name, None)
        await self._store.async_save(self._data)


class KindState:
    """One object type's slice of the ledger. Values must be JSON."""

    def __init__(self, ledger: Ledger, name: str) -> None:
        self._ledger = ledger
        self._name = name

    def get(self, key: str, default: Any = None) -> Any:
        return self._ledger._get(self._name, key, default)

    async def async_set(self, key: str, value: Any) -> None:
        """Store `value` under `key`, or remove it for None. Saves only on change."""
        await self._ledger._async_set(self._name, key, value)
