"""Taking in a client copy: the record, the restore errors, the reader role, the
archive and the core — each classifier on invented fixtures."""

from __future__ import annotations

import json

import pytest

from odoo_dwg import intake as it

COMMIT = "4" * 40


def _record(**over) -> dict:
    raw = {"schema": 1, "reference_database": "ACME_original", "reader_role": "acme_reader",
           "archive_root": "client-src/acme_addons", "addons_dirs": ["custom", "web"],
           "core": {"flavour": "ocb", "commit": COMMIT}}
    raw.update(over)
    return raw


# --- the record ------------------------------------------------------------------------

def test_the_record_round_trips():
    record = it.parse_intake(json.dumps(_record()))
    assert record.core == it.Core("ocb", COMMIT) and record.core.url.endswith("/OCA/OCB")
    assert it.parse_intake(it.dump_intake(record)) == record


@pytest.mark.parametrize("over, expected", [
    ({"schema": 2}, "schema version"),
    ({"reference_database": "x;drop"}, "reference_database"),
    ({"archive_root": "/etc"}, "archive_root"),
    ({"addons_dirs": ["../../etc"]}, "addons_dirs"),
    ({"core": {"flavour": "fork", "commit": COMMIT}}, "core"),
    ({"core": {"flavour": "ocb", "commit": "abc"}}, "core"),
])
def test_a_record_that_cannot_be_used_is_refused(over, expected):
    with pytest.raises(it.IntakeError) as caught:
        it.parse_intake(json.dumps(_record(**over)))
    assert any(expected in p for p in caught.value.problems)


# --- the restore -----------------------------------------------------------------------

STDERR = """pg_restore: error: could not execute query: ERROR:  function array_cat(anyarray, anyarray) does not exist
Command was: CREATE AGGREGATE public.array_concat_agg(anyarray) (
    SFUNC = array_cat,
    STYPE = anyarray
);


pg_restore: error: could not execute query: ERROR:  type "geography" does not exist
Command was: CREATE TABLE public.x (g geography);
pg_restore: warning: errors ignored on restore: 2
"""


def test_restore_errors_are_read_with_their_command_and_classified():
    errors = it.parse_restore_errors(STDERR)
    assert len(errors) == 2
    assert "CREATE AGGREGATE public.array_concat_agg" in errors[0].command
    verdicts = it.classify(errors)
    assert verdicts[0][1] is not None and verdicts[0][1].id == "array-cat-anyarray-aggregate"
    assert "postgresql.org/docs/release/14.0" in verdicts[0][1].source
    assert verdicts[1][1] is None  # unknown: a finding, never passed over


# --- the reader role -------------------------------------------------------------------

def test_the_reader_role_hides_secrets_column_by_column():
    columns = [("res_users", "id"), ("res_users", "login"), ("res_users", "password"),
               ("ir_config_parameter", "key"), ("ir_config_parameter", "value"),
               ("sale_order", "access_token"), ("sale_order", "payment_token_id"),
               ("res_partner", "name")]
    sql = it.reader_role_sql("acme_reader", "ACME_original", columns)
    assert 'GRANT SELECT ON ALL TABLES IN SCHEMA public TO "acme_reader";' in sql
    assert 'GRANT SELECT ON ALL SEQUENCES IN SCHEMA public TO "acme_reader";' in sql
    assert "USAGE ON ALL SEQUENCES" not in sql  # reading a sequence, never advancing it
    assert 'REVOKE SELECT ON public."res_users" FROM "acme_reader";' in sql
    assert 'GRANT SELECT ("id", "login") ON public."res_users"' in sql
    assert 'GRANT SELECT ("key") ON public."ir_config_parameter"' in sql
    assert '"payment_token_id"' in sql  # a foreign key is not a secret
    assert "res_partner" not in sql  # nothing secret: the table-wide grant stands
    assert "information_schema" not in sql
    assert it.hidden_columns(columns) == [("ir_config_parameter", "value"),
                                          ("res_users", "password"), ("sale_order", "access_token")]


def test_the_reader_role_refuses_a_name_that_is_not_one():
    with pytest.raises(it.IntakeError):
        it.reader_role_sql("r; DROP", "ACME_original", [])


# --- the archive -----------------------------------------------------------------------

CONF = """[options]
addons_path = /opt/acme/src/core/odoo/addons,/opt/acme/src/custom,/opt/acme/src/web,/opt/acme/src/gone,/opt/acme/src/core/addons
admin_passwd = hidden
"""


def test_the_addons_path_maps_onto_the_archive_and_finds_the_core():
    entries = it.conf_addons_path(CONF)
    layout = it.archive_layout(entries, {"core/odoo/addons", "custom", "web", "core/addons"},
                               {"core/odoo/addons"})
    assert layout.dirs == ("core/odoo/addons", "custom", "web", "core/addons")
    assert layout.missing == ("/opt/acme/src/gone",)
    assert layout.core_root == "core"
    assert layout.client_dirs == ("custom", "web")


def test_modules_load_from_the_first_directory_and_legacy_manifests_count():
    listing = [("custom", "sale_margin", "__manifest__.py"),
               ("web", "web_widget", "__manifest__.py"),
               ("web", "sale_margin", "__manifest__.py"),
               ("l10n", "partner_registry", "__openerp__.py")]
    modules = it.classify_modules(listing, {"sale_margin", "partner_registry", "lost_module"})
    assert modules.loads_from["sale_margin"] == "custom"
    assert modules.duplicates == {"sale_margin": ["custom", "web"]}
    assert modules.legacy_manifest == ("partner_registry",)
    assert modules.installed_without_code == ("lost_module",)


# --- the core --------------------------------------------------------------------------

def test_the_blob_id_is_gits():
    # `printf 'hello\n' | git hash-object --stdin`, a value git has printed for years.
    assert it.git_blob_id(b"hello\n") == "ce013625030ba8dba906f756967f9e9ca394464a"


RAW = (
    "@" + "a" * 40 + " 2021-10-01\n"
    ":100644 100644 " + "1" * 40 + " " + "2" * 40 + " M\taddons/web/models.py\n"
    "@" + "b" * 40 + " 2021-11-03\n"
    # a merge commit's line for one parent (--diff-merges=separate)
    ":100644 100644 " + "2" * 40 + " " + "3" * 40 + " M\taddons/mail/thread.py\n"
    "@" + "c" * 40 + " 2021-09-01\n"
    ":100644 100644 " + "0" * 40 + " " + "2" * 40 + " M\taddons/web/models.py\n"
)


def test_the_raw_log_is_read_by_its_tab_merges_included():
    found = it.parse_raw_log(RAW)
    assert found[("addons/mail/thread.py", "3" * 40)] == "2021-11-03"  # only a merge made it
    assert found[("addons/web/models.py", "2" * 40)] == "2021-09-01"   # the first date wins


def test_ls_tree_is_read():
    text = "100644 blob " + "a" * 40 + "\taddons/web/a b.py\n040000 tree " + "b" * 40 + "\taddons\n"
    assert it.parse_ls_tree(text) == {"addons/web/a b.py": "a" * 40}


TREE = {"addons/web/models.py": "2" * 40, "addons/mail/thread.py": "3" * 40,
        "addons/base/x.py": "5" * 40}


def test_a_core_matching_its_closest_commit_is_that_flavour():
    client = {**TREE, "addons/web/views/r.xml_backup": "6" * 40,
              "addons/web/__pycache__/m.cpython-37.pyc": "7" * 40}
    verdict = it.core_identity(client, "ocb", COMMIT, TREE, {})
    assert (verdict.flavour, verdict.commit, verdict.differing) == ("ocb", COMMIT, ())
    assert verdict.client_only == ("addons/web/views/r.xml_backup",)


def test_a_file_differing_from_the_commit_but_in_history_is_another_version_not_a_patch():
    client = {**TREE, "addons/mail/thread.py": "3" * 40, "addons/web/models.py": "0" * 40}
    history = {("addons/web/models.py", "0" * 40): "2021-09-01"}
    verdict = it.core_identity(client, "odoo", COMMIT, TREE, {"odoo": {}, "ocb": history})
    assert verdict.flavour == "odoo" and verdict.differing == ("addons/web/models.py",)
    assert verdict.patched == ()


def test_a_local_patch_is_named_by_path():
    client = {**TREE, "addons/mail/thread.py": "f" * 40}
    verdict = it.core_identity(client, "ocb", COMMIT, TREE, {"odoo": it.parse_raw_log(RAW),
                                                             "ocb": it.parse_raw_log(RAW)})
    assert verdict.flavour == "patched" and verdict.patched == ("addons/mail/thread.py",)


def test_without_a_commit_the_core_is_unidentified():
    assert it.core_identity(TREE, "odoo", "", {}, {}).flavour == "unidentified"


def test_sampling_spreads_over_the_line_and_keeps_both_ends():
    commits = [str(i) for i in range(1000)]
    picked = it.sample(commits, 10)
    assert picked[0] == "0" and picked[-1] == "999" and len(picked) == 10
    assert it.sample(commits[:5], 10) == commits[:5]


def test_the_best_commit_is_the_closest_tree():
    client = {"a.py": "1" * 40, "b.py": "2" * 40, "stray.xml_backup": "3" * 40}
    trees = [("c1", {"a.py": "1" * 40, "b.py": "0" * 40}),
             ("c2", {"a.py": "1" * 40, "b.py": "2" * 40}),
             ("c3", {"a.py": "1" * 40, "b.py": "2" * 40, "new.py": "4" * 40})]
    match = it.best_commit(client, trees)
    assert match == it.CommitMatch("c2", 1, ("stray.xml_backup",))  # the stray counts once
    assert it.best_commit(client, []) is None
    # A commit whose tree has none of the client's paths is not a perfect match.
    assert it.best_commit(client, [("ancient", {}), ("c2", trees[1][1])]).commit == "c2"


# --- plans -----------------------------------------------------------------------------

from pathlib import Path  # noqa: E402

from odoo_dwg import planners, templates  # noqa: E402
from odoo_dwg.models import MigrationEnv  # noqa: E402


def _env(intake: it.IntakeRecord | None = None) -> MigrationEnv:
    return MigrationEnv(source="12.0", target="18.0", intake=intake)


def test_the_restore_keeps_its_errors_and_carries_no_owner():
    plan = planners.plan_intake_restore(_env(), Path("/x/acme.dump"), "ACME_original")
    restore = plan[-1].command
    assert "--no-owner --no-acl" in restore and "2> " in restore and "|| true" in restore
    assert "createdb" in plan[1].command and "ACME_original" in plan[1].command
    with pytest.raises(ValueError):
        planners.plan_intake_restore(_env(), Path("/x/a.dump"), "bad;name")


def test_the_role_plan_never_carries_the_password():
    plan = planners.plan_reader_role(_env(), "ACME_original", "acme_reader", "SELECT 1;", True)
    create = plan[0].command
    assert "secrets.token_hex(24)" in create and "sudo -n -u postgres psql" in create
    assert "chmod 600" in create and "$PW" in create
    assert len(planners.plan_reader_role(_env(), "ACME_original", "acme_reader", "x", False)) == 1


def test_the_archive_is_unpacked_read_only_and_histories_are_blobless():
    plan = planners.plan_unpack_archive(_env(), Path("/x/addons.tar.gz"), "acme_addons")
    assert plan[-1].command.startswith("chmod -R a-w ") and "client-src/acme_addons" in plan[-1].command
    history = planners.plan_history(_env(), "ocb", "12.0")[0].command
    assert "--filter=blob:none" in history and "--no-checkout" in history
    assert "https://github.com/OCA/OCB" in history


def test_with_an_intake_the_source_is_the_clients_core_pinned():
    record = it.IntakeRecord("ACME_original", "acme_reader", "client-src/acme", ("custom", "web"),
                             it.Core("ocb", COMMIT))
    env = _env(record)
    text = "\n".join(c.command for c in planners.plan_seed_environment(env))
    assert f"fetch -q --depth 1 https://github.com/OCA/OCB {COMMIT}" in text
    assert "checkout -q FETCH_HEAD" in text and "oca/" not in text  # client's own OCA, as delivered
    conf = templates.render_seed_conf(env)
    assert f"client-src/acme/custom,{env.root}/client-src/acme/web" in conf
    assert f"data_dir = {env.data_dir}" in conf
    assert "data_dir" not in templates.render_seed_conf(_env())  # no intake: as before


def test_a_private_remote_is_recorded_without_its_credentials():
    assert it.redact_url("https://bot:ghp_secret@github.com/acme/private.git") == \
        "https://github.com/acme/private.git"
    assert it.redact_url("git@github.com:acme/private.git") == "git@github.com:acme/private.git"
    assert it.redact_url("https://github.com/OCA/web.git") == "https://github.com/OCA/web.git"


def test_reading_a_client_repository_never_reaches_its_remote():
    import inspect

    from odoo_dwg import system
    source = inspect.getsource(system.repo_state)
    for verb in ("fetch", "pull", "ls-remote", "clone", "push", "remote update"):
        assert f'"{verb}"' not in source, verb
    assert "redact_url" in source


def test_a_command_too_long_to_be_an_argument_runs_from_a_script(tmp_path, monkeypatch):
    import tempfile

    from odoo_dwg import system
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    with system._Bash("true") as argv:
        assert argv == ["bash", "-lc", "true"]
    long = "echo " + "x" * (system._ARG_LIMIT + 1)
    with system._Bash(long) as argv:
        assert argv[:2] == ["bash", "-l"] and Path(argv[2]).read_text() == long
        script = Path(argv[2])
    assert not script.exists()  # removed afterwards


def test_building_the_source_first_creates_its_conf_directory():
    record = it.IntakeRecord("ACME_original", "", "client-src/acme", ("custom",),
                             it.Core("ocb", COMMIT))
    env = _env(record)
    commands = planners.plan_seed_environment(env)
    mkdir = next(i for i, c in enumerate(commands) if str(env.conf_dir) in c.command
                 and c.command.startswith("mkdir"))
    write = next(i for i, c in enumerate(commands) if str(env.config_file("12.0")) in c.command)
    assert mkdir < write


def test_a_manifests_python_imports_become_pip_names():
    manifest = ("{'name': 'X', 'external_dependencies': {'python': ['OpenSSL', 'zeep', "
                "'dateutil'], 'bin': ['wkhtmltopdf']}}")
    imports = it.manifest_python_imports(manifest)
    assert imports == ["OpenSSL", "zeep", "dateutil"]
    assert it.pip_names(imports) == ("pyOpenSSL", "python-dateutil", "zeep")
    assert it.manifest_python_imports("{'name': 'X'}") == []
    assert it.manifest_python_imports("__import__('os').system('x')") is None  # never executed


def test_the_source_venv_gets_the_clients_python_dependencies():
    record = it.IntakeRecord("ACME_original", "", "client-src/acme", ("custom",),
                             it.Core("ocb", COMMIT), "core", ("pyOpenSSL", "zeep"))
    env = _env(record)
    assert it.parse_intake(it.dump_intake(record)) == record
    text = "\n".join(c.command for c in planners.plan_seed_environment(
        env, exists=lambda p: True))  # everything built already: the deps still install
    assert "uv pip install --python" in text and "pyOpenSSL zeep" in text
    # Never upgrades what Odoo pinned: constrained to what the venv holds.
    assert "uv pip freeze" in text and '-c "$held"' in text


# --- survey, availability, scan (spec 3b) -----------------------------------------------

def test_the_survey_only_reads_and_its_rows_are_read():
    import re
    writes = re.compile(r"\b(INSERT|UPDATE|DELETE|CREATE|DROP|ALTER|TRUNCATE)\b", re.I)
    for sql in it.SURVEY_SQL.values():  # whole words: create_date is a column, not a statement
        assert not writes.search(sql), sql
    queue = it.read_mail_queue([["exception", "12", "2022-01-03", "2026-09-01"], ["bad"]])
    assert queue == [it.MailQueue("exception", 12, "2022-01-03", "2026-09-01")]
    crons = it.overdue_crons([["Mail queue", "1 hours", "2026-09-21 11:00", "3"], ["x"]])
    assert crons == [["Mail queue", "1 hours", "2026-09-21 11:00", "3"]]


def test_origin_comes_from_the_recorded_remote():
    remotes = {"web": "https://github.com/OCA/web.git", "custom": "https://github.com/acme/x.git",
               "tools": "git@github.com:OCA/server-tools"}
    assert it.oca_repo(remotes["tools"]) == "server-tools"
    assert it.module_origin("core/addons", {"core/addons"}, remotes) == "odoo"
    assert it.module_origin("web", set(), remotes) == "oca"
    assert it.module_origin("custom", set(), remotes) == "custom"


class _Fate:
    def __init__(self, module, kind, successor, version):
        self.module, self.kind, self.successor, self.version = module, kind, successor, version


STEPS = ["13.0", "14.0", "15.0"]


def test_availability_follows_moves_merges_and_gaps():
    installed = {"web_moved": ("oca", "web"), "old_sale": ("oca", "sale-workflow"),
                 "never_ported": ("oca", "account-invoicing"), "acme_custom": ("custom", ""),
                 "sale": ("odoo", "")}
    fates = [_Fate("old_sale", "merged", "sale", "14.0")]
    found = {"13.0": {"web_moved": "web", "old_sale": "sale-workflow", "sale": "core"},
             "14.0": {"web_moved": "web-extra", "sale": "core"},
             "15.0": {"web_moved": "web-extra", "sale": "core"}}
    rows = {r.module: r for r in it.availability(installed, fates, STEPS, found)}
    assert rows["web_moved"].where == ("web", "web-extra", "web-extra") and rows["web_moved"].moved
    assert rows["web_moved"].gaps == ()
    merged = rows["old_sale"]
    assert merged.names == ("old_sale", "sale", "sale") and merged.merged_at == "14.0"
    assert merged.where == ("sale-workflow", "core", "core") and merged.gaps == ()
    assert rows["never_ported"].gaps == (0, 1, 2) and not rows["never_ported"].moved
    assert rows["acme_custom"].where == ("port", "port", "port") and rows["acme_custom"].gaps == ()
    assert rows["sale"].where == ("core", "core", "core")


def test_the_scanner_works_before_it_is_believed(monkeypatch):
    assert it.scanner_self_test() == []
    code = "import requests\n# requests.get(x) in a comment\nr = requests.post(url, json=d)\n"
    assert it.scan_source(code) == [(3, "requests", "r = requests.post(url, json=d)")]
    assert it.scan_skipped("acme/tests/test_x.py") and it.scan_skipped("acme/migrations/1/p.py")
    assert not it.scan_skipped("acme/models/x.py")
    broken = (("requests", r"\brequestz\.", "r = requests.post(url)"), *it.NETWORK_PATTERNS[1:])
    monkeypatch.setattr(it, "NETWORK_PATTERNS", broken)
    assert it.scanner_self_test() == ["requests"]


def test_the_org_listing_page_is_read():
    page = json.dumps([{"name": "web"}, {"name": "server-tools"}, {"name": "x;rm"}, {"id": 3}])
    assert it.parse_repo_page(page) == ["web", "server-tools"]
    assert it.parse_repo_page("[]") == [] and it.parse_repo_page("{") is None
    assert it.parse_repo_page('{"message": "API rate limit exceeded"}') is None


def test_oca_trees_are_blobless_and_an_absent_branch_is_remembered():
    plan = planners.plan_oca_trees(_env(), {"web": ["13.0", "14.0"], "bad;name": ["13.0"]})
    assert len(plan) == 1
    command = plan[0].command
    assert command.count("--filter=blob:none --no-checkout") == 2
    assert "ls-remote --exit-code --heads https://github.com/OCA/web.git 13.0" in command
    assert "[ $code -eq 2 ]" in command and "web-14.0.absent" in command
