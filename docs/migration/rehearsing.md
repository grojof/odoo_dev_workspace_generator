---
type: how-to
title: "Rehearsing a migration"
description: "Rehearse on Odoo's demo data before there is a client dump, and against a tester module built to break."
tags: [migration, rehearsal, demo-data, tester]
audience: [developer]
updated: 2026-09-25
---

# Rehearsing a migration

Two aids for rehearsals: a source database seeded from Odoo's demo data, for before there is a client
dump, and a tester module that asks each step what it took away. Both run through the same driver
([running](running.md)).

## Rehearsing before there is a client dump

The driver needs a source dump, and before a client's database exists nobody has one. **Menu → Migration →
Seed a demo source database** builds one from Odoo's own demo data.

It prepares the **source** version, which the chain itself never builds — `chain()` is 13.0 … 19.0 for a
12 → 19 migration, so the environment has no Odoo 12 clone, venv or config at all. It needs none to
migrate; it needs one to *make* a dump. What it builds is plain Odoo, not OpenUpgrade: there is no
OpenUpgrade 12.0 branch, and the 12 → 13 step runs OpenUpgrade 13.

Before asking what to install, it shows what this chain does to the modules already linked under the
source version's `addons/odoo12/oca` and `custom`:

```
[INFO] Modules found under the source version, with what this chain does to them:
  website_sale_product_style_badge             absorbed into website_sale (14.0)
  account_consolidation                        renamed to account_consolidation_oca (14.0)
  partner_firstname                            carries on under its own name
```

That is the set worth rehearsing with — **one absorbed, one renamed, one that carries on** — because those
are three different things for the chain to get right, and they are read from each step's own `apriori.py`,
not chosen by this tool's opinion. Only modules actually on disk at the source version are offered: one
that is not there cannot be installed there, and a rehearsal that fails for that reason reads exactly like
the chain failing.

Applying the plan writes `seed_demo.sh`. Run it yourself, like the driver:

```bash
cd ~/odoo-migrations/12-to-19
./seed_demo.sh                      # builds seed_12_to_19 with demo data, dumps it
./run_migration.sh source-12.0-demo.dump
```

It installs **one module per call**, so a failure names which module rather than saying that something did
not install, and it stops there instead of dumping a database missing the module the rehearsal was for. It
refuses to overwrite an existing dump or reuse an existing database — a dump the checkpoints were taken
against is not replaceable silently.

Demo data is loaded because the flag is *not* passed: in Odoo 12.0 to 18.0 `--without-demo` defaults to
off, so a database created with `-i` gets demo data. (19.0 rewrote that option and flipped the default,
which cannot affect a seed — a chain's source is always ≤ 18.0.)

**Menu → Migration → Module fates in this chain** answers the same question for any module you name,
without seeding anything: renamed to X at a step, absorbed into Y at a step, or nothing declared, which
means it is expected to carry on. A step whose `apriori.py` cannot be read is named as unread rather than
counted as declaring nothing.

## Rehearsing against a module built to break

A chain rehearsed only against the client's own add-ons exercises the classes of change *that client*
happens to meet. **Menu → Migration → Generate the migration tester** writes an add-on of the tool's own
into every step's `addons/odoo<major>/custom`, with one probe per class of change the chain actually
contains — taken from that chain's own `upgrade_analysis.txt` files and `apriori.py`, never invented:

```
23 probes, from this chain's own sources.
  16.0  removed_model      base.update.translations
  16.0  unstored_field     sale.order/show_update_pricelist
  16.0  moved_field        account.move/partner_shipping_id
  ...
[WARN] Classes this chain never exercises: company_dependent
```

The classes with no instance are named rather than dropped: a class with no probe is not a class that
passed.

Each probe is a **declaration**, not synthesized model code — a record naming the subject, the class, the
step its analysis predicts it at, and that file's own line. (Generated model code referring to the subject
would fail on the *source* version when derived wrongly, destroying the rehearsal instead of measuring it.)

After a step, **Check the migration tester** asks the database what became of each subject, by reading its
`ir_model` and `ir_model_fields`. It needs no Odoo running, which is the point: the step worth asking about
is often the one where something failed to load.

```
[WARN] 2 probe(s) need looking at in acme_16.
  ! 16.0  gone unannounced   moved_field: account.move/partner_shipping_id
      sale / account.move / partner_shipping_id (many2one): module is now 'account' ('sale')
  ! 16.0  still there        removed_model: base.update.translations
      obsolete model base.update.translations [transient]
    16.0  intact             unstored_field: sale.order/show_update_pricelist
```

The two findings come first, and they are the two the run's logs never mention:

- **gone unannounced** — the subject is not there and nothing predicted it would go. This is the quiet
  loss: the module loaded, the step passed, and a column is empty.
- **still there** — the sources said it would go and it did not, so a migration script did not run.

The others are printed too, one line each, so you can see the question was asked:

- **`intact`** — the subject is still there and nothing said it would go.
- **`gone as predicted`** — it went, and what it became is there instead.
- **`not yet reached`** — the probe is about a step this database has not reached, so its subject being
  present says nothing yet. Expect many of these when checking between steps.
- **`past its step`** — the database is beyond the probe's step, so a missing subject cannot be blamed on
  it.
- **`not observed`** — neither the subject nor its successor is in the database, so this probe measured
  nothing: the subject was never installed here. It sorts **last**, after everything that was actually
  measured, and is not counted as a pass. A real run reported two module probes as `gone as predicted`
  about modules that had never been installed — absent proves nothing on its own.

If the module never installed, every probe reports `absent` rather than a reassuring `intact`.

**A module the chain installs along the way.** The preflight reads the source database once, so it cannot
see a module that does not exist yet: `partner_firstname_portal` appeared in an OCA repository at 18.0, was
auto-installed there because its dependencies were present, and had vanished from that repository by 19.0 —
installed, with no code, and nothing had asked. Each step therefore re-reads the live database and judges
what the preflight never saw, stopping at the step that found it rather than at the end.

**A probe can only report a loss if there was something to lose.** A field whose *model* is not in the
database, a module whose successor is not there either — neither was ever present, so the probe measured
nothing and says `not observed`. A real 12 → 19 run produced four alarms at one step about `stock.quant`
and `purchase.order` in a database where neither module was installed.

**Check after each step, not only at the end.** A probe claims something about *its own* step — *at 15.0
this field stops being computed, so it should survive that step*. A database carried on to 19.0 has had
four more steps at it, and a subject a later step removed is not a silent loss at 15.0. Checking a 12 → 19
chain only at the end produced six such false alarms, and six on seven steps teach you to stop reading the
report. Where the database is past a probe's step, a missing subject is reported as **`past its step`**
rather than as a finding — run the check between steps to judge those. An expected removal is still judged
from any later version, because "gone from its step onward" holds there too.

**What `not observed` cannot catch.** It fires when the subject *and* its successor are both missing. Where
the successor is a core module that would be installed anyway — `base_vat_sanitized` is absorbed into
`base_vat`, which any accounting database has — its presence says nothing about whether the subject was
ever there, and the probe still reads `gone as predicted`. Module probes are therefore only as meaningful
as the module set you seeded: probe what you installed.

The tester is a rehearsal instrument. Its manifest says so, it depends on `base` alone, and it declares no
menu, no group, no `auto_install` and read-only access to its own table.
