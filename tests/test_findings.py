"""The findings ledger: what it accepts, what the operations keep, what the reports show."""

from __future__ import annotations

import copy
import json
from datetime import date

import pytest

from odoo_dwg import findings as fl
from odoo_dwg import i18n
from odoo_dwg.models import MigrationEnv

TODAY = date(2026, 9, 23)


@pytest.fixture(autouse=True)
def _reset_language():
    yield
    i18n.set_language("en")


def _finding(fid: str = "sii-pending", **over) -> dict:
    raw = {
        "id": fid, "found": "2026-09-23", "phase": "outbound-inventory", "severity": "critical",
        "category": "outbound", "audience": "client", "subject": "l10n_es_aeat_sii",
        "summary": "SII enabled in production mode; 1687 invoices pending.",
        "evidence": {"not_sent": 1685, "sent_modified": 2},
        "query": "select sii_state, count(*) from account_invoice group by 1",
        "action": "neutralise on every working copy",
        "decision": {"state": "pending", "date": "2026-09-23", "note": ""},
        "client": {
            "es": {"title": "SII activo en modo real", "text": "Hay 1.687 facturas pendientes.",
                   "question": "¿Deben enviarse desde producción?"},
            "en": {"title": "SII live", "text": "1,687 invoices are pending.",
                   "question": "Should they be sent from production?"},
        },
        "tables": [{"file": "sii.tsv", "audience": "client",
                    "columns": {"es": ["Estado", "Facturas"]}}],
    }
    raw.update(over)
    return raw


def _raw(**over) -> dict:
    raw = {
        "schema": 1, "client_name": "ACME, SL", "database": "ACME", "source_version": "12.0",
        "target_version": "18.0", "reference_database": "ACME_original", "note": "",
        "context": {
            "received": [{"item": {"en": "Database", "es": "Base de datos"},
                          "detail": "pg_dump custom", "date": "2026-09-21"}],
            "versions": [{"what": {"en": "Target", "es": "Destino"}, "value": "18.0",
                          "link": "https://github.com/odoo/odoo/tree/18.0"}],
            "sources": [{"origin": "Custom (private)", "link": ""}],
            "references": [], "data_handling": [{"en": "We work on a copy.",
                                                 "es": "Trabajamos sobre una copia."}],
        },
        "phases": [{"id": "intake", "title": {"en": "Intake", "es": "Recepción"},
                    "state": "done"}],
        "findings": [
            _finding(),
            _finding("core-is-ocb", severity="info", audience="internal", client={}, tables=[],
                     summary="The core is OCB."),
        ],
        "corrections": [],
    }
    raw.update(over)
    return raw


def _ledger(**over) -> fl.Ledger:
    return fl.parse_ledger(json.dumps(_raw(**over)))


TABLES = {"sii.tsv": [["state", "count"], ["not_sent", "1685"], ["sent_modified", "2"]]}


def _problems(raw: dict) -> list[str]:
    with pytest.raises(fl.LedgerError) as caught:
        fl.parse_ledger(json.dumps(raw))
    return caught.value.problems


# --- the ledger ------------------------------------------------------------------

def test_a_ledger_round_trips_byte_for_byte():
    text = fl.dump_ledger(_ledger())
    assert fl.dump_ledger(fl.parse_ledger(text)) == text
    assert text.endswith("}\n") and "Recepción" in text  # UTF-8 kept, not escaped


def test_a_ledger_from_a_later_tool_is_refused():
    problems = _problems(_raw(schema=2))
    assert len(problems) == 1 and "2" in problems[0] and "1" in problems[0]


@pytest.mark.parametrize("field, value, expected", [
    ("id", "Bad_Id", "kebab-case"),
    ("severity", "urgent", "severity"),
    ("audience", "everyone", "audience"),
    ("found", "23/09/2026", "found"),
    ("evidence", {}, "evidence: required"),
    ("query", "", "query: required"),
    ("decision", {"state": "maybe", "date": "2026-09-23"}, "decision.state"),
])
def test_a_finding_missing_what_it_rests_on_is_refused(field, value, expected):
    raw = _raw()
    raw["findings"][0][field] = value
    assert any(expected in p for p in _problems(raw))


def test_every_problem_is_reported_not_only_the_first():
    raw = _raw()
    raw["findings"][0]["query"] = ""
    raw["findings"][0]["severity"] = "urgent"
    raw["phases"][0]["state"] = "finished"
    problems = _problems(raw)
    assert len(problems) == 3


def test_a_duplicate_id_is_refused():
    raw = _raw()
    raw["findings"].append(copy.deepcopy(raw["findings"][0]))
    assert any("duplicate id" in p for p in _problems(raw))


def test_a_table_outside_the_data_directory_is_refused():
    raw = _raw()
    raw["findings"][0]["tables"][0]["file"] = "../../etc/passwd.tsv"
    assert any("tables[0].file" in p for p in _problems(raw))


def test_a_new_ledger_is_valid_and_says_only_what_is_true():
    ledger = fl.new_ledger("ACME", "ACME", "12.0", "18.0", "ACME_original")
    assert fl.parse_ledger(fl.dump_ledger(ledger)) == ledger
    assert [p.state for p in ledger.phases] == ["pending"] * len(ledger.phases)
    # No promise that copies send nothing: that is true only once they are neutralised.
    assert "send" not in json.dumps(ledger.context["data_handling"])


def test_environment_paths():
    env = MigrationEnv(source="12.0", target="18.0")
    assert env.findings_ledger == env.root / "findings" / "findings.json"
    assert env.findings_data_dir == env.root / "findings" / "data"


# --- operations ------------------------------------------------------------------

def test_the_client_changes_their_mind():
    ledger = fl.decide(_ledger(), "sii-pending", "act", "2026-09-24", "client: clean it")
    ledger = fl.decide(ledger, "sii-pending", "declined", "2026-09-30", "client: keep them")
    finding = ledger.findings[0]
    assert finding.decision == fl.Decision("declined", "2026-09-30", "client: keep them")
    assert [d.state for d in finding.history] == ["pending", "act"]
    assert finding.history[1].note == "client: clean it"


def test_a_finding_that_proves_false_is_corrected_not_deleted():
    ledger = fl.withdraw(_ledger(), "core-is-ocb", "2026-09-23", "the scan missed OCB history")
    assert [f.id for f in ledger.findings] == ["sii-pending"]
    correction = ledger.corrections[0]
    assert (correction.withdrawn, correction.reason) == ("core-is-ocb", "the scan missed OCB history")
    assert correction.finding is not None and correction.finding.summary == "The core is OCB."
    # The id stays taken.
    again = fl.parse_findings(json.dumps([_finding("core-is-ocb")]))
    with pytest.raises(fl.LedgerError, match="withdrawn"):
        fl.add_findings(ledger, again)


def test_a_withdrawal_needs_its_reason():
    with pytest.raises(fl.LedgerError, match="reason"):
        fl.withdraw(_ledger(), "core-is-ocb", "2026-09-23", "  ")


def test_adding_a_duplicate_leaves_the_ledger_unchanged():
    ledger = _ledger()
    with pytest.raises(fl.LedgerError, match="duplicate"):
        fl.add_findings(ledger, fl.parse_findings(json.dumps([_finding()])))
    assert len(ledger.findings) == 2


def test_adding_findings_from_a_file():
    new = fl.parse_findings(json.dumps({"findings": [_finding("mail-broken")]}))
    ledger = fl.add_findings(_ledger(), new)
    assert [f.id for f in ledger.findings] == ["sii-pending", "core-is-ocb", "mail-broken"]


def test_setting_a_phase_and_an_unknown_one():
    assert fl.set_phase(_ledger(), "intake", "in-progress").phases[0].state == "in-progress"
    with pytest.raises(fl.LedgerError):
        fl.set_phase(_ledger(), "nope", "done")
    with pytest.raises(fl.LedgerError):
        fl.set_phase(_ledger(), "intake", "finished")


def test_pending_and_urls():
    ledger = _ledger()
    assert [f.id for f in fl.pending(ledger)] == ["sii-pending", "core-is-ocb"]
    urls = fl.ledger_urls(ledger)
    assert urls == [("context.versions[0].link", "https://github.com/odoo/odoo/tree/18.0")]


# --- rendering -------------------------------------------------------------------

def test_the_client_report_keeps_internal_matter_out():
    report = fl.render_client_report(_ledger(), TABLES, "es", TODAY)
    assert "SII activo en modo real" in report
    assert "¿Deben enviarse desde producción?" in report  # pending -> asked
    assert "| Estado | Facturas |" in report and "| not_sent | 1685 |" in report
    assert "core-is-ocb" not in report and "The core is OCB." not in report  # internal
    assert "select sii_state" not in report  # no queries for the client
    assert "23/09/2026" in report and "Trabajamos sobre una copia." in report
    assert "repositorio privado" in report


def test_a_decided_finding_is_no_longer_asked():
    ledger = fl.decide(_ledger(), "sii-pending", "act", "2026-09-24")
    report = fl.render_client_report(ledger, TABLES, "en", TODAY)
    assert "Should they be sent" not in report
    assert "SII live" in report


def test_a_finding_not_yet_written_for_the_client_stops_the_report():
    raw = _raw()
    del raw["findings"][0]["client"]["es"]
    with pytest.raises(fl.LedgerError) as caught:
        fl.render_client_report(fl.parse_ledger(json.dumps(raw)), TABLES, "es", TODAY)
    assert caught.value.problems == ["finding sii-pending: no es client text"]


def test_a_missing_table_stops_the_report_and_is_named():
    with pytest.raises(fl.LedgerError, match="findings/data/sii.tsv"):
        fl.render_client_report(_ledger(), {}, "en", TODAY)


def test_the_extended_report_shows_everything_and_how_to_check_it():
    ledger = fl.decide(_ledger(), "sii-pending", "act", "2026-09-24", "client: clean")
    ledger = fl.withdraw(ledger, "core-is-ocb", "2026-09-25", "was official Odoo after all")
    report = fl.render_extended_report(ledger, TABLES, "en", TODAY)
    assert "select sii_state, count(*) from account_invoice group by 1" in report
    assert '"not_sent": 1685' in report
    assert "Act on it (2026-09-24) — client: clean" in report
    assert "Pending (2026-09-23)" in report  # the earlier decision, kept
    assert "was official Odoo after all" in report  # the correction
    assert "## core-is-ocb" not in report  # withdrawn: not among the findings


def test_same_input_same_bytes_whoever_renders_it():
    ledger = _ledger()
    i18n.set_language("en")
    from_english = fl.render_client_report(ledger, TABLES, "es", TODAY)
    again = fl.render_client_report(ledger, TABLES, "es", TODAY)
    i18n.set_language("es")
    from_spanish = fl.render_client_report(ledger, TABLES, "es", TODAY)
    assert from_english == again == from_spanish
    assert "Lo que hemos encontrado" in from_english


def test_a_report_language_the_tool_does_not_speak():
    with pytest.raises(fl.LedgerError, match="fr"):
        fl.render_client_report(_ledger(), TABLES, "fr", TODAY)


def test_a_pipe_in_a_cell_does_not_break_the_table():
    tables = {"sii.tsv": [["state", "count"], ["a|b", "1"]]}
    assert "| a\\|b | 1 |" in fl.render_client_report(_ledger(), tables, "en", TODAY)


def test_a_table_note_phase_marks_and_link_labels():
    raw = _raw()
    raw["findings"][0]["tables"][0]["note"] = {"es": "✅ existe · ❌ no encontrado", "en": "legend"}
    report = fl.render_client_report(fl.parse_ledger(json.dumps(raw)), TABLES, "es", TODAY)
    assert "| not_sent | 1685 |\n| sent_modified | 2 |\n\n✅ existe · ❌ no encontrado\n" in report
    assert "| Recepción | ✅ Hecho |" in report
    assert "informe a fecha 23/09/2026" in report
    assert "[github.com/odoo/odoo/tree/18.0](https://github.com/odoo/odoo/tree/18.0)" not in report
    raw["context"]["references"] = [{"what": "OpenUpgrade", "link": "https://oca.github.io/OpenUpgrade/"}]
    report = fl.render_client_report(fl.parse_ledger(json.dumps(raw)), TABLES, "en", TODAY)
    assert "| OpenUpgrade | [oca.github.io/OpenUpgrade](https://oca.github.io/OpenUpgrade/) |" in report


def test_the_link_check_never_reaches_a_url_that_is_evidence():
    raw = _raw()
    raw["findings"][0]["evidence"] = {"web.base.url": "http://client-production.example:81"}
    raw["findings"][0]["summary"] = "Frozen to http://client-production.example:81"
    raw["findings"][0]["query"] = "curl http://client-production.example:81"
    raw["findings"][0]["client"]["es"]["text"] = "Ver https://sede.agenciatributaria.gob.es/x."
    raw["findings"][0]["tables"][0]["note"] = "Fuente: https://github.com/OCA/l10n-spain"
    urls = [url for _where, url in fl.ledger_urls(fl.parse_ledger(json.dumps(raw)))]
    assert "http://client-production.example:81" not in urls
    assert urls == ["https://github.com/odoo/odoo/tree/18.0",
                    "https://sede.agenciatributaria.gob.es/x",
                    "https://github.com/OCA/l10n-spain"]
