from __future__ import annotations

from pathlib import Path

from heimdall.advance_work_labels import (
    FROM_DONE,
    FROM_DOING,
    Plan,
    WORK_DONE,
    WORK_DOING,
    WORK_READY,
    closing_issue_numbers,
    main,
    mode_from_event,
    plan_work,
    self_test,
)
from heimdall.sync_labels import taxonomy_names

REPO_LABELS = Path(__file__).resolve().parents[1] / "labels.yml"
REPO = "mikolaj92/heimdall"


def test_self_test() -> None:
    self_test()


def test_self_test_cli(capsys) -> None:
    assert main(["--self-test"]) == 0
    assert "ok: self-test" in capsys.readouterr().out


def test_closes_n_on_merge_moves_ready_to_done() -> None:
    allowed = taxonomy_names(REPO_LABELS)
    assert closing_issue_numbers("Closes #4", REPO) == {4}
    plan = plan_work(
        {WORK_READY, "pri:p2", "bifrost:in"},
        allowed,
        WORK_DONE,
        FROM_DONE,
    )
    assert plan == Plan(frozenset({WORK_DONE}), frozenset({WORK_READY}))


def test_work_blocked_and_no_work_are_left_alone() -> None:
    allowed = taxonomy_names(REPO_LABELS)
    assert plan_work({"work:blocked", "pri:p2"}, allowed, WORK_DONE, FROM_DONE) is None
    assert plan_work({"bifrost:in", "verdict:hold"}, allowed, WORK_DONE, FROM_DONE) is None
    assert plan_work({WORK_DONE, "pri:p2"}, allowed, WORK_DOING, FROM_DOING) is None


def test_mode_from_event() -> None:
    assert mode_from_event("closed", True) == "done"
    assert mode_from_event("closed", False) is None
    assert mode_from_event("opened", False) == "doing"
