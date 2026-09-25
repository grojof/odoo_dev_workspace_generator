# Design

## The lock date

A line is in a closed period when its date is on or before the later of its company's
`fiscalyear_lock_date` and `period_lock_date`. The period lock is what a client moves at each filing,
and the fiscal-year lock is the hard one. A company with neither has no closed period, and nothing is
listed.

## What is kept

An unreconciled line that matches an open receivable or payable item of the same partner, by exact
amount, is kept. It may be money that arrived and was never registered. Only the accountant can tell, in the
new version, where the line will then have its entry. The match is deliberately loose: keeping a line
costs one entry to review, while dropping a real payment loses evidence.

## Optional by construction

The step writes the file, and the operator decides whether it goes in the hook. The finding says whose
decision it is. The duplicates' SQL and this one are separate files, because the first is a correction
and the second a choice.
