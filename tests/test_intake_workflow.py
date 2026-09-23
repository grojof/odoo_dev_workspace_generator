"""The intake steps from the menu, with PostgreSQL and git stood in for."""

from __future__ import annotations

import json

import pytest

from odoo_dwg import findings as fl
from odoo_dwg import intake as it
from odoo_dwg.models import MigrationEnv
from odoo_dwg.workflows import intake as wi

COMMIT = "c" * 40


@pytest.fixture
def env(tmp_path, monkeypatch) -> MigrationEnv:
    monkeypatch.setattr(MigrationEnv, "base_dir", str(tmp_path))
    env = MigrationEnv(source="12.0", target="18.0")
    env.intake = it.IntakeRecord("ACME_original", archive_root="client-src/acme")
    return env


@pytest.fixture
def written(monkeypatch) -> list:
    """What the recording plan would write, applied for real so the test can read it."""
    plans: list = []

    def apply(commands):
        plans.append(commands)
        return False
    monkeypatch.setattr(wi, "apply_if_confirmed", apply)
    return plans


def _answers(monkeypatch, *values: str) -> None:
    queue = list(values)
    monkeypatch.setattr(wi, "ask_text", lambda *a, **k: queue.pop(0))


def _files(plan) -> dict[str, str]:
    """``{path: content}`` of every ``write_text_file_command`` in a plan."""
    out = {}
    for command in plan:
        header, _, rest = command.command.partition("\n")
        if "<<'" not in header:
            continue
        end = header.rsplit("<<'", 1)[1].rstrip("'")
        lines = rest.split("\n")
        target = command.command.rsplit("mv -f ", 1)[1].split(" ", 1)[1].strip().strip("'")
        out[target] = "\n".join(lines[: lines.index(end)]) + "\n"
    return out


def _archive(root) -> None:
    for d, module, manifest in [("core/odoo/addons", "base", "__manifest__.py"),
                                ("core/addons", "sale", "__manifest__.py"),
                                ("custom", "acme_sale", "__manifest__.py"),
                                ("oca", "partner_registry", "__openerp__.py")]:
        (root / d / module).mkdir(parents=True)
        (root / d / module / manifest).write_text("{}\n")


def test_classifying_the_archive_records_the_clients_dirs_and_what_is_off(env, monkeypatch,
                                                                          written, tmp_path):
    root = env.root / "client-src" / "acme"
    _archive(root)
    conf = tmp_path / "odoo.conf"
    conf.write_text("[options]\naddons_path = /srv/src/core/odoo/addons,/srv/src/custom,"
                    "/srv/src/oca,/srv/src/core/addons\n")
    _answers(monkeypatch, str(conf), "ACME")
    monkeypatch.setattr(wi, "psql_rows", lambda *a, **k: [["base"], ["acme_sale"],
                                                           ["partner_registry"], ["lost"]])
    monkeypatch.setattr(wi, "repo_state", lambda path: {
        "remote": "https://github.com/acme/custom.git", "dirty": "acme_sale/models.py"}
        if str(path).endswith("custom") else {})
    wi.classify_archive(env)
    files = _files(written[0])
    record = it.parse_intake(files[str(env.intake_file)])
    assert record.addons_dirs == ("custom", "oca") and record.core_dir == "core"
    ledger = fl.parse_ledger(files[str(env.findings_ledger)])
    ids = {f.id for f in ledger.findings}
    assert {"intake-archive", "intake-installed-without-code", "intake-uncommitted-custom"} <= ids
    missing = next(f for f in ledger.findings if f.id == "intake-installed-without-code")
    assert missing.evidence == {"modules": ["lost"]}  # the legacy manifest was found
    assert all(f.audience == "internal" for f in ledger.findings)
    assert "partner_registry\toca" in files[str(env.findings_data_dir / "intake-installed.tsv")]


def test_identifying_an_ocb_core_records_its_commit(env, monkeypatch, written):
    env.intake = it.IntakeRecord("ACME_original", archive_root="client-src/acme", core_dir="core")
    for flavour in ("odoo", "ocb"):
        (env.history_dir / f"{flavour}-12.0").mkdir(parents=True)
    client = {"addons/web/a.py": "2" * 40, "addons/web/x.xml_backup": "9" * 40}
    monkeypatch.setattr(wi, "tree_blobs", lambda root: client)
    official, ocb = "a" * 40, COMMIT

    def git(repo, *args):
        line = {"odoo-12.0": official, "ocb-12.0": ocb}[repo.name]
        if args[0] == "log":
            return f"{line} 2021-11-03\n"
        if args[:2] == ("ls-tree", "-r"):  # OCB has the client's version, official does not
            blob = "2" * 40 if repo.name == "ocb-12.0" else "1" * 40
            return f"100644 blob {blob}\taddons/web/a.py\n"
        return ""
    monkeypatch.setattr(wi, "git_output", git)
    monkeypatch.setattr(wi, "git_raw_log", lambda repo, paths: "")
    _answers(monkeypatch, "ACME")
    wi.identify_core(env)
    files = _files(written[-1])
    record = it.parse_intake(files[str(env.intake_file)])
    assert record.core == it.Core("ocb", COMMIT)
    core = next(f for f in fl.parse_ledger(files[str(env.findings_ledger)]).findings
                if f.id == "intake-core")
    assert core.severity == "info" and core.evidence["client_only"] == ["addons/web/x.xml_backup"]


def test_a_finding_already_recorded_is_not_recorded_twice(env, monkeypatch, written, capsys):
    ledger = fl.new_ledger("ACME", "ACME", "12.0", "18.0", "ACME_original")
    finding = wi._finding("intake-restore", "info", "x", "s", {"a": 1}, "q", "a")
    ledger = fl.add_findings(ledger, fl.parse_findings(json.dumps([finding])))
    env.findings_dir.mkdir(parents=True)
    env.findings_ledger.write_text(fl.dump_ledger(ledger))
    wi._record(env, env.intake, [finding], {})
    assert "already in the ledger" in capsys.readouterr().out
    written_ledger = fl.parse_ledger(_files(written[0])[str(env.findings_ledger)])
    assert [f.id for f in written_ledger.findings] == ["intake-restore"]


def test_an_unreadable_intake_is_refused(env):
    env.root.mkdir(parents=True)
    env.intake_file.write_text('{"schema": 1, "reference_database": "x;y"}')
    with pytest.raises(it.IntakeError):
        wi.load_intake(env)


def test_the_exact_commit_between_two_samples_is_found(env, monkeypatch, written):
    """The branch's commits are dense early and sparse late: the true commit sits
    between the best sample and its neighbour, not within days of it."""
    env.intake = it.IntakeRecord("ACME_original", archive_root="client-src/acme", core_dir="core")
    for flavour in ("odoo", "ocb"):
        (env.history_dir / f"{flavour}-12.0").mkdir(parents=True)
    commits = [f"{i:040x}" for i in range(1000)]          # newest first
    exact = commits[5]
    client = {"addons/web/a.py": "e" * 40}
    monkeypatch.setattr(wi, "tree_blobs", lambda root: client)

    def git(repo, *args):
        if args[0] == "log":
            if repo.name != "ocb-12.0":
                return ""
            # Years between the head and the rest; the exact commit is near the head.
            return "".join(f"{c} {'2024-01-01' if i < 3 else '2021-11-03'}\n"
                           for i, c in enumerate(commits))
        if args[:2] == ("ls-tree", "-r"):
            blob = "e" * 40 if args[2] == exact else f"{commits.index(args[2]) % 9}" * 40
            return f"100644 blob {blob}\taddons/web/a.py\n"
        return ""
    monkeypatch.setattr(wi, "git_output", git)
    monkeypatch.setattr(wi, "git_raw_log", lambda repo, paths: "")
    _answers(monkeypatch, "ACME")
    wi.identify_core(env)
    record = it.parse_intake(_files(written[-1])[str(env.intake_file)])
    assert record.core == it.Core("ocb", exact)
