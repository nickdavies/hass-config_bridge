"""What the bridge has to remember between boots. Deliberately little.

None of this is a source of truth — the YAML is. Losing the file (a restored
backup, a fresh volume) costs two things, both in the safe direction: areas
an `owned` section has since dropped are left in place instead of deleted,
and an HTTP config that was re-staged once may be re-staged once more.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from typing import Any, Final

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

STORAGE_KEY: Final = DOMAIN
STORAGE_VERSION: Final = 1

_OWNED: Final = "owned"
_HTTP_RESTAGED: Final = "http_restaged"


class Ledger:
    def __init__(self, hass: HomeAssistant) -> None:
        self._store: Store[dict[str, Any]] = Store(
            hass, STORAGE_VERSION, STORAGE_KEY, atomic_writes=True
        )
        self._data: dict[str, Any] = {}

    async def async_load(self) -> None:
        """Load, or start empty. An unreadable ledger must not stop the kinds.

        Starting empty is the safe failure described above, so it is logged
        and carried on from rather than raised.
        """
        try:
            self._data = await self._store.async_load() or {}
        except Exception:
            _LOGGER.exception("Could not load the config bridge ledger; starting empty")
            self._data = {}

    def owned(self, kind: str) -> frozenset[str]:
        return frozenset(self._data.get(_OWNED, {}).get(kind, ()))

    async def async_set_owned(self, kind: str, keys: Iterable[str]) -> None:
        keys = sorted(keys)
        if self._data.get(_OWNED, {}).get(kind) == keys:
            return
        self._data.setdefault(_OWNED, {})[kind] = keys
        await self._store.async_save(self._data)

    @property
    def http_restaged(self) -> str | None:
        """Fingerprint of the HTTP config last re-staged after a revert."""
        return self._data.get(_HTTP_RESTAGED)

    async def async_set_http_restaged(self, fingerprint: str | None) -> None:
        if self._data.get(_HTTP_RESTAGED) == fingerprint:
            return
        self._data[_HTTP_RESTAGED] = fingerprint
        await self._store.async_save(self._data)
