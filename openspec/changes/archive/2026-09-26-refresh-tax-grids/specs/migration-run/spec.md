# Spec Delta

## ADDED Requirements

### Requirement: Tax grids are refreshed from the chart template after the target step

When the chain crosses 17.0, the target step SHALL, after the valuation alignment and before its checkpoint,
run the target's Odoo to:
- apply the chart template's reload restricted to taxes, setting the repartition lines' tags of every tax
  whose template is unchanged, and leaving any other tax;
- recompute the tax tags of every journal item of an invoice or credit note from repartition lines: a tax
  line from its repartition line, a base line from its taxes' base repartition lines for the document's
  type;
- archive the tax tags no repartition line or journal item uses and no tax report generates.

It SHALL keep nothing when any journal item's amounts, taxes or tag inversion would change. It SHALL list
every repartition line retagged, every tax left, every tag archived, and the number of journal items
regridded and of plain-entry items left, in `logs/<target>-tax-grids.tsv`.

#### Scenario: Unsigned tags from an older chart

- **WHEN** a tax's repartition lines and journal items still carry the unsigned tags of the source's chart
- **THEN** they get the signed tags of the 18 template, and the old tags nothing uses are archived

#### Scenario: A tax with no template

- **WHEN** a tax matches no unchanged template
- **THEN** its tags stay as they are and it is listed

#### Scenario: A second run

- **WHEN** the refresh runs on a database it already refreshed
- **THEN** it retags nothing
