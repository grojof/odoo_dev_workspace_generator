# Design

**Ownership is the first `ir_model_data` row.** A model or field that several modules extend is attributed
to the module that created it, as the uninstall rehearsal does. That module is the one whose removal would
take it away.

**"Since" is read from `write_date` of the rows holding a value.** It is a lower bound: a row written since
the date for another reason also counts. For a decision between "keep" and "drop", a lower bound on
disuse errs the safe way.

**A wizard's use is its sequence.** Transient rows are vacuumed; the sequence is not. That gives times
opened, but not when. Wizards therefore count toward "in use" only through the total, and the table says so.

**Prints come from an access log, when there is one.** The step parses both the werkzeug line and the
combined log format with one pattern on the request path. The date is read from either format; a line
without a readable date is counted as undated and reported apart.

**The label is deliberately coarse.** What a module does, and whether Odoo 18 covers it, is read from its
code. That is the operator's part, and the step leaves it to them.
