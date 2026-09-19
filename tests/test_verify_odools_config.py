"""The pure parts of tools/verify_odools_config.py, without the network.

OdooLS has already changed the shape of its published schema once: 1.4.0 keeps
the profile definition behind a ``$ref`` into ``$defs``, 1.5.2 inlines it. The
check has to read both, or it breaks the day a new shape reaches the stable
channel — which is exactly when it is needed.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

TOOL = Path(__file__).resolve().parent.parent / "tools" / "verify_odools_config.py"
spec = importlib.util.spec_from_file_location("verify_odools_config", TOOL)
verify = importlib.util.module_from_spec(spec)
spec.loader.exec_module(verify)

PROFILE = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "name": {"type": "string"},
        "odoo_path": {"type": ["string", "null"]},
        "addons_paths": {"type": ["array", "null"], "items": {"type": "string"}},
        "python_path": {"type": ["string", "null"]},
        "file_cache": {"type": "boolean"},
    },
}
SCHEMA_WITH_REF = {  # the 1.4.0 shape
    "properties": {"config": {"type": "array", "items": {"$ref": "#/$defs/ConfigEntryRaw"}}},
    "$defs": {"ConfigEntryRaw": PROFILE},
}
SCHEMA_INLINE = {  # the 1.5.2 shape
    "properties": {"config": {"type": "array", "items": PROFILE}},
}


def test_both_published_schema_shapes_are_read():
    for schema in (SCHEMA_WITH_REF, SCHEMA_INLINE):
        properties, additional = verify.entry_properties(schema)
        assert set(verify.ODOOLS_KEYS) <= set(properties)
        assert additional is False


def test_accepted_types_handle_single_list_and_union_forms():
    assert verify.accepted_types({"type": "string"}) == {"string"}
    assert verify.accepted_types({"type": ["string", "null"]}) == {"string", "null"}
    assert verify.accepted_types({"anyOf": [{"type": "string"}, {"type": "null"}]}) == {
        "string",
        "null",
    }


def test_every_emitted_key_has_a_type_to_check():
    # A key added to the renderer without a type here would be checked for
    # presence only, silently.
    assert set(verify.EMITTED_TYPES) == set(verify.ODOOLS_KEYS)


def test_versions_compare_numerically():
    assert verify.version_tuple("1.10.0") > verify.version_tuple("1.9.2")
    assert verify.version_tuple("[1.5.2] - 2026/07/30 - Fixes") == (1, 5, 2)
