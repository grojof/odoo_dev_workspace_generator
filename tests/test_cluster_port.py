"""The host's own PostgreSQL cluster, not whatever answers on loopback 5432.

On WSL 2 every distribution shares one network: a second distribution's new
cluster gets 5433 while 5432 is another distribution's server, which trusts the
same development role. Everything that defaulted to 5432 reached that server."""

from __future__ import annotations

from odoo_dwg import cli, planners, provisioning, system, templates
from odoo_dwg.models import (
    DEFAULT_DB_PORT,
    WorkspaceConfig,
    local_cluster_port,
    parse_pg_lsclusters,
)
from odoo_dwg.workflows import checks, workspace

LSCLUSTERS = (
    "16  main    5433 online postgres /var/lib/postgresql/16/main /var/log/postgresql/x.log\n"
    "14  old     5434 down   postgres /var/lib/postgresql/14/old  /var/log/postgresql/y.log\n"
    "garbage line\n"
)


def test_pg_lsclusters_is_read_with_each_cluster_state():
    assert parse_pg_lsclusters(LSCLUSTERS) == [(16, 5433, True), (14, 5434, False)]


def test_the_local_port_is_the_hosts_own_cluster():
    assert local_cluster_port([(16, 5433, False)]) == 5433       # one cluster, even stopped
    assert local_cluster_port([(16, 5433, True), (14, 5434, False)]) == 5433  # the one online
    assert local_cluster_port([(16, 5433, True), (14, 5434, True)]) == DEFAULT_DB_PORT
    assert local_cluster_port([]) == DEFAULT_DB_PORT
    assert local_cluster_port(None) == DEFAULT_DB_PORT


def test_the_check_names_the_port_it_probed():
    rows = provisioning.provision_rows(provisioning.ProvisionFacts(
        postgres_installed=True, postgres_running=True, postgres_port=5433))
    assert ("OK", "PostgreSQL", "installed and running (port 5433)") in rows


def test_the_check_probes_the_local_cluster(monkeypatch):
    seen: dict[str, object] = {}
    monkeypatch.setattr(system, "_clusters", lambda: [(16, 5433, True)])
    monkeypatch.setattr(system, "run", lambda *a, **k: type("R", (), {
        "stdout": "", "returncode": 1, "stderr": ""})())
    monkeypatch.setattr(system, "db_role_exists", lambda role, port: seen.setdefault("role", port))
    monkeypatch.setattr(system, "pg_hba_loopback_state",
                        lambda role, port: seen.setdefault("hba", port) and None)
    facts = provisioning.gather_facts()
    assert facts.postgres_port == 5433 and facts.postgres_running
    assert seen == {"role": 5433, "hba": 5433}


def test_apply_connects_to_the_server_it_configured():
    probe = next(c.command for c in planners.plan_pg_hba_trust("odoo")
                 if "connects over loopback" in c.description)
    asked = probe.index('port=$(sudo -u postgres psql -X -tAc "SHOW port;")')
    assert asked < probe.index('-h 127.0.0.1 -p "$port" -U odoo')
    assert "-h 127.0.0.1 -U" not in probe


def test_a_quick_workspace_takes_the_local_port(monkeypatch):
    monkeypatch.setattr(system, "_clusters", lambda: [(16, 5433, True)])
    answers = iter(["acme", "18.0", ""])
    monkeypatch.setattr(workspace, "ask_text", lambda *a, **k: next(answers))
    cfg = workspace._quick_profile()
    assert cfg is not None and cfg.db_port == 5433
    cfg.normalize_defaults()  # as creation does before it renders
    readme = templates.render_workspace_readme(cfg)
    assert "createdb -h 127.0.0.1 -p 5433 -U odoo acme" in readme
    # An empty database is not one Odoo can serve: the first start installs base.
    assert "bash scripts/run-odoo18.sh -d acme -i base" in readme


def test_a_profile_keeps_the_port_it_states():
    cfg = WorkspaceConfig(name="acme", versions=["18.0"], db_port=6000)
    assert "-p 6000" in templates.render_workspace_readme(cfg)


def test_read_only_commands_default_to_the_local_port(monkeypatch):
    monkeypatch.setattr(system, "_clusters", lambda: [(16, 5433, True)])
    ports: list[int] = []
    monkeypatch.setattr(checks, "neutralise_check", lambda db, host, port, user: ports.append(port))
    cli.main(["neutralise", "check", "--database", "acme_copy", "--lang", "en"])
    cli.main(["neutralise", "check", "--database", "acme_copy", "--db-port", "6000", "--lang", "en"])
    assert ports == [5433, 6000]
