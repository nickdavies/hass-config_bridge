"""The contract between the runner and one kind's adapter."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping
from enum import Enum
from typing import Any, ClassVar

from homeassistant.core import HomeAssistant

from ..const import CONF_REPORT_ONLY
from ..ledger import Ledger
from ..model.plan import Plan


class KindError(Exception):
    """This kind can't be reconciled now. The message is the report's reason.

    Raised for anything the adapter recognises: a store version it wasn't
    written against, a live object with keys it doesn't know, a reference to
    something that doesn't exist. Anything else that escapes is caught by the
    runner too — this just lets the report say why in words.
    """


class RunAt(Enum):
    SETUP = "setup"
    """As soon as the bridge loads, during bootstrap."""
    STARTED = "started"
    """Once Home Assistant has started and every integration's entities exist."""


class Kind(ABC):
    """One kind of thing the bridge reconciles.

    The runner calls `async_plan`, then — unless the plan is in sync, blocked
    or the kind is report-only — `async_apply` and `async_verify`. Each call
    reads Home Assistant afresh; nothing is cached between them, so verify
    checks what is actually there now.

    Imports of Home Assistant internals (anything under `components.`) belong
    inside these methods, not at module level: a renamed module then fails
    this kind, inside its error boundary, instead of failing the import of the
    whole bridge.
    """

    name: ClassVar[str]
    run_at: ClassVar[RunAt] = RunAt.SETUP

    def __init__(
        self, hass: HomeAssistant, conf: Mapping[str, Any], ledger: Ledger
    ) -> None:
        self.hass = hass
        self.conf = conf
        self.ledger = ledger

    @property
    def report_only(self) -> bool:
        return bool(self.conf.get(CONF_REPORT_ONLY, False))

    @property
    def settings(self) -> dict[str, Any]:
        """The kind's YAML without the bridge's own switches."""
        return {
            key: value for key, value in self.conf.items() if key != CONF_REPORT_ONLY
        }

    @abstractmethod
    async def async_plan(self) -> Plan:
        """Read Home Assistant and decide. Must not write anything."""

    @abstractmethod
    async def async_apply(self, plan: Plan) -> None:
        """Make the writes the plan describes."""

    @abstractmethod
    async def async_verify(self, plan: Plan) -> None:
        """Re-read and raise `KindError` if Home Assistant doesn't match."""

    async def async_remember(self, plan: Plan) -> None:
        """Record bookkeeping once the kind is known to match the YAML.

        Called after a successful apply *and* when already in sync — an
        `owned` area that already matched on the first run is still owned
        from then on. Not called when reporting.
        """

    @classmethod
    @abstractmethod
    async def async_export(cls, hass: HomeAssistant) -> Any:
        """What Home Assistant has now, in the shape of this kind's YAML."""
