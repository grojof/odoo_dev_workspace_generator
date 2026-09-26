# Design

## Successors

`RENAMES` is keyed by the target's model and the field it lacks. Each entry cites where the chain moved
that field's data: an OpenUpgrade or OCA migration script, or both versions' field definitions. A
successor is used only when every field it names exists in the target, and never when the old name
still exists there.

| Kind | Path, grouping, sort | Domain leaf |
|---|---|---|
| rename | the new name; a non-relational successor ends the path | the new name; a value map translates the value (an account type) |
| drop | an export column is dropped | the filter is left |
| either | cannot be named: left | `|` of both fields (`&` for a negative operator) |
| rank | the rank field | `= True` becomes `> 0`, `= False` becomes `= 0` |
| invoice line | the entry (`move_id`), in groupings and sorts only | `!= False` becomes `move_id.move_type in` the four invoice types |

## Running it

The file is stdlib only and the driver embeds it verbatim into the target's `odoo-bin shell`, like
`carry.py`, followed by `APPLY`. `APPLY`:
- reads the fields and their relations from `ir_model_fields`;
- rewrites with plain SQL updates;
- writes a filter's sort as a JSON array, which Odoo checks (`ir_filters_check_sort_json`).

A domain is parsed with `ast` and written back with `ast.unparse`, only when something changed.

## What it does not see

A field with the same name and another meaning is not rewritten. For example, an invoice's `name`
(its description in 12, its number from 13) or its `state` (paid in 12, posted in 18). Telling them
apart needs the source's model per saved record, kept at the source restore. That is left for a later
change, which could also harvest renames from OpenUpgrade's scripts and analysis files.
