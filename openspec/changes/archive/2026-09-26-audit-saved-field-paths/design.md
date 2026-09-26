# Design

## One query

Fields, filters and export columns come in one query, as one JSON array per row. A user can save a tab or
a newline in a domain; as JSON it never splits a row. A filter's `sort` is read through `to_jsonb`, so a
database without that column still answers.

## Reading a domain

`ast.parse`, never `literal_eval` or `safe_eval`. A saved domain may compute a date with
`context_today()`, and only the field names matter here. A leaf is a three-element list or tuple whose
first element is a string and whose second is a domain operator. Its value is not looked into, because
`("state", "in", ["a", "in", "b"])` holds a list that reads like a leaf. An expression that does not parse
is itself reported.

## Reading a path

Segment by segment, through each field's relation:
- domains use `.`, exports `/`;
- a grouping's `:month` and a sort's `-` are dropped;
- `id`, an export's `.id` and measures such as `__count` end the check.

A path breaks at the first segment its model lacks, or at a model the database no longer has. A filter or
export on a model that is gone is broken whatever it names.

## What counts as present

`ir_model_fields` rows. A module still installed without code keeps its fields there until the
client-modules stage uninstalls it, so on a database before that stage its fields count as present. The
check says so in its fix.
