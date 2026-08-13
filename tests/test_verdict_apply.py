from __future__ import annotations

import json
from pathlib import Path

from heimdall.observe_queue import GhError
from heimdall.verdict_apply import apply_verdict, parse_verdict_labels

ALLOWED = frozenset(
    {
        "verdict:pass",
        "verdict:hold",
        "verdict:reject",
        "verdict:needs-scout",
    }
)

LABELS_YML = """\
namespaces:
  - name: bifrost
    labels:
      - name: bifrost:in
  - name: verdict
    labels:
      - name: verdict:pass
      - name: verdict:hold
      - name: verdict:reject
      - name: verdict:needs-scout
  - name: work
    labels:
      - name: work:ready
"""


def _labels(*names: str) -> str:
    return json.dumps({"number": 4, "labels": [{"name": n} for n in names]})


def test_parse_verdict_labels_from_taxonomy() -> None:
    assert parse_verdict_labels(LABELS_YML) == ALLOWED


def test_parse_verdict_labels_from_repo_labels_yml() -> None:
    text = (Path(__file__).resolve().parents[1] / "labels.yml").read_text(
        encoding="utf-8"
    )
    assert parse_verdict_labels(text) == ALLOWED


def test_apply_pass_replaces_hold_on_issue() -> None:
    edits: list[list[str]] = []

    def run(args: list[str]) -> str:
        if args[:2] == ["issue", "view"]:
            return _labels("verdict:hold", "work:ready")
        if args[:2] == ["issue", "edit"]:
            edits.append(args)
            return ""
        raise AssertionError(args)

    payload = apply_verdict(
        "mikolaj92/heimdall",
        "verdict:pass",
        issue=4,
        allowed=ALLOWED,
        run=run,
    )
    assert payload == {
        "ok": True,
        "atom": "verdict-apply",
        "repo": "mikolaj92/heimdall",
        "issue": 4,
        "added": ["verdict:pass"],
        "removed": ["verdict:hold"],
    }
    assert edits == [
        [
            "issue",
            "edit",
            "4",
            "-R",
            "mikolaj92/heimdall",
            "--add-label",
            "verdict:pass",
            "--remove-label",
            "verdict:hold",
        ]
    ]


def test_apply_hold_on_pr_uses_pr_commands() -> None:
    edits: list[list[str]] = []

    def run(args: list[str]) -> str:
        if args[:1] == ["api"]:
            raise AssertionError("must not fetch mill catalog")
        if args[:2] == ["pr", "view"]:
            return _labels("verdict:pass", "bifrost:out")
        if args[:2] == ["pr", "edit"]:
            edits.append(args)
            return ""
        raise AssertionError(args)

    payload = apply_verdict(
        "mikolaj92/lokay",
        "verdict:hold",
        pr=9,
        allowed=ALLOWED,
        run=run,
    )
    assert payload["ok"] is True
    assert payload["atom"] == "verdict-apply"
    assert payload["pr"] == 9
    assert "issue" not in payload
    assert payload["added"] == ["verdict:hold"]
    assert payload["removed"] == ["verdict:pass"]
    assert edits == [
        [
            "pr",
            "edit",
            "9",
            "-R",
            "mikolaj92/lokay",
            "--add-label",
            "verdict:hold",
            "--remove-label",
            "verdict:pass",
        ]
    ]


def test_idempotent_when_chosen_verdict_already_only() -> None:
    edits: list[list[str]] = []

    def run(args: list[str]) -> str:
        if args[:2] == ["issue", "view"]:
            return _labels("verdict:pass", "pri:p2")
        if args[:2] == ["issue", "edit"]:
            edits.append(args)
            return ""
        raise AssertionError(args)

    payload = apply_verdict(
        "mikolaj92/heimdall",
        "verdict:pass",
        issue=4,
        allowed=ALLOWED,
        run=run,
    )
    assert payload["ok"] is True
    assert payload["added"] == []
    assert payload["removed"] == []
    assert edits == []


def test_removes_other_taxonomy_verdicts_only() -> None:
    edits: list[list[str]] = []

    def run(args: list[str]) -> str:
        if args[:2] == ["issue", "view"]:
            return _labels(
                "verdict:hold",
                "verdict:reject",
                "verdict:custom",
                "work:ready",
            )
        if args[:2] == ["issue", "edit"]:
            edits.append(args)
            return ""
        raise AssertionError(args)

    payload = apply_verdict(
        "mikolaj92/heimdall",
        "verdict:pass",
        issue=4,
        allowed=ALLOWED,
        run=run,
    )
    assert payload["ok"] is True
    assert payload["added"] == ["verdict:pass"]
    assert payload["removed"] == ["verdict:hold", "verdict:reject"]
    assert "--remove-label" in edits[0]
    assert "verdict:custom" not in edits[0]
    assert "work:ready" not in edits[0]


def test_unknown_verdict_fails_closed() -> None:
    def run(args: list[str]) -> str:
        raise AssertionError(f"must not call gh: {args}")

    payload = apply_verdict(
        "mikolaj92/heimdall",
        "verdict:ship-it",
        issue=4,
        allowed=ALLOWED,
        run=run,
    )
    assert payload["ok"] is False
    assert payload["atom"] == "verdict-apply"
    assert payload["error"] == "unknown verdict: verdict:ship-it"
    assert payload["repo"] == "mikolaj92/heimdall"
    assert payload["issue"] == 4
    assert payload["added"] == []
    assert payload["removed"] == []


def test_missing_target_fails_closed() -> None:
    def run(args: list[str]) -> str:
        raise AssertionError(args)

    payload = apply_verdict(
        "mikolaj92/heimdall",
        "verdict:pass",
        allowed=ALLOWED,
        run=run,
    )
    assert payload["ok"] is False
    assert payload["error"] == "missing --issue or --pr"


def test_both_targets_fail_closed() -> None:
    def run(args: list[str]) -> str:
        raise AssertionError(args)

    payload = apply_verdict(
        "mikolaj92/heimdall",
        "verdict:pass",
        issue=1,
        pr=2,
        allowed=ALLOWED,
        run=run,
    )
    assert payload["ok"] is False
    assert payload["error"] == "use --issue or --pr, not both"


def test_view_error_fails_closed() -> None:
    def run(args: list[str]) -> str:
        raise GhError("Could not resolve to an issue")

    payload = apply_verdict(
        "mikolaj92/heimdall",
        "verdict:pass",
        issue=4,
        allowed=ALLOWED,
        run=run,
    )
    assert payload["ok"] is False
    assert payload["error"] == "Could not resolve to an issue"
    assert payload["added"] == []
    assert payload["removed"] == []


def test_edit_error_fails_closed() -> None:
    def run(args: list[str]) -> str:
        if args[:2] == ["issue", "view"]:
            return _labels("verdict:hold")
        raise GhError("HTTP 422: Validation Failed")

    payload = apply_verdict(
        "mikolaj92/heimdall",
        "verdict:pass",
        issue=4,
        allowed=ALLOWED,
        run=run,
    )
    assert payload["ok"] is False
    assert payload["error"] == "HTTP 422: Validation Failed"


def test_comment_after_apply() -> None:
    calls: list[list[str]] = []

    def run(args: list[str]) -> str:
        calls.append(args)
        if args[:2] == ["issue", "view"]:
            return _labels("verdict:hold")
        if args[:2] == ["issue", "edit"]:
            return ""
        if args[:2] == ["issue", "comment"]:
            return ""
        raise AssertionError(args)

    payload = apply_verdict(
        "mikolaj92/heimdall",
        "verdict:pass",
        issue=4,
        comment="QA pass",
        allowed=ALLOWED,
        run=run,
    )
    assert payload["ok"] is True
    assert payload["added"] == ["verdict:pass"]
    assert ["issue", "comment", "4", "-R", "mikolaj92/heimdall", "--body", "QA pass"] in calls
    assert calls[0][:2] == ["issue", "view"]
    assert calls[1][:2] == ["issue", "edit"]
    assert calls[2][:2] == ["issue", "comment"]


def test_comment_error_fails_closed() -> None:
    def run(args: list[str]) -> str:
        if args[:2] == ["issue", "view"]:
            return _labels("verdict:hold")
        if args[:2] == ["issue", "edit"]:
            return ""
        raise GhError("comment failed")

    payload = apply_verdict(
        "mikolaj92/heimdall",
        "verdict:reject",
        issue=4,
        comment="out of scope",
        allowed=ALLOWED,
        run=run,
    )
    assert payload["ok"] is False
    assert payload["error"] == "comment failed"
    assert payload["added"] == ["verdict:reject"]
    assert payload["removed"] == ["verdict:hold"]


def test_labels_yml_error_fails_closed() -> None:
    def run(args: list[str]) -> str:
        raise AssertionError(args)

    payload = apply_verdict(
        "mikolaj92/heimdall",
        "verdict:pass",
        issue=4,
        labels_yml=Path("/no/such/labels.yml"),
        run=run,
    )
    assert payload["ok"] is False
    assert "labels.yml" in payload["error"]


def test_fala_package_does_not_include_verdict_apply() -> None:
    text = (Path(__file__).resolve().parents[1] / "fala-package.toml").read_text(
        encoding="utf-8"
    )
    assert "verdict-apply" not in text
    assert "verdict_apply" not in text
    assert 'id = "monitor"' in text
    assert 'command = ["uv", "run", "observe-queue"]' in text
