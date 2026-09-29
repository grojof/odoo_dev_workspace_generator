# Design

## Decisions

- **Lock dates, not fiscal years.** The company's lock dates are what the accountant closed: the fiscal
  year lock (nothing posts on or before it) and the tax lock (its taxes are declared). The later of the two
  is the edge; both columns exist from 14.0, so the condition is valid on every target the repairs run on.
- **An open invoice is repaired wherever it is dated.** OpenUpgrade's own advice for grouped items is to
  fix the invoices still to be paid by hand (cancel, draft, remove the grouped item, post): whoever
  registers a payment or a credit note on it needs its lines. The repair does the same, checked.
- **Tags follow `account_chart_update`.** It retags taxes and their repartition lines, which new documents
  use; past journal items keep the tags they were declared with.
- **No option.** The earlier behaviour changed closed periods without the client's accountant; the
  default now follows OCA. An option for the other way is added when someone needs it, with that approval.
