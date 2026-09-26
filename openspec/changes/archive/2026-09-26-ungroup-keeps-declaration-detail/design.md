# Design

## Which zero-amount lines are OpenUpgrade's

OpenUpgrade 13.0 adds `aml_matched` to `account_invoice_line` and sets it on each invoice line it matched to
an existing journal item. It inserts the others as new items at zero. The flag survives the chain in the
legacy table. On the first client it split the zero-amount lines exactly: every line that existed in the
source had a matched invoice line, and every inserted line did not.

- **Not "has no references".** Inserted lines are referenced by their own business links (sale lines, stock
  moves, OCA's stored analytic accounts), so that rule would leave nearly every group.
- **Not "id above the source's highest".** That needs a table kept from the source, which a chain resumed
  from an older checkpoint does not have. The flag is in every database OpenUpgrade 13.0 migrated.

Without the column, no line is excluded, and the new check stops a repair that would change a box's detail.

## The detail check

For each link table, the records that pointed at a repaired grouped item are taken before the repair. The
sum of the balances of all journal items linked to each record is compared before and after. Only those
records are compared: an inserted line's own business links (a sale line's invoice lines) rightly add up to
more once the line carries its amount.
