"""The `config_bridge:` block's schema, built from the object types' own.

Every object type's YAML is checked here, as part of `CONFIG_SCHEMA`, so a
typo fails `check_config` rather than turning into a report at boot. These
schemas check the YAML's shape only. Home Assistant's own rules for an
object type are applied by its Kind, inside its error boundary: a failing
`CONFIG_SCHEMA` stops the whole integration, where an object type failing
on its own stops only itself.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import probatio

from ..const import CONF_REPORT_ONLY
from .object_type import ObjectType
from .validators import Validator


def with_report_only(schema: Validator) -> Validator:
    """An object type's schema, plus the `report_only` switch they all take.

    The switch belongs to the runner, not the object type: it is validated
    and set aside here, the object type's own schema never sees it, and the
    result always carries it.
    """
    boolean = probatio.Boolean()

    def validate(value: Any) -> Any:
        if not isinstance(value, Mapping):
            # The object type's schema says what it expected instead.
            return schema(value)
        settings = dict(value)
        try:
            report_only = boolean(settings.pop(CONF_REPORT_ONLY, False))
        except probatio.Invalid as err:
            raise probatio.Invalid(err.msg, path=[CONF_REPORT_ONLY]) from err
        return {**schema(settings), CONF_REPORT_ONLY: report_only}

    return validate


def bridge_schema(object_types: Mapping[str, ObjectType]) -> Validator:
    """The whole block: any of the object types, each under its name."""
    return probatio.All(
        # A bare `config_bridge:` loads the integration with nothing to
        # manage, which is how the export action is reached before any YAML
        # is written.
        lambda value: {} if value is None else value,
        probatio.Schema(
            {
                probatio.Optional(name): with_report_only(object_type.schema)
                for name, object_type in object_types.items()
            }
        ),
    )
