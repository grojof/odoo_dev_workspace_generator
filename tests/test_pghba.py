"""The rules PostgreSQL reports, and the two questions asked of them.

Pure: every case here is the output `pg_hba_file_rules` gives for a file shape,
taken from a real PostgreSQL 16 (see the change's design.md). The query itself
lives in `system` and is exercised by `tools/verify_pg_hba_trust.py`.
"""

from __future__ import annotations

from odoo_dwg import pghba

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
