"""Reading back what a migration run left: the driver's step log, each step's
Odoo log, and the outbound firewall's journal."""

from __future__ import annotations

from odoo_dwg import runlog

STEPS = "\n".join([
    "2026-09-20T11:32:51+02:00\ta1b2\t-\trun-start\t12.0 -> 14.0",
    "2026-09-20T11:32:52+02:00\ta1b2\t-\trestore\t00_source",
    "2026-09-20T11:32:55+02:00\ta1b2\t13.0\tstart\t",
    "2026-09-20T11:41:02+02:00\ta1b2\t13.0\tok\t",
    "2026-09-20T11:41:05+02:00\ta1b2\t14.0\tstart\t",
    "2026-09-20T11:49:00+02:00\ta1b2\t14.0\tfail\t1",
    "2026-09-20T12:00:00+02:00\tc3d4\t-\trun-start\t12.0 -> 14.0",
    "2026-09-20T12:00:01+02:00\tc3d4\t13.0\tskip\t",
    "2026-09-20T12:10:00+02:00\tc3d4\t14.0\tstart\t",
])


def test_runs_are_read_back_with_each_step_s_outcome_and_window():
    history = runlog.runs(runlog.parse_steps(STEPS))
    assert [run.run for run in history] == ["a1b2", "c3d4"]

    failed = history[0]
    assert failed.chain == "12.0 -> 14.0" and failed.outcome == "fail"
    assert failed.restored == ["00_source"]
    step = failed.step("14.0")
    assert (step.outcome, step.code) == ("fail", "1")
    # The window is what the journal is asked for, so it must be the step's own.
    assert step.window == ("2026-09-20T11:41:05+02:00", "2026-09-20T11:49:00+02:00")

    # A run still going: a skipped step ran nothing, and the last has no end.
    current = history[1]
    assert current.outcome == "unfinished"
    assert current.step("13.0").outcome == "skip"
    assert current.step("14.0").window == ("2026-09-20T12:10:00+02:00", "")


def test_a_half_written_line_is_skipped_rather_than_guessed_at():
    """The file is appended to by a shell script that may be killed mid-write."""
    events = runlog.parse_steps(STEPS + "\n2026-09-20T12:11:00+02:00\tc3d4")
    assert len(events) == len(STEPS.splitlines())
    assert runlog.parse_steps("") == []


def test_a_log_is_summarised_by_what_its_lines_carry_not_by_meaning():
    """Odoo states its line shape once, in `odoo/netsvc.py`, and it is the same
    from 13.0 to 19.0. Level, logger and count are facts the line carries;
    naming categories would assert something about OpenUpgrade we have not
    verified."""
    log = "\n".join([
        "2026-09-20 11:41:00,123 999 WARNING acme odoo.modules.loading: field removed",
        "2026-09-20 11:41:00,124 999 WARNING acme odoo.modules.loading: field removed",
        "2026-09-20 11:41:01,000 999 ERROR acme odoo.modules.registry: could not load",
        "2026-09-20 11:41:02,000 999 INFO acme odoo.service: the running commentary",
        "a line that is not Odoo's at all",
    ])
    entries = runlog.summarise_log(log)
    # Worst level first, and the repeated warning counted once — one broken
    # field can emit the same line per record, and ten thousand copies of it
    # hide everything else.
    assert [(e.level, e.count) for e in entries] == [("ERROR", 1), ("WARNING", 2)]
    assert entries[1].logger == "odoo.modules.loading"
    assert all(e.level != "INFO" for e in entries)


def test_the_firewall_s_answers_are_read_for_the_step_s_own_process():
    """`ARG1` is the decision and `ARG2` the rule that made it. Filtering by
    process is what makes it *the migration's* reach and not the host's."""
    journal = "\n".join([
        'h opensnitch[1]: CONNECTION - [DSTHOST="pypi.org" ARG1="reject" '
        'ARG2="00-odwg-003-reject-odoo-external" CMDLINE="odoo-bin -c x" PATH="/x/odoo-bin"]',
        'h opensnitch[1]: CONNECTION - [DSTHOST="pypi.org" ARG1="reject" '
        'ARG2="00-odwg-003-reject-odoo-external" CMDLINE="odoo-bin -c x" PATH="/x/odoo-bin"]',
        'h opensnitch[1]: CONNECTION - [DSTHOST="github.com" ARG1="allow" '
        'ARG2="00-odwg-020" CMDLINE="claude" PATH="/y/claude"]',
    ])
    everything = runlog.summarise_decisions(journal)
    assert len(everything) == 2
    # Refusals first: with the firewall on, odoo-bin is rejected off localhost,
    # so a rejection is the half worth reading.
    assert everything[0].action == "reject" and everything[0].count == 2

    mine = runlog.summarise_decisions(journal, process="odoo-bin")
    assert [(d.action, d.host, d.count) for d in mine] == [("reject", "pypi.org", 2)]
    assert mine[0].rule == "00-odwg-003-reject-odoo-external"


def test_the_live_view_shows_where_the_chain_is_including_what_has_not_run():
    """A step the run has not reached is shown as pending: what has not happened
    yet is part of knowing where a chain is."""
    history = runlog.runs(runlog.parse_steps("\n".join([
        "2026-09-20T11:00:00+02:00\ta1\t-\trun-start\t12.0 -> 15.0",
        "2026-09-20T11:00:01+02:00\ta1\t13.0\tstart\t",
        "2026-09-20T11:08:08+02:00\ta1\t13.0\tok\t",
        "2026-09-20T11:08:09+02:00\ta1\t14.0\tstart\t",
    ])))
    rows = runlog.live_view(history[-1], ["13.0", "14.0", "15.0"], "2026-09-20T11:11:21+02:00")

    assert [(r.version, r.state) for r in rows] == [
        ("13.0", "ok"), ("14.0", "running"), ("15.0", "pending"),
    ]
    # A finished step is timed by its own two instants; a running one against now.
    assert rows[0].elapsed == "8m 07s"
    assert rows[1].elapsed == "3m 12s"
    assert rows[2].elapsed == ""
    # And the log a watcher should be reading is the running step's.
    assert runlog.current_step(rows) == "14.0"


def test_the_live_view_has_no_clock_of_its_own():
    """`now` is injected: a view that asks the clock cannot be tested against a
    fixed instant, and a run's own timestamps are what it must be read against."""
    rows = runlog.live_view(None, ["13.0"], "2026-09-20T11:00:00+02:00")
    assert [(r.version, r.state, r.elapsed) for r in rows] == [("13.0", "pending", "")]
    # An unparseable instant is not worth a guess.
    history = runlog.runs(runlog.parse_steps("whenever\ta1\t13.0\tstart\t"))
    assert runlog.live_view(history[-1], ["13.0"], "2026-09-20T11:00:00+02:00")[0].elapsed == ""


def test_a_step_log_is_read_for_the_run_that_wrote_it():
    """A step's log is appended to, never rotated. A 12 -> 19 chain re-run after
    a failure had three attempts in one file, and the report led with "Failed to
    initialize database" about an attempt already superseded.
    """
    text = (
        "2026-09-20 17:58:46,024 1 ERROR db odoo.modules.registry: Failed to load registry\n"
        "2026-09-20 18:02:15,614 2 ERROR db odoo.modules.loading: inconsistent states\n"
    )
    # The window is local time with an offset; Odoo writes UTC, because it forces
    # TZ=UTC on its own process.
    window = ("2026-09-20T20:01:28+02:00", "2026-09-20T20:02:41+02:00")
    inside = runlog.summarise_log(text, window=window)
    assert [entry.first for entry in inside] == ["inconsistent states"]
    # With no window, the whole file — which is what produced the wrong lead.
    assert len(runlog.summarise_log(text)) == 2


def test_a_window_that_cannot_be_read_keeps_every_line():
    text = "2026-09-20 18:02:15,614 2 ERROR db odoo.x: boom\n"
    assert len(runlog.summarise_log(text, window=("", ""))) == 1
    assert len(runlog.summarise_log(text, window=("not a time", ""))) == 1
