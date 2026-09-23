"""The neutralisation catalogue and its SQL, as text. Executing it is
tools/verify_neutralisation.py's job: the suite may not touch a database."""

from __future__ import annotations

import re

from odoo_dwg import neutralise as nz


def test_every_rule_says_where_it_comes_from():
    for rule in nz.CATALOGUE:
        assert rule.source.strip(), rule.id
        assert re.fullmatch(r"[a-z0-9-]+", rule.id), rule.id
    assert len({r.id for r in nz.CATALOGUE}) == len(nz.CATALOGUE)


def test_housekeeping_is_matched_by_xmlid_and_says_why_it_is_safe():
    for keep in nz.HOUSEKEEPING:
        module, name = keep.xmlid.split(".")
        assert module and name and keep.reason.strip()
    crons = next(r for r in nz.CATALOGUE if r.id == "crons")
    assert "ir_model_data" in crons.where and "cron_name" not in crons.where  # never by name


def test_a_rule_is_guarded_by_every_column_it_names():
    for rule in nz.CATALOGUE:
        text = " ".join([rule.where, *(e for _, e in rule.sets)])
        named = set(re.findall(r"\bt\.([a-z_0-9]+)", text))
        assert named <= set(rule.columns), (rule.id, named - set(rule.columns))


def test_apply_records_before_it_writes_and_is_guarded_per_rule():
    sql = nz.apply_sql("http://127.0.0.1:8070")
    assert sql.count("FROM pg_attribute a") == len(nz.CATALOGUE)
    assert "information_schema" not in sql and "information_schema" not in nz.columns_sql()
    for rule in nz.CATALOGUE:
        for column, _expr in rule.sets:
            record = sql.index(f"'{rule.id}', '{rule.table}', t.id")
            write = sql.index(f"UPDATE {rule.table} t SET {column} =", record)
            assert record < write, rule.id
    assert "ON CONFLICT DO NOTHING" in sql  # a record is never overwritten
    assert "'http://127.0.0.1:8070'" in sql and ":local_url" not in sql


def test_the_local_url_is_quoted_not_spliced():
    sql = nz.apply_sql("http://x'; DROP TABLE res_users; --")
    assert "'http://x''; DROP TABLE res_users; --'" in sql


def test_the_uuid_is_rolled_once_not_on_every_run():
    uuid = next(r for r in nz.CATALOGUE if r.id == "database-uuid")
    assert uuid.once
    block = nz._rule_block(uuid, nz.DEFAULT_LOCAL_URL)
    write = block.split("UPDATE ir_config_parameter t SET value =")[1].split(";")[0]
    # The write finds the record this run just made; a row recorded by an earlier
    # run (production's uuid, already replaced) is not rolled again.
    assert "n.run = r AND n.applied IS NULL" in write and "NOT EXISTS" not in write


def test_the_check_only_reads():
    existing = {(r.table, c) for r in nz.CATALOGUE for c in r.columns}
    sql = nz.check_sql(nz.applicable(existing))
    for word in ("INSERT", "UPDATE", "DELETE", "CREATE", "DROP", "ALTER", "TRUNCATE"):
        assert word not in sql.upper(), word
    assert "LIMIT" not in sql.upper()  # every armed row counted, a sample only shown


def test_only_applicable_rules_are_checked():
    existing = {("ir_cron", "id"), ("ir_cron", "active"), ("ir_cron", "cron_name")}
    assert [r.id for r in nz.applicable(existing)] == ["crons"]
    assert nz.check_sql([]).endswith("WHERE false")


def test_armed_rows_are_read_and_bad_rows_skipped():
    rows = [["crons", "7", "Mail queue, Digest"], ["iap", "x", ""], ["short"], ["", "1", ""]]
    assert nz.read_armed(rows) == [nz.Armed("crons", 7, "Mail queue, Digest")]


def test_restore_gives_back_the_first_run_and_names_the_rest():
    sql = nz.restore_sql()
    assert "RAISE EXCEPTION 'no neutralisation is recorded" in sql
    assert "rec.run > first_run" in sql and "left neutralised, not in production" in sql
    assert "jsonb_populate_record" in sql
    assert f"DROP TABLE {nz.RECORD_TABLE}, {nz.RULE_TABLE}, {nz.RUN_TABLE}" in sql


def test_later_rows_are_read():
    rows = [["crons", "ir_cron", "9", "", "active"], ["bad"]]
    assert nz.read_later_rows(rows) == [nz.LaterRow("crons", "ir_cron", "9", "", "active")]


# --- the surface -------------------------------------------------------------------

import pytest  # noqa: E402

from odoo_dwg import cli, egress, planners  # noqa: E402
from odoo_dwg.workflows import checks, common  # noqa: E402


def test_neutralise_captures_mail_first_and_restore_gives_it_back_last():
    plan = planners.plan_neutralise("acme_copy", "127.0.0.1", 5432, "odoo", "http://127.0.0.1:8069")
    assert egress.CAPTURE_RECORD_TABLE in plan[0].command
    assert nz.RUN_TABLE in plan[1].command
    back = planners.plan_restore_production("acme_copy", "127.0.0.1", 5432, "odoo")
    assert "no neutralisation is recorded" in back[0].command
    assert "no mail capture is recorded" in back[1].command
    assert all("-d acme_copy" in c.command and "ON_ERROR_STOP=1" in c.command
               for c in plan + back)


def test_nothing_in_the_codebase_restores_production_but_the_operator_action():
    from pathlib import Path
    # A restore that any flow reaches on its own — a driver step, the end of a
    # chain, a start script — would re-arm production on a development host.
    calls = re.compile(r"\b(plan_restore_production|neutralise\.restore_sql)\(")
    package = Path(common.__file__).resolve().parents[1]
    callers = sorted(str(p.relative_to(package)) for p in package.rglob("*.py")
                     if calls.search(p.read_text()))
    assert callers == ["planners.py", "workflows/common.py"]


def _state(*servers: tuple[str, bool]) -> egress.MailState:
    return egress.MailState(servers=tuple(
        egress.MailServer(str(i), "s", host, "25", active) for i, (host, active) in
        enumerate(servers)))


@pytest.mark.parametrize("armed, mail, expected", [
    ([], _state(), 0),                                          # no server: config fallback, a note
    ([], _state((egress.MAILPIT_SMTP_HOST, True)), 0),
    ([nz.Armed("crons", 3, "Mail queue")], _state(), 1),
    ([], _state(("smtp.client.example", True)), 1),
])
def test_the_check_exits_on_whether_anything_can_act(monkeypatch, capsys, armed, mail, expected):
    if mail.servers and mail.servers[0].host == egress.MAILPIT_SMTP_HOST:
        mail = egress.MailState(servers=(egress.MailServer(
            "1", "capture", egress.MAILPIT_SMTP_HOST, str(egress.MAILPIT_SMTP_PORT), True),))
    monkeypatch.setattr(checks, "armed_state", lambda *a: armed)
    monkeypatch.setattr(checks, "mail_state", lambda *a: mail)
    assert cli.main(["neutralise", "check", "--database", "acme_copy", "--lang", "en"]) == expected
    out = capsys.readouterr().out
    if not mail.servers:
        assert "configuration file's smtp_server" in out


def test_the_check_cannot_tell_is_not_clean(monkeypatch):
    monkeypatch.setattr(checks, "armed_state", lambda *a: None)
    monkeypatch.setattr(checks, "mail_state", lambda *a: _state())
    assert cli.main(["neutralise", "check", "--database", "acme_copy", "--lang", "en"]) == 2
    assert cli.main(["neutralise", "check", "--database", "bad;name", "--lang", "en"]) == 2


def test_restore_names_what_stays_off_and_needs_its_phrase(monkeypatch, capsys):
    monkeypatch.setattr(common, "ask_text", lambda *a, **k: "acme_copy")
    monkeypatch.setattr(common, "later_rows", lambda *a: [
        nz.LaterRow("crons", "ir_cron", "9", "sale.new_cron", "active")])
    phrases: list[str] = []
    monkeypatch.setattr(common, "confirm_with_phrase",
                        lambda label, phrase: (phrases.append(phrase), False)[1])
    planned: list = []
    monkeypatch.setattr(common, "apply_if_confirmed", lambda commands: planned.append(commands))
    common.restore_production("127.0.0.1", 5432, "odoo")
    out = capsys.readouterr().out
    assert "ir_cron #9 sale.new_cron" in out and "stay neutralised" in out
    assert phrases == ["RESTORE PRODUCTION"] and planned == []  # refused phrase: nothing planned


def test_neutralise_asks_the_url_and_its_phrase(monkeypatch):
    answers = iter(["acme_copy", "http://127.0.0.1:8070"])
    monkeypatch.setattr(common, "ask_text", lambda *a, **k: next(answers))
    monkeypatch.setattr(common, "confirm_with_phrase", lambda label, phrase: phrase == "NEUTRALISE")
    planned: list = []
    monkeypatch.setattr(common, "apply_if_confirmed", lambda commands: planned.append(commands))
    common.neutralise_database("127.0.0.1", 5432, "odoo")
    assert len(planned) == 1 and "http://127.0.0.1:8070" in planned[0][1].command


def test_generation_writes_the_neutralisation_and_the_guarded_start():
    from odoo_dwg import templates
    from odoo_dwg.models import MigrationEnv
    env = MigrationEnv(source="12.0", target="18.0")
    text = "\n".join(c.command for c in planners.plan_migration_configs(env))
    for name in (templates.NEUTRALISE_FILE, templates.NEUTRAL_CHECK_FILE, "open_for_testing.sh"):
        assert str(env.root / name) in text, name
    opener = templates.render_open_for_testing_sh(env)
    assert "--max-cron-threads=0" in opener and "--http-interface=127.0.0.1" in opener
    assert opener.index(templates.NEUTRAL_CHECK_FILE) < opener.index("exec ")
