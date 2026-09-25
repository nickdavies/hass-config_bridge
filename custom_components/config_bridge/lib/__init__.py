"""The engine every object type runs on.

- `object_type`: `ObjectType`, how an object type is registered.
- `kind`: `Kind`, the interface an object type implements to read and write
  Home Assistant, and `KindError`.
- `schema`: the `config_bridge:` block's schema, built from the object
  types' own, plus the `report_only` switch they all take.
- `validators`: validators the object types' schemas share.
- `diff`, `plan`, `collection`: field diffs, plans, and the exclusive and
  owned collection planning that object types build their decisions from.
- `runner`: runs each object type inside its own error boundary, raises and
  clears repair issues, and serves the export action.
- `ledger`: the state object types keep between boots.

Everything but `runner` and `ledger` imports no Home Assistant, so the unit
tests run with nothing but pytest and probatio. `tests/test_no_ha_imports.py`
keeps it that way.
"""
