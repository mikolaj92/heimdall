from __future__ import annotations

from pathlib import Path

from heimdall.auto_label_issue import Plan, main, plan_labels, self_test
from heimdall.sync_labels import taxonomy_names

REPO_LABELS = Path(__file__).resolve().parents[1] / "labels.yml"


def test_self_test() -> None:
    self_test()


def test_self_test_cli(capsys) -> None:
    assert main(["--self-test"]) == 0
    assert "ok: self-test" in capsys.readouterr().out


def test_inbound_never_applies_work_ready() -> None:
    allowed = taxonomy_names(REPO_LABELS)
    body = (
        "### Source\n\nsource:github\n\n"
        "### Signal kind\n\nsignal:bug\n\n"
        "### Proposed verdict\n\nverdict:pass\n"
    )
    plan = plan_labels(body, {"bifrost:in", "verdict:hold"}, allowed)
    assert "work:ready" not in plan.add
    assert plan.add == frozenset({"source:github", "signal:bug", "verdict:pass"})
    assert plan.remove == frozenset({"verdict:hold"})


def test_work_ready_form_swaps_pri_only() -> None:
    allowed = taxonomy_names(REPO_LABELS)
    body = (
        "### Problem\n\nMissing auto-label.\n\n"
        "### Priority\n\npri:p0\n"
    )
    plan = plan_labels(body, {"work:ready", "pri:p2", "bifrost:in"}, allowed)
    assert plan == Plan(frozenset({"pri:p0"}), frozenset({"pri:p2"}))
    assert "work:ready" not in plan.remove


def test_unknown_dropdown_is_noop() -> None:
    allowed = taxonomy_names(REPO_LABELS)
    body = (
        "### Source\n\nsource:email\n\n"
        "### Signal kind\n\nbug\n"
    )
    plan = plan_labels(body, {"bifrost:in", "verdict:hold"}, allowed)
    assert plan == Plan(frozenset(), frozenset())
