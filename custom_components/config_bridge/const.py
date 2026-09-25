"""Constants shared by the engine and the object types."""

from __future__ import annotations

from typing import Final

DOMAIN: Final = "config_bridge"

CONF_REPORT_ONLY: Final = "report_only"
"""Per object type: plan and report, but never write.

The same state an object type falls into on its own when its Kind finds
Home Assistant isn't what it was written against.
"""

ISSUE_REPORT: Final = "report"
"""Translation key for an object type that was not applied. One issue each."""

SERVICE_EXPORT: Final = "export"
