"""Constants shared by the model and the Home Assistant layer."""

from __future__ import annotations

from typing import Final

DOMAIN: Final = "config_bridge"

CONF_REPORT_ONLY: Final = "report_only"
"""Per kind: compute and report the plan, but never write.

The same state a kind falls into on its own when something about Home
Assistant no longer matches what its adapter was written against — pinning it
in YAML is for when you want that on purpose, say across an upgrade you don't
trust yet.
"""

ISSUE_REPORT: Final = "report"
"""Translation key for a kind that was not applied. One issue per kind."""

SERVICE_EXPORT: Final = "export"
