from __future__ import annotations

from pathlib import Path

from heimdall.craft_inbound import craft_from_text, craft_inbound, issue_body
from heimdall.observe_queue import HEIMDALL, GhError


def _spec(**overrides: object) -> dict:
    data: dict = {
        "title": "Feedback from Influenzer",
        "signal": "signal:feedback",
        "source": "source:github",
        "summary": "User says the post was too long.",
        "fit": "In scope for influenzer copy; not engineering.",
    }
    data.update(overrides)
    return data


def test_missing_field_fails() -> None:
    calls: list[list[str]] = []

    def run(args: list[str]) -> str:
        calls.append(args)
        raise AssertionError("must not call gh when a field is missing")

    spec = _spec()
    del spec["fit"]
    payload = craft_inbound(spec, run=run)
    assert payload["ok"] is False
    assert payload["atom"] == "craft-inbound"
    assert "fit" in payload["error"]
    assert calls == []

    empty = _spec(summary="  ")
    payload = craft_inbound(empty, run=run)
    assert payload["ok"] is False
    assert "summary" in payload["error"]
    assert calls == []


def test_refuses_work_ready() -> None:
    calls: list[list[str]] = []

    def run(args: list[str]) -> str:
        calls.append(args)
        raise AssertionError("must not file work:ready")

    payload = craft_inbound(_spec(work="work:ready"), run=run)
    assert payload["ok"] is False
    assert payload["atom"] == "craft-inbound"
    assert "work:ready" in payload["error"]
    assert calls == []

    payload = craft_inbound(_spec(labels=["work:ready"]), run=run)
    assert payload["ok"] is False
    assert "work:ready" in payload["error"]
    assert calls == []

    creates: list[list[str]] = []

    def create(args: list[str]) -> str:
        if args[:1] == ["api"]:
            raise AssertionError("must not fetch mill catalog")
        if args[:2] == ["issue", "create"]:
            creates.append(args)
            return "https://github.com/mikolaj92/lokay/issues/3\n"
        raise AssertionError(args)

    payload = craft_inbound(_spec(repo="mikolaj92/lokay"), run=create)
    assert payload["ok"] is True
    assert "work:ready" not in payload["labels"]
    assert "ai:ready" not in payload["labels"]
    assert "work:ready" not in creates[0]
    assert "ai:ready" not in creates[0]


def test_heimdall_default_repo() -> None:
    creates: list[list[str]] = []

    def run(args: list[str]) -> str:
        if args[:1] == ["api"]:
            raise AssertionError("must not fetch mill catalog")
        if args[:2] == ["issue", "create"]:
            creates.append(args)
            return "https://github.com/mikolaj92/heimdall/issues/11\n"
        raise AssertionError(args)

    payload = craft_inbound(_spec(), run=run)
    assert payload["ok"] is True
    assert payload["atom"] == "craft-inbound"
    assert payload["repo"] == HEIMDALL
    assert payload["issue"] == 11
    assert payload["url"] == "https://github.com/mikolaj92/heimdall/issues/11"
    assert payload["labels"] == [
        "bifrost:in",
        "source:github",
        "signal:feedback",
        "verdict:hold",
    ]
    assert "work:ready" not in payload["labels"]
    assert "ai:ready" not in payload["labels"]
    assert creates[0][creates[0].index("-R") + 1] == HEIMDALL
    assert "verdict:hold" in creates[0]
    assert "bifrost:in" in creates[0]
    body = creates[0][creates[0].index("--body") + 1]
    assert "### Source" in body
    assert "### Signal kind" in body
    assert "### Signal" in body
    assert "### Fit check" in body
    assert "### Proposed verdict" in body


def test_unknown_signal_fails_closed() -> None:
    calls: list[list[str]] = []

    def run(args: list[str]) -> str:
        calls.append(args)
        raise AssertionError("must not call gh on unknown signal")

    payload = craft_inbound(_spec(signal="signal:ship-it"), run=run)
    assert payload["ok"] is False
    assert payload["atom"] == "craft-inbound"
    assert payload["error"] == "unknown signal: signal:ship-it"
    assert calls == []


def test_gh_error_fail_closed() -> None:
    creates: list[list[str]] = []

    def run(args: list[str]) -> str:
        if args[:2] == ["issue", "create"]:
            creates.append(args)
            raise GhError("HTTP 422: Validation Failed")
        raise AssertionError(args)

    payload = craft_inbound(_spec(), run=run)
    assert payload["ok"] is False
    assert payload["atom"] == "craft-inbound"
    assert payload["error"] == "HTTP 422: Validation Failed"
    assert payload["repo"] == HEIMDALL
    assert "issue" not in payload
    assert "url" not in payload
    assert creates


def test_issue_body_matches_inbound_headings() -> None:
    body = issue_body(_spec(proposed_verdict="verdict:reject"))
    for heading in (
        "### Source",
        "### Signal kind",
        "### Signal",
        "### Fit check",
        "### Proposed verdict",
    ):
        assert heading in body
    assert "source:github" in body
    assert "signal:feedback" in body
    assert "verdict:reject" in body


def test_craft_from_text_invalid_json() -> None:
    payload = craft_from_text("not-json")
    assert payload["ok"] is False
    assert "invalid json" in payload["error"]


def test_fala_package_does_not_include_craft_inbound() -> None:
    text = (Path(__file__).resolve().parents[1] / "fala-package.toml").read_text(
        encoding="utf-8"
    )
    assert "craft-inbound" not in text
    assert "craft_inbound" not in text
    assert 'id = "monitor"' in text
    assert 'command = ["uv", "run", "observe-queue"]' in text
