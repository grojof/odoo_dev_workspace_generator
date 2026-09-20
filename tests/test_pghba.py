"""The rules PostgreSQL reports, and the two questions asked of them.

Pure: every case here is the output `pg_hba_file_rules` gives for a file shape,
taken from a real PostgreSQL 16 (see the change's design.md). The query itself
lives in `system` and is exercised by `tools/verify_pg_hba_trust.py`.
"""

from __future__ import annotations

import pytest

from odoo_dwg import pghba, system

HBA = "/etc/postgresql/16/main/pg_hba.conf"


def _row(type_="host", databases="all", users="all", address="127.0.0.1",
         netmask="255.255.255.255", method="trust", file=HBA, line=1, error="") -> str:
    return "\t".join(
        [type_, databases, users, address, netmask, method, file, str(line), error]
    )


def test_a_rule_arrives_with_its_fields_split_and_its_source_named():
    rules = pghba.parse_rules(_row(databases="all,template1", users="odoo,postgres", line=42))
    assert len(rules) == 1
    rule = rules[0]
    assert rule.databases == ("all", "template1")
    assert rule.users == ("odoo", "postgres")
    assert rule.file == HBA and rule.line == 42
    assert rule.is_tcp


def test_rows_that_cannot_be_read_are_skipped_not_guessed_at():
    assert pghba.parse_rules("") == []
    assert pghba.parse_rules("host\tall\n\n") == []


def test_a_trust_for_every_role_counts_on_any_tcp_type_and_any_address():
    for type_ in ("host", "hostssl", "hostnossl", "hostgssenc", "hostnogssenc"):
        rules = pghba.parse_rules(_row(type_=type_))
        assert pghba.blanket_trust(rules) is not None, type_
    for address in ("all", "0.0.0.0/0", "127.0.0.0/8", "localhost", "samenet"):
        rules = pghba.parse_rules(_row(address=address, netmask=""))
        assert pghba.blanket_trust(rules) is not None, address


def test_what_is_not_a_blanket_trust():
    # A password method, a rule for one role, and the unix socket.
    assert pghba.blanket_trust(pghba.parse_rules(_row(method="scram-sha-256"))) is None
    assert pghba.blanket_trust(pghba.parse_rules(_row(users="odoo"))) is None
    assert pghba.blanket_trust(pghba.parse_rules(_row(type_="local", address="", netmask=""))) is None


def test_a_rule_the_server_could_not_parse_makes_the_file_unjudgeable():
    rules = pghba.parse_rules(_row(error="invalid connection type"))
    assert pghba.unreadable(rules) is not None


def test_the_role_is_reached_only_when_its_rule_is_the_first_that_matches():
    reached = pghba.parse_rules(
        _row(users="odoo", line=1) + "\n" + _row(method="scram-sha-256", line=2)
    )
    assert pghba.role_is_reached(reached, "odoo")

    # First-match-wins: anything matching this connection earlier decides it.
    for shadow in (_row(method="scram-sha-256", line=1), _row(line=1)):
        shadowed = pghba.parse_rules(shadow + "\n" + _row(users="odoo", line=2))
        assert not pghba.role_is_reached(shadowed, "odoo")

    # A rule for another role does not shadow it.
    other = pghba.parse_rules(
        _row(users="someone_else", method="scram-sha-256", line=1) + "\n" + _row(users="odoo", line=2)
    )
    assert pghba.role_is_reached(other, "odoo")

    # Neither does the unix socket, which is a different connection.
    local_first = pghba.parse_rules(
        _row(type_="local", address="", netmask="", method="peer", line=1)
        + "\n" + _row(users="odoo", line=2)
    )
    assert pghba.role_is_reached(local_first, "odoo")


def test_a_rule_for_a_role_named_all_is_told_apart_by_its_own_text():
    # The view reports `"all"` and `all` identically; the line does not.
    assert not pghba.role_field_is_keyword_all('host "all" "all" 127.0.0.1/32 trust')
    assert not pghba.role_field_is_keyword_all('host all "all" 127.0.0.1/32 trust')
    assert pghba.role_field_is_keyword_all("host all all 127.0.0.1/32 trust")
    assert pghba.role_field_is_keyword_all('host all all 127.0.0.1/32 trust # "quoted" comment')
    # Only the role's field decides: the server reads a quoted address as that
    # address, so the rule is the blanket trust it looks like.
    assert pghba.role_field_is_keyword_all('host all all "127.0.0.1/32" trust')
    assert pghba.role_field_is_keyword_all('host "one db" all 127.0.0.1/32 trust')
    assert pghba.role_field_is_keyword_all("  hostssl\tmydb\tall\t127.0.0.1/32\ttrust")
    assert not pghba.role_field_is_keyword_all("host all odoo 127.0.0.1/32 trust")
    assert not pghba.role_field_is_keyword_all("local all all trust")


def test_a_trust_for_every_role_on_one_database_is_still_a_blanket_trust():
    """It lets any local user connect to that database as `postgres`, and a
    superuser in one database runs programs on the host."""
    assert pghba.blanket_trust(pghba.parse_rules(_row(databases="mydb"))) is not None
    # The role field is what decides, not the database one.
    assert pghba.blanket_trust(pghba.parse_rules(_row(databases="mydb", users="odoo"))) is None


def test_roles_named_by_pattern_or_group_cannot_be_ruled_out():
    """`/regex` and `+group` reach every member without spelling `all`, and the
    view reports the field verbatim — so the answer is "unknown", not "fine"."""
    for users in ("/.*", "+everyone"):
        rules = pghba.parse_rules(_row(users=users))
        assert pghba.names_roles_by_pattern(rules) is not None, users
        # It is not a blanket trust by the literal test, which is the point.
        assert pghba.blanket_trust(rules) is None
    # A password method is not this tool's business, patterned or not.
    assert pghba.names_roles_by_pattern(pghba.parse_rules(_row(users="/.*", method="peer"))) is None
    assert pghba.names_roles_by_pattern(pghba.parse_rules(_row(users="odoo"))) is None


def test_only_a_plain_host_rule_reaches_the_role():
    """With `ssl = on`, which the supported host has, a `hostnossl` rule is never
    consulted: counting one as reached would call a host narrowed where the role
    cannot connect at all."""
    assert pghba.role_is_reached(pghba.parse_rules(_row(type_="host", users="odoo")), "odoo")
    for type_ in ("hostnossl", "hostgssenc"):
        rules = pghba.parse_rules(_row(type_=type_, users="odoo"))
        assert not pghba.role_is_reached(rules, "odoo"), type_


# --- what `system` does with the answers ------------------------------------
#
# The classification above is well covered; what was not covered is that the
# probe *consults* it. Each guard below survived both the suite and the
# server-backed verifier, which only reaches cases the rules are classified in.


def test_a_rule_naming_roles_by_group_leaves_the_state_unknown(monkeypatch):
    """`+devs` may contain `postgres`. Whether it does cannot be told from the
    view, so the answer is "unknown", never "already narrow"."""
    rules = pghba.parse_rules(
        _row(users="+devs", line=1) + "\n" + _row(users="odoo", line=2)
    )
    monkeypatch.setattr(system, "pg_hba_rules", lambda port=5432: rules)
    assert system.pg_hba_loopback_state("odoo") is None


def test_a_rule_the_server_could_not_parse_leaves_the_state_unknown(monkeypatch):
    rules = pghba.parse_rules(_row(users="odoo", error="invalid connection type"))
    monkeypatch.setattr(system, "pg_hba_rules", lambda port=5432: rules)
    assert system.pg_hba_loopback_state("odoo") is None


def test_a_blanket_trust_whose_line_cannot_be_read_is_still_a_blanket_trust(monkeypatch):
    """The line is read only to tell the keyword `all` from a role *named* `all`.
    When it cannot be read the view's answer stands: reporting a host as narrowed
    on a file this cannot open is the one mistake with a cost."""
    monkeypatch.setattr(system, "pg_hba_rules", lambda port=5432: pghba.parse_rules(_row()))
    monkeypatch.setattr(system, "read_text", lambda _path: None)
    assert system.pg_hba_loopback_state("odoo") == (True, False)


def test_a_role_named_all_is_not_a_blanket_trust(monkeypatch):
    """The view reports `"all"` exactly like the keyword, so the line decides —
    for *both* questions. The role's own rule is the one the server matches, so
    reporting it as not reached would leave `provision check` red on a host that
    is correctly configured, for ever, with apply unable to change anything.
    """
    monkeypatch.setattr(system, "pg_hba_rules", lambda port=5432: pghba.parse_rules(
        _row(users="all", line=1) + "\n" + _row(users="odoo", line=2)
    ))
    monkeypatch.setattr(
        system, "read_text",
        lambda _path: 'host all "all" 127.0.0.1/32 trust\nhost all odoo 127.0.0.1/32 trust\n',
    )
    assert system.pg_hba_loopback_state("odoo") == (False, True)


def test_a_role_field_listing_all_among_others_is_a_blanket_trust(monkeypatch):
    """PostgreSQL matches the keyword anywhere in a comma list: `all,bob` lets
    every role in. Reading only a bare `all` called such a host narrow."""
    for line in ('host all all,bob 127.0.0.1/32 trust', 'host all bob,all 127.0.0.1/32 trust'):
        monkeypatch.setattr(system, "pg_hba_rules", lambda port=5432: pghba.parse_rules(
            _row(users="all,bob", line=1)
        ))
        monkeypatch.setattr(system, "read_text", lambda _path, line=line: line + "\n")
        assert system.pg_hba_loopback_state("odoo") == (True, False), line


def test_an_unnamed_role_is_refused_before_any_query(monkeypatch):
    monkeypatch.setattr(system, "pg_hba_rules",
                        lambda port=5432: pytest.fail("a bad role name must not reach the server"))
    assert system.pg_hba_loopback_state("odoo; DROP DATABASE x --") is None


def test_the_role_rule_counts_only_when_it_covers_every_database():
    """`host acme odoo … trust` trusts the role for one database, so a connection
    to another is not reached by it."""
    assert pghba.role_is_reached(pghba.parse_rules(_row(users="odoo")), "odoo")
    assert not pghba.role_is_reached(
        pghba.parse_rules(_row(databases="acme", users="odoo")), "odoo"
    )
