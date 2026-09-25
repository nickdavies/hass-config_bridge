"""The bridge's decisions, with no Home Assistant in them.

Everything that decides *what* to do lives here: validating the YAML,
rendering it into the shape Home Assistant stores, diffing against what it
has, and choosing between create, update, delete, stage or refuse. The
adapters in `kinds/` only read Home Assistant into plain mappings and write
the result back.

Keeping this side free of Home Assistant imports is what lets it be unit
tested with nothing but pytest and voluptuous — and it is also the hedge
against Home Assistant closing off an internal API: the decisions would
survive a move to a different way of reading and writing, whether that is
the websocket API or editing `.storage` before boot.
`tests/test_no_ha_imports.py` keeps it that way.
"""
