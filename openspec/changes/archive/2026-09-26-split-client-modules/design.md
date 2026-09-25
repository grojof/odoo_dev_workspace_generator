# Design

`plan()` already knows two things:
- a rename: an old module's record becomes `to[0]`, which the stage updates;
- an install: modules named by `replaced` join one `-i` list.

A split is both. It is `to[0]` for the rename, and `to[1:]` added to the installs. The installs pass the
same checks, and appear in the same "not installed after the update" guard before anything is
uninstalled.

The first module is the one that owns the old module's data. That choice is made in the decision, not
derived: only the ported code knows where a table's model lives. The order of `to` is therefore
meaningful, and `migrate decide` keeps it as given.

Records the old module owned that belong to a split part are the first module's to hand over (for
example by moving `ir_model_data` rows to the part's name before its update), or the part rebuilds them.
A module installed new runs no `migrations/` script, so it cannot clean up after the old module itself.
