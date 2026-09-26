# Design

## Why not protect the maps before each step

Marking the maps the boxes use as `noupdate` would stop Odoo from deleting them, since `_process_end` only
deletes records whose `noupdate` is false. But the current maps are used by filed boxes too, and
`noupdate` would also stop every later update of them. OCA's 17.0 module rewrites how each map line names
its taxes, so a current map frozen before 17.0 would lose its taxes, and every later return would compute
zero. Which maps a later version drops is only known from its data files, at run time.

## Why at the source restore and at the target

- The source restore is the one point every fresh run passes through. Its checkpoint then carries the
  copies through the chain; no step reads or changes tables it does not know.
- The target is the one point where everything any step deleted is known. Putting back there covers every
  step, including one a future module version adds.
- Before the grouped-items repair, because that repair moves the links of the items it deletes, and it
  must move the put-back boxes' links too. Its detail check then covers them.

## Putting back

Parents first, maps, then map lines, then boxes, each only where its id is missing. The ids are the
source's: a sequence never goes back, so no later record holds them. Columns are those both sides have,
cast to the target's type. A put-back map has no identifier, so no module update deletes it again.
