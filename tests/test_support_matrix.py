"""The support matrix is the project's authority on what it supports, so these
tests guard its shape and its lookups — not the specific bounds, which
``tools/verify_support_matrix.py`` checks against the official sources."""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

import pytest

from odoo_dwg.models import (
    DERIVED,
    EVIDENCE_TIERS,
    HOST_PYTHON,
    ODOO_SUPPORT,
    OFFICIAL,
    SUPPORTED_HOSTS,
    TOOL_PYTHON_MINIMUM,
    UNTESTED,
    UV_PYTHON,
    odoo_docs_url,
    postgres_floor_for,
    postgres_minimum_for,
    python_in_range,
    python_maximum_for,
    python_minimum_for,
    python_tuple,
    resolve_interpreter,
    supported_host,
    version_support,
    version_support_or_none,
)

PYPROJECT = Path(__file__).resolve().parent.parent / "pyproject.toml"


def test_every_supported_version_has_a_complete_row():
    assert sorted(ODOO_SUPPORT) == [12, 13, 14, 15, 16, 17, 18, 19]
    for major, support in ODOO_SUPPORT.items():
        assert support.major == major
        assert support.python_min.value, f"Odoo {major} has no Python floor"
        assert support.postgres_min.tier in EVIDENCE_TIERS
        assert support.python_max.tier in EVIDENCE_TIERS
        # Every version runs on a uv-provided interpreter, so every row
        # recommends one.
        assert support.acquisition == "uv"
        assert support.is_native and support.recommended_python


def test_recommended_interpreter_is_inside_the_declared_range():
    for support in ODOO_SUPPORT.values():
        if support.recommended_python:
            assert support.python_in_range(support.recommended_python), (
                f"Odoo {support.version} recommends {support.recommended_python}, "
                f"outside {support.python_range_text()}"
            )


def test_odoo_19_is_the_only_officially_stated_python_maximum():
    official = {
        support.version
        for support in ODOO_SUPPORT.values()
        if support.python_max.value and support.python_max.is_official
    }
    assert official == {"19.0"}
    assert version_support("19.0").python_max.value == "3.14"


def test_untested_maxima_carry_no_value_and_say_so():
    for major in (12, 13):
        bound = ODOO_SUPPORT[major].python_max
        assert bound.value is None
        assert bound.tier == UNTESTED
        assert "not stated" in bound.describe()


def test_a_derived_bound_is_never_described_as_official():
    bound = version_support("18.0").python_max
    assert bound.tier == DERIVED
    described = bound.describe()
    assert described.startswith("3.14")
    assert DERIVED in described and "requirements.txt" in described
    # An official bound needs no qualifier.
    assert version_support("18.0").python_min.describe() == "3.10"
    assert version_support("18.0").python_min.tier == OFFICIAL


def test_unsupported_version_is_rejected_not_guessed():
    with pytest.raises(ValueError, match="Unsupported Odoo version"):
        version_support("20.0")
    assert version_support_or_none("20.0") is None


def test_python_range_checks():
    # Below the floor.
    assert not python_in_range("18.0", "3.9")
    # Inside.
    assert python_in_range("18.0", "3.12")
    # Above a derived maximum: Odoo 14 tops out at Jammy's 3.10.
    assert not python_in_range("14.0", "3.12")
    # Inside a derived maximum: Odoo 15 does target Noble's 3.12.
    assert python_in_range("15.0", "3.12")
    # An unstated maximum bounds nothing above the floor.
    assert python_in_range("12.0", "3.8")
    assert not python_in_range("12.0", "3.4")


def test_python_tuple_compares_numerically():
    assert python_tuple("3.9") < python_tuple("3.10")
    assert python_tuple("3.10") == (3, 10)
    with pytest.raises(ValueError):
        python_tuple("3.x")


def test_minimum_and_maximum_lookups():
    assert python_minimum_for("12.0") == "3.5"
    assert python_minimum_for("19.0") == "3.10"
    assert python_maximum_for("16.0") == "3.13"
    assert python_maximum_for("13.0") is None


def test_postgres_floors():
    assert postgres_minimum_for("18.0") == "12.0"
    # Odoo 19 raised the floor from 12 to 13.
    assert postgres_minimum_for("19.0") == "13.0"
    assert postgres_minimum_for("12.0") is None
    # A shared server must satisfy the strictest version in play. With a tie,
    # any of the tied versions names the floor equally well.
    floor, version = postgres_floor_for(["17.0", "18.0"])
    assert floor == "12.0" and version in {"17.0", "18.0"}
    assert postgres_floor_for(["17.0", "19.0"]) == ("13.0", "19.0")
    assert postgres_floor_for(["12.0", "13.0"]) is None


def test_docs_url_follows_the_layout_of_each_era():
    assert odoo_docs_url("12.0").endswith("/12.0/setup/install.html")
    assert odoo_docs_url("14.0").endswith("/14.0/administration/install/source.html")
    assert odoo_docs_url("19.0").endswith("/19.0/administration/on_premise/source.html")


def test_the_only_supported_host_is_the_reference_box():
    assert [host.version_id for host in SUPPORTED_HOSTS] == ["24.04"]
    assert SUPPORTED_HOSTS[0].reference
    assert supported_host("Ubuntu", "24.04").codename == "noble"
    assert supported_host("ubuntu", "24.04").system_python == "3.12"
    # Declared-but-never-run hosts were dropped rather than implied.
    assert supported_host("ubuntu", "22.04") is None
    assert supported_host("debian", "12") is None


def test_tool_python_floor_matches_pyproject():
    declared = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))["project"]["requires-python"]
    assert declared == f">={TOOL_PYTHON_MINIMUM}"
    # And it is the supported host's system Python.
    assert TOOL_PYTHON_MINIMUM == SUPPORTED_HOSTS[0].system_python


# --- interpreter resolution ------------------------------------------------


def test_in_range_host_interpreter_is_kept():
    choice = resolve_interpreter("18.0", host_python="3.12")
    assert (choice.python, choice.source) == ("3.12", HOST_PYTHON)
    assert not choice.out_of_range and choice.crossed is None
    assert not choice.needs_uv


def test_host_above_the_maximum_falls_back_to_the_recommendation():
    # Odoo 14 tops out at 3.10; a 24.04 host runs 3.12.
    choice = resolve_interpreter("14.0", host_python="3.12")
    assert (choice.python, choice.source) == ("3.8", UV_PYTHON)
    assert choice.needs_uv
    # The recommendation itself is in range, so nothing is flagged.
    assert not choice.out_of_range


def test_an_unstated_maximum_does_not_make_a_newer_host_the_default():
    # Odoo 12/13 declare no ceiling, but their gevent does not build on 3.12:
    # the recommendation is the default, and the host still counts as in range.
    for version in ("12.0", "13.0"):
        choice = resolve_interpreter(version, host_python="3.12")
        assert (choice.python, choice.source) == ("3.8", UV_PYTHON)
        assert not choice.out_of_range
    # A host at or below the recommendation is still used as-is.
    assert resolve_interpreter("13.0", host_python="3.8").source == HOST_PYTHON
    # And the operator can still choose the host explicitly.
    pinned = resolve_interpreter("13.0", host_python="3.12", operator_choice="3.12")
    assert (pinned.python, pinned.source) == ("3.12", HOST_PYTHON)


def test_host_below_the_minimum_falls_back_to_the_recommendation():
    # A host interpreter below Odoo 19's 3.10 floor falls back to the recommendation.
    choice = resolve_interpreter("19.0", host_python="3.9")
    assert (choice.python, choice.source) == ("3.12", UV_PYTHON)


def test_operator_override_wins_and_is_marked_uv_when_it_is_not_the_host_python():
    choice = resolve_interpreter("16.0", host_python="3.12", operator_choice="3.11")
    assert (choice.python, choice.source) == ("3.11", UV_PYTHON)
    assert not choice.out_of_range


def test_operator_override_equal_to_the_host_python_stays_on_the_host():
    choice = resolve_interpreter("15.0", host_python="3.12", operator_choice="3.12")
    assert (choice.python, choice.source) == ("3.12", HOST_PYTHON)


def test_out_of_range_override_is_reported_with_the_bound_it_crosses():
    choice = resolve_interpreter("14.0", host_python="3.12", operator_choice="3.12")
    assert choice.out_of_range
    assert choice.crossed is not None
    assert choice.crossed.value == "3.10"
    assert choice.crossed.tier == DERIVED
    assert "outside the supported range" in choice.describe()
    # Below the floor is crossed just as visibly.
    low = resolve_interpreter("19.0", operator_choice="3.9")
    assert low.out_of_range and low.crossed.value == "3.10"


def test_the_legacy_versions_resolve_to_a_uv_interpreter():
    # Odoo 13 used to run in a container; it now resolves like any other step.
    # Migration never offers the host interpreter, so it asks without one.
    choice = resolve_interpreter("13.0")
    assert (choice.python, choice.source) == ("3.8", UV_PYTHON)
    assert choice.needs_uv
    # And it can be pinned, which a container-backed step could not be.
    assert resolve_interpreter("13.0", operator_choice="3.9").python == "3.9"


# --- the docs must not drift from the declared matrix ----------------------

SUPPORT_DOC = Path(__file__).resolve().parent.parent / "docs" / "reference" / "support-matrix.md"


def _doc_version_rows() -> dict[str, list[str]]:
    """Parse the version table of docs/reference/support-matrix.md into {version: cells}."""
    rows: dict[str, list[str]] = {}
    for line in SUPPORT_DOC.read_text(encoding="utf-8").splitlines():
        if not line.startswith("| 1"):
            continue
        cells = [cell.strip().strip("*").strip() for cell in line.strip("|").split("|")]
        if re.fullmatch(r"\d+\.0", cells[0]):
            rows.setdefault(cells[0], cells)
    return rows


def test_support_doc_table_matches_the_declared_matrix():
    rows = _doc_version_rows()
    assert set(rows) == {support.version for support in ODOO_SUPPORT.values()}
    for version, cells in rows.items():
        support = version_support(version)
        py_min, min_tier, py_max, max_tier, recommended, pg_min, pg_tier = cells[1:8]
        # "official¹" carries a footnote marker; compare the tier name only.
        assert min_tier.rstrip("¹") == support.python_min.tier
        assert py_min.rstrip("¹") == support.python_min.value
        assert max_tier == support.python_max.tier
        assert py_max == (support.python_max.value or "—")
        assert pg_tier == support.postgres_min.tier
        assert pg_min == (support.postgres_min.value or "—")
        expected_recommended = support.recommended_python or "Docker image"
        assert recommended == expected_recommended


def test_support_doc_states_the_tool_python_floor():
    text = SUPPORT_DOC.read_text(encoding="utf-8")
    assert f"Python floor is {TOOL_PYTHON_MINIMUM}" in text
    for host in SUPPORTED_HOSTS:
        assert host.name in text
        assert host.codename in text


# --- reading back an existing venv ------------------------------------------

from odoo_dwg.models import interpreter_from_pyvenv  # noqa: E402

UV_PYVENV = """home = /home/u/.local/share/uv/python/cpython-3.8-linux-x86_64-gnu/bin
implementation = CPython
uv = 0.12.15
version_info = 3.8
include-system-site-packages = false
seed = true
"""
STDLIB_PYVENV = """home = /usr/bin
include-system-site-packages = false
version = 3.12.3
executable = /usr/bin/python3.12
"""


def test_pyvenv_of_a_uv_venv():
    choice = interpreter_from_pyvenv("14.0", UV_PYVENV)
    assert (choice.python, choice.source) == ("3.8", UV_PYTHON)
    assert not choice.out_of_range


def test_pyvenv_of_a_stdlib_venv():
    choice = interpreter_from_pyvenv("15.0", STDLIB_PYVENV)
    assert (choice.python, choice.source) == ("3.12", HOST_PYTHON)
    # Read back as it is, even when it is outside the range: it is what exists.
    assert interpreter_from_pyvenv("14.0", STDLIB_PYVENV).out_of_range


def test_unreadable_pyvenv():
    assert interpreter_from_pyvenv("18.0", "home = /usr/bin\n") is None
