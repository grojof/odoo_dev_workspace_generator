"""Egress control (OpenSnitch) and mail capture (Mailpit): pure builders and plans."""

from __future__ import annotations

import json
import re

from odoo_dwg import egress, planners, templates
from odoo_dwg.models import DB_NAME_RE, MigrationEnv, WorkspaceConfig
from odoo_dwg.provisioning import ProvisionFacts, provision_rows

RESOLVERS = ["10.255.255.254"]


def _names(rules: list[dict]) -> list[str]:
    return [egress.rule_filename(rule) for rule in rules]


# --- rules --------------------------------------------------------------------


def test_owned_rules_sort_ahead_of_every_other_rule():
    ours = _names(egress.baseline_rules(RESOLVERS))
    # The package's own, the operator's, and what the UI creates from a prompt.
    others = ["000-allow-localhost.json", "001-allow-my-tool.json",
              "allow-always-simple-usr-bin-python3.12.json", "deny-once-x.json"]
    ordered = sorted(ours + others)
    assert ordered[: len(ours)] == sorted(ours)
    assert all(name.startswith(egress.RULE_PREFIX) for name in ours)


def test_odoo_is_rejected_before_the_infrastructure_allowance():
    names = sorted(_names(egress.baseline_rules(RESOLVERS)))
    odoo = names.index("00-odwg-010-reject-odoo-external.json")
    infra = names.index("00-odwg-020-allow-dev-infrastructure.json")
    localhost = names.index("00-odwg-000-allow-localhost.json")
    assert localhost < odoo < infra


def test_rule_shapes():
    rules = {rule["name"]: rule for rule in egress.baseline_rules(RESOLVERS)}
    odoo = rules["00-odwg-010-reject-odoo-external"]
    assert odoo["action"] == "reject"
    assert odoo["operator"] == {"operand": "process.command", "data": "odoo-bin",
                                "type": "regexp", "list": [], "sensitive": False}
    for rule in rules.values():
        assert rule["precedence"] is True and rule["duration"] == "always"
        json.loads(egress.render_rule(rule))  # valid JSON


def test_infrastructure_hosts_match_what_they_should_and_nothing_else():
    rules = {rule["name"]: rule for rule in egress.baseline_rules(RESOLVERS)}
    pattern = re.compile(rules["00-odwg-020-allow-dev-infrastructure"]["operator"]["data"])
    for host in ("github.com", "cli.github.com", "objects.githubusercontent.com", "pypi.org",
                 "files.pythonhosted.org", "releases.astral.sh", "archive.ubuntu.com",
                 "es.archive.ubuntu.com", "de.archive.ubuntu.com",
                 "registry.npmjs.org"):
        assert pattern.fullmatch(host), host
    for host in ("evilgithub.com", "github.com.evil.io", "smtp.gmail.com", "api.stripe.com",
                 "example.com", "evil.es.archive.ubuntu.com", "archive.ubuntu.com.evil.io"):
        assert not pattern.fullmatch(host), host


def test_resolvers_come_from_resolv_conf_without_loopback():
    text = "# generated\nnameserver 127.0.0.53\nnameserver 10.255.255.254\nnameserver ::1\n" \
           "nameserver 10.255.255.254\nsearch lan\nnameserver 1.1.1.1\n"
    assert egress.parse_resolvers(text) == ["10.255.255.254", "1.1.1.1"]
    rules = {rule["name"]: rule for rule in egress.baseline_rules(["10.255.255.254", "1.1.1.1"])}
    dns = re.compile(rules["00-odwg-001-allow-dns-resolvers"]["operator"]["data"])
    assert dns.fullmatch("1.1.1.1") and not dns.fullmatch("1.1.1.12")
    # With no non-loopback resolver there is no resolver rule at all.
    assert "00-odwg-001-allow-dns-resolvers" not in {r["name"] for r in egress.baseline_rules([])}


def test_no_rule_names_an_assistant():
    text = json.dumps(egress.baseline_rules(RESOLVERS)).lower()
    for word in ("claude", "anthropic", "copilot", "openai", "cursor"):
        assert word not in text


# --- daemon configuration -----------------------------------------------------


def test_hardening_script_applies_settings_and_keeps_other_keys(tmp_path):
    shipped = {"Server": {"Address": "unix:///tmp/osui.sock"}, "DefaultAction": "allow",
               "ProcMonitorMethod": "ebpf", "LogLevel": 2,
               "FwOptions": {"ConfigPath": "/etc/opensnitchd/system-fw.json", "QueueBypass": True},
               "Internal": {"GCPercent": 100, "FlushConnsOnStart": True}}
    config = tmp_path / "default-config.json"
    config.write_text(json.dumps(shipped))
    script = egress.hardening_script().replace(repr(egress.OPENSNITCH_CONFIG), repr(str(config)))
    exec(compile(script, "hardening", "exec"), {})  # the exact snippet the plan runs
    result = json.loads(config.read_text())
    assert egress.config_deviations(result) == []
    assert result["FwOptions"]["ConfigPath"] == "/etc/opensnitchd/system-fw.json"
    assert result["Internal"]["GCPercent"] == 100
    assert result["Server"]["Address"] == shipped["Server"]["Address"]
    assert result["Server"]["Loggers"] == [{"Name": "syslog", "Format": "rfc5424"}]
    # And the package defaults are exactly the deviations the check reports.
    assert len(egress.config_deviations(shipped)) == 6  # InterceptUnknown is absent here


# --- plans --------------------------------------------------------------------


def test_opensnitch_plan_verifies_then_installs_stopped_then_configures():
    cmds = [c.command for c in planners.plan_opensnitch(RESOLVERS)]
    joined = "\n".join(cmds)
    for name, sha512 in egress.OPENSNITCH_PACKAGES:
        assert f"echo '{sha512}  /tmp/odwg-opensnitch/{name}' | sha512sum -c -" in joined
    install = next(i for i, c in enumerate(cmds) if "apt-get -y install /tmp/" in c)
    verifies = [i for i, c in enumerate(cmds) if "sha512sum -c" in c]
    harden = next(i for i, c in enumerate(cmds) if c.startswith("python3 - <<'PYEOF'"))
    start = next(i for i, c in enumerate(cmds) if "systemctl restart opensnitch" in c)
    assert max(verifies) < install < harden < start
    # policy-rc.d keeps the service stopped, refuses to clobber an existing one,
    # and is removed even when the install fails.
    assert "if [ -e /usr/sbin/policy-rc.d ] && ! grep -q 'odoo_dwg:" in cmds[install]
    assert "trap 'rm -f /usr/sbin/policy-rc.d' EXIT INT TERM HUP;" in cmds[install]
    assert cmds[install].index("trap ") < cmds[install].index("printf ")
    # Only the tool's own rules are replaced.
    assert f"rm -f /etc/opensnitchd/rules/{egress.RULE_PREFIX}*.json" in cmds
    rule_writes = [c for c in cmds if c.startswith("cat > /etc/opensnitchd/rules/")]
    assert len(rule_writes) == len(egress.baseline_rules(RESOLVERS))


def test_opensnitch_plan_skips_the_install_when_the_pinned_version_is_present():
    cmds = [c.command for c in planners.plan_opensnitch(RESOLVERS, "1.8.0-1")]
    assert not any("curl" in c or "apt-get" in c for c in cmds)
    assert any("systemctl restart opensnitch" in c for c in cmds)


def test_mailpit_plan_verifies_and_runs_on_loopback():
    cmds = [c.command for c in planners.plan_mailpit()]
    joined = "\n".join(cmds)
    assert f"echo '{egress.MAILPIT_SHA256}  /tmp/odwg-mailpit/mailpit-linux-amd64.tar.gz'" in joined
    assert "sha256sum -c -" in joined
    unit = egress.render_mailpit_unit()
    assert "--smtp 127.0.0.1:1025 --listen 127.0.0.1:8025" in unit
    assert "DynamicUser=yes" in unit and "StateDirectory=mailpit" in unit
    # Already at the pinned version: unit and restart only.
    again = [c.command for c in planners.plan_mailpit(egress.MAILPIT_VERSION)]
    assert not any("curl" in c for c in again)


def test_mail_redirect_is_column_aware_and_quoted():
    sql = egress.mail_redirect_sql()
    assert "smtp_host = '127.0.0.1', smtp_port = 1025" in sql
    assert "smtp_user = NULL, smtp_pass = NULL" in sql
    assert "column_name = 'smtp_authentication'" in sql  # absent before Odoo 15
    assert "to_regclass('fetchmail_server')" in sql  # absent without its module
    cmd = planners.plan_mail_redirect("acme-copy.2026", "127.0.0.1", 5432, "odoo")[0].command
    assert cmd.startswith("psql -h 127.0.0.1 -p 5432 -U odoo -d acme-copy.2026 -v ON_ERROR_STOP=1 -c '")


def test_database_names_follow_odoo():
    for name in ("acme", "acme_copy", "acme-2026.09", "A1"):
        assert DB_NAME_RE.fullmatch(name)
    for name in ("", "a", "-acme", "acme copy", "acme;drop", "acme'x"):
        assert not DB_NAME_RE.fullmatch(name)


# --- generated configs and the readiness report ---------------------------------


def test_generated_configs_send_mail_to_the_capture():
    cfg = WorkspaceConfig(name="acme", versions=["18.0"])
    cfg.normalize_defaults()
    for conf in (templates.render_odoo_conf(cfg, "18.0"),
                 templates.render_migration_conf(MigrationEnv(source="16.0", target="17.0"), "17.0")):
        assert "smtp_server = 127.0.0.1\nsmtp_port = 1025\n" in conf


def _facts(**kw) -> ProvisionFacts:
    return ProvisionFacts(os_id="ubuntu", os_version_id="24.04", **kw)


def _row(facts: ProvisionFacts, label_start: str) -> tuple[str, str]:
    for state, label, detail in provision_rows(facts):
        if label.startswith(label_start):
            return state, detail
    raise AssertionError(label_start)


def test_readiness_rows_for_egress_and_mail():
    assert _row(_facts(), "Egress firewall")[0] == "INFO"
    assert _row(_facts(), "Mail capture")[0] == "INFO"
    hardened = _facts(opensnitch_version="1.8.0-1", opensnitch_active=True)
    assert _row(hardened, "Egress firewall") == ("OK", "1.8.0-1 running, hardened (default deny)")
    softened = _facts(opensnitch_version="1.8.0-1", opensnitch_active=True,
                      opensnitch_deviations=["DefaultAction: 'allow'"])
    state, detail = _row(softened, "Egress firewall")
    assert state == "WARN" and "DefaultAction: 'allow'" in detail
    stopped = _facts(opensnitch_version="1.8.0-1", opensnitch_active=False)
    assert _row(stopped, "Egress firewall")[0] == "WARN"
    assert _row(_facts(mailpit_version="1.31.2", mailpit_active=True), "Mail capture")[0] == "OK"


# --- turning off and uninstalling ---------------------------------------------


def test_switches_persist_across_restarts():
    assert [c.command for c in planners.plan_service_switch("opensnitch", on=False)] == [
        "systemctl disable --now opensnitch"]
    assert [c.command for c in planners.plan_service_switch("mailpit", on=True)] == [
        "systemctl enable --now mailpit"]


def test_opensnitch_uninstall_keeps_the_operators_rules():
    cmds = [c.command for c in planners.plan_opensnitch_uninstall()]
    assert cmds[0] == "systemctl disable --now opensnitch"
    assert cmds[1] == f"rm -f /etc/opensnitchd/rules/{egress.RULE_PREFIX}*.json"
    assert cmds[2] == "apt-get -y purge --autoremove opensnitch python3-opensnitch-ui"
    assert cmds[3] == "modprobe -r nft_queue nfnetlink_queue 2>/dev/null || true"
    assert not any("rm -rf /etc/opensnitchd" in c for c in cmds)


def test_mailpit_uninstall_removes_unit_binary_and_mail():
    joined = "\n".join(c.command for c in planners.plan_mailpit_uninstall())
    assert "systemctl disable --now mailpit" in joined
    assert "rm -f /etc/systemd/system/mailpit.service && systemctl daemon-reload" in joined
    assert "rm -f /usr/local/bin/mailpit" in joined
    assert "rm -rf /var/lib/mailpit /var/lib/private/mailpit" in joined
