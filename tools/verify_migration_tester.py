#!/usr/bin/env python3
"""Generate the rehearsal tester and check that it is a module, and that its
question is a query PostgreSQL answers.

The unit suite asserts the chooser and the verdicts on fixtures. What it cannot
say is whether the *files* are a module — a manifest that does not evaluate, an
XML that does not parse, a Python file that does not compile — or whether
`probe_state_sql` is valid SQL. Both are text this project generates for
something else to execute, which is what the project verifies by executing.

    python tools/verify_migration_tester.py

The analysis input is real: lines copied verbatim from OpenUpgrade's own
`upgrade_analysis.txt` files. Where the host has the environment's clones, it is
run against those too, so the generator meets the whole vocabulary and not only
the sample. Needs a PostgreSQL server binary; no network, no root, nothing
written outside a temporary directory.
"""

from __future__ import annotations

import ast
import compileall
import csv
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from verify_mail_capture import Cluster, _bindir  # noqa: E402

from odoo_dwg import analysis, templates, tester  # noqa: E402

CLONES = Path.home() / "odoo-migrations" / ".repos"

# Verbatim from OpenUpgrade's own analysis files: one line per class, so the
# generator is exercised against every class it claims to cover.
REAL_LINES = """---Models in module 'base'---
obsolete model base.update.translations [transient]
obsolete model sale.payment.acquirer.onboarding.wizard (renamed to sale.payment.provider.onboarding.wizard) [transient]
---Fields in module 'sale'---
sale         / sale.order.line          / qty_delivered_manual (float)  : DEL
sale         / sale.order               / show_update_pricelist (boolean): not stored anymore
sale         / sale.order.line          / product_template_id (many2one): not related anymore
sale         / sale.order.line          / qty_delivered (float)         : not a function anymore
sale         / account.move             / partner_shipping_id (many2one): module is now 'account' ('sale')
sale         / sale.order.line          / product_type (selection)      : previously in module sale_stock
sale         / sale.order.line          / price_unit (float)            : now a function
sale         / sale.order               / amount_total (monetary)       : is now stored
sale         / sale.order               / note (text)                   : now related
l10n_be_invoice_bba / account.journal   / invoice_reference_model (False): selection_keys is now '['be', 'euro', 'odoo']' ('['be', 'c'])
sale_project / product.template         / project_template_id (many2one): needs conversion to v18-style company dependent
"""


class _Fate:
    """A `preflight.ModuleFate` in the shape the bridge reads, verbatim from
    OpenUpgrade 14.0's own apriori.py."""

    def __init__(self, module: str, kind: str, successor: str) -> None:
        self.module, self.kind, self.successor = module, kind, successor


FATES = [
    _Fate("account_consolidation", "renamed", "account_consolidation_oca"),
    _Fate("website_sale_product_style_badge", "merged", "website_sale"),
    _Fate("partner_firstname", "carries on", "partner_firstname"),
]


def _by_version_from_clones() -> dict[str, list]:
    """The real chain, where this host has it."""
    found: dict[str, list] = {}
    for clone in sorted(CLONES.glob("openupgrade-*")):
        version = clone.name.split("-", 1)[1]
        records: list = []
        for path in clone.rglob("upgrade_analysis.txt"):
            records += analysis.harvest_changes(path.read_text(errors="replace"))
        if records:
            found[version] = records
    return found


def _write(files: dict[str, str], root: Path) -> None:
    for name, content in files.items():
        target = root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")


def main() -> int:
    failures: list[str] = []

    def check(label: str, condition: bool, detail: str = "") -> None:
        print(f"{'ok  ' if condition else 'FAIL'}  {label}")
        if not condition:
            failures.append(f"{label}: {detail}")

    # Both sources, as the generator uses them: analysis files for models and
    # fields, apriori.py for modules.
    sample = {"16.0": analysis.harvest_changes(REAL_LINES) + tester.module_fate_changes(FATES)}
    check(
        "every class this tool claims is harvested from the sample",
        {record.kind for record in sample["16.0"]} == set(analysis.CHANGE_CLASSES),
        str(sorted(set(analysis.CHANGE_CLASSES) - {r.kind for r in sample["16.0"]})),
    )

    # Substring patterns: the hazard is one pattern eating another's lines, and
    # the order of the table then deciding the answer invisibly.
    overlapping = {}
    for text in [REAL_LINES] + [
        path.read_text(errors="replace")
        for clone in sorted(CLONES.glob("openupgrade-*"))
        for path in clone.rglob("upgrade_analysis.txt")
    ]:
        for line in text.splitlines():
            row = analysis._FIELD_ROW_RE.match(line.strip())
            if not row:
                continue
            status = row.group("status")
            matched = [n for token, n in analysis._FIELD_STATUS_CLASSES if token in status]
            if len(matched) > 1:
                overlapping[tuple(matched)] = status
    check(
        "no status in the whole vocabulary is claimed by two patterns",
        not overlapping,
        str(overlapping),
    )

    probes, uncovered = tester.choose_probes(sample)
    check("the sample covers every class", uncovered == [], str(uncovered))
    files = templates.render_tester_module(probes, uncovered, "12.0 - 19.0")

    with tempfile.TemporaryDirectory(prefix="odwg-tester-") as tmp:
        root = Path(tmp) / tester.TESTER_MODULE
        _write(files, root)

        check(
            "every Python file compiles",
            compileall.compile_dir(str(root), quiet=2, force=True),
            "a generated .py does not compile",
        )
        manifest = ast.literal_eval((root / "__manifest__.py").read_text().split("\n", 1)[1])
        check(
            "the manifest is a dict Odoo would accept",
            isinstance(manifest, dict)
            and manifest["depends"] == ["base"]
            and manifest["installable"] is True
            and "auto_install" not in manifest,
            str(manifest)[:200],
        )
        check(
            "and it declares every file it ships",
            set(manifest["data"]) == {"security/ir.model.access.csv", "data/probes.xml"}
            and all((root / name).exists() for name in manifest["data"]),
            str(manifest["data"]),
        )
        tree = ET.parse(root / "data" / "probes.xml")
        records = tree.getroot().findall("./data/record")
        check(
            "the data file parses and holds one record per probe",
            len(records) == len(probes),
            f"{len(records)} records for {len(probes)} probes",
        )
        ids = [record.get("id") for record in records]
        check("record ids are unique", len(set(ids)) == len(ids), str(ids))
        check(
            "no record carries a tab into a tab-separated read",
            not any("\t" in (field.text or "") for record in records for field in record),
            "a source line kept its tab",
        )
        with (root / "security" / "ir.model.access.csv").open() as handle:
            rows = list(csv.DictReader(handle))
        check(
            "the access rule is read-only and on this module's model alone",
            len(rows) == 1
            and rows[0]["model_id:id"] == f"model_{tester.PROBE_TABLE}"
            and (rows[0]["perm_write"], rows[0]["perm_create"], rows[0]["perm_unlink"])
            == ("0", "0", "0"),
            str(rows),
        )

    # The question, asked of a real server.
    bindir = _bindir()
    if bindir is None:
        print("No PostgreSQL server binaries found under /usr/lib/postgresql.")
        return 1
    with tempfile.TemporaryDirectory(prefix="odwg-tester-pg-") as tmp:
        cluster = Cluster(Path(tmp), bindir)
        cluster.start()
        try:
            cluster.sql("CREATE DATABASE probe")
            cluster.sql(
                "CREATE TABLE ir_model (id serial PRIMARY KEY, model varchar);"
                "CREATE TABLE ir_model_fields (id serial PRIMARY KEY, model varchar, name varchar);"
                "CREATE TABLE ir_module_module (id serial PRIMARY KEY, name varchar, "
                "state varchar);"
                f"CREATE TABLE {tester.PROBE_TABLE} (id serial PRIMARY KEY, name varchar, "
                "kind varchar, step varchar, subject_model varchar, subject_field varchar, "
                "successor varchar, expected_gone boolean, source_line text);",
                "probe",
            )
            # The database keeps the model of a probe that predicted its removal,
            # and loses the field of one that predicted nothing: one of each finding.
            kept = next(p for p in probes if p.expected_gone and p.subject_kind == "model")
            quiet = next(p for p in probes if not p.expected_gone and p.subject_kind == "field")
            # A module the chain absorbed, still installed: the same finding one
            # table over, and the one this whole demo rehearsal is aimed at.
            kept_module = next(p for p in probes if p.subject_kind == "module")
            for probe in probes:
                if probe.subject_kind == "module":
                    if probe is kept_module:
                        cluster.sql(
                            "INSERT INTO ir_module_module (name, state) VALUES "
                            f"('{probe.model}', 'installed')", "probe")
                elif probe.subject_kind == "model":
                    if probe is kept:
                        cluster.sql(
                            f"INSERT INTO ir_model (model) VALUES ('{probe.model}')", "probe")
                elif probe is not quiet:
                    cluster.sql(
                        "INSERT INTO ir_model_fields (model, name) VALUES "
                        f"('{probe.model}', '{probe.field}')", "probe")
                cluster.sql(
                    f"INSERT INTO {tester.PROBE_TABLE} "
                    "(name, kind, step, subject_model, subject_field, successor, "
                    "expected_gone, source_line) "
                    f"VALUES ('{probe.name}', '{probe.kind}', '{probe.version}', "
                    f"'{probe.model}', '{probe.field}', '{probe.successor}', "
                    f"{probe.expected_gone}, $line${probe.detail}$line$)", "probe")

            read_back = cluster.sql(tester.probe_rows_sql(), "probe")
            check("the probe table reads back", read_back.returncode == 0, read_back.stderr.strip())
            stored = tester.probes_from_rows(
                [line.split("\t") for line in read_back.stdout.splitlines() if line.strip()]
            )
            check(
                "every probe the module declared comes back",
                {p.name for p in stored} == {p.name for p in probes},
                f"{len(stored)} of {len(probes)}",
            )
            asked = cluster.sql(tester.probe_state_sql(stored), "probe")
            check("the state query is SQL PostgreSQL runs", asked.returncode == 0,
                  asked.stderr.strip())
            verdicts = tester.read_probe_states(
                stored, [line.split("\t") for line in asked.stdout.splitlines() if line.strip()]
            )
            by_name = {verdict.probe.name: verdict.state for verdict in verdicts}
            check(
                "a subject still there where the sources said it would go is a finding",
                by_name.get(kept.name) == "still there", str(by_name.get(kept.name)))
            check(
                "a subject gone with nothing predicting it is a finding",
                by_name.get(quiet.name) == "gone unannounced", str(by_name.get(quiet.name)))
            check(
                "an absorbed module still installed is a finding too",
                by_name.get(kept_module.name) == "still there",
                str(by_name.get(kept_module.name)),
            )
            check(
                "and the findings are reported first",
                all(verdict.is_finding for verdict in verdicts[:3]),
                str([(v.probe.name, v.state) for v in verdicts[:4]]),
            )
            check(
                "a database without the module reports absent, not intact",
                {v.state for v in tester.read_probe_states(stored, [], installed=False)}
                == {"absent"},
                "an uninstalled tester was read as passing",
            )
        finally:
            cluster.stop()

    # The whole vocabulary, where the host has the clones.
    real = _by_version_from_clones()
    if real:
        probes, uncovered = tester.choose_probes(real)
        with tempfile.TemporaryDirectory(prefix="odwg-tester-real-") as tmp:
            root = Path(tmp) / tester.TESTER_MODULE
            _write(templates.render_tester_module(probes, uncovered, "real"), root)
            check(
                f"the real chain ({len(real)} steps, {len(probes)} probes) generates a module",
                compileall.compile_dir(str(root), quiet=2, force=True)
                and ET.parse(root / "data" / "probes.xml") is not None,
                "the real chain did not generate cleanly",
            )
        check(
            "every probe names a subject the sources stated",
            all(
                any(
                    record.model == probe.model and record.field == probe.field
                    and record.kind == probe.kind
                    for record in real[probe.version]
                )
                for probe in probes
            ),
            "a probe named a subject no analysis record carries",
        )
    else:
        print("note  no OpenUpgrade clones on this host; the real chain was not generated")

    if failures:
        print("\nFAILED:")
        for failure in failures:
            print(f"  {failure}")
        return 1
    print("\nThe rehearsal tester generates, parses and answers as documented.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
