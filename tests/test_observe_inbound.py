from __future__ import annotations

import json
from pathlib import Path

import pytest

from heimdall.observe_inbound import (
    keep_inbound,
    main,
    observe_inbound,
    why_inbound,
)
from heimdall.observe_queue import HEIMDALL, GhError


def _issue(number: int, title: str, labels: list[str]) -> dict:
    return {
        "number": number,
        "title": title,
        "labels": [{"name": n} for n in labels],
        "url": f"https://github.com/example/repo/issues/{number}",
    }


def test_keep_inbound_in_without_ready_or_out() -> None:
    assert keep_inbound(["bifrost:in"])
    assert keep_inbound(["bifrost:in", "verdict:hold"])
    assert keep_inbound(["bifrost:in", "verdict:pass"])
    assert keep_inbound(["bifrost:in", "signal:feedback"])


def test_keep_inbound_ready_or_out_dropped() -> None:
    assert not keep_inbound(["bifrost:in", "work:ready"])
    assert not keep_inbound(["bifrost:in", "work:ready", "pri:p2"])
    assert not keep_inbound(["bifrost:in", "bifrost:out"])
    assert not keep_inbound(["bifrost:in", "bifrost:out", "verdict:pass"])
    assert not keep_inbound(["work:ready"])
    assert not keep_inbound(["work:ready", "pri:p2"])
    assert not keep_inbound(["bifrost:out"])
    assert not keep_inbound([])


def test_why_inbound_always_inbound_plus_verdicts() -> None:
    assert why_inbound(["bifrost:in"]) == ["inbound"]
    assert why_inbound(["bifrost:in", "verdict:hold"]) == ["inbound", "hold"]
    assert why_inbound(["bifrost:in", "verdict:pass"]) == ["inbound", "pass"]
    assert why_inbound(["bifrost:in", "verdict:hold", "verdict:pass"]) == [
        "inbound",
        "hold",
        "pass",
    ]


def test_observe_inbound_filters_and_counts() -> None:
    listed: list[tuple[str, str]] = []

    def run(args: list[str]) -> str:
        if args[:1] == ["api"]:
            raise AssertionError(f"observe-inbound must not fetch catalog: {args}")
        if args[:2] == ["pr", "list"] or args[:2] == ["pr", "comment"]:
            raise AssertionError(f"observe-inbound must not touch PRs: {args}")
        if args[:2] == ["issue", "edit"] or "--add-label" in args:
            raise AssertionError(f"observe-inbound is read-only: {args}")
        if "craft-inbound" in " ".join(args) or "craft-ready" in " ".join(args):
            raise AssertionError(f"observe-inbound is read-only: {args}")
        if "influenzer" in " ".join(args).lower() or "mail" in " ".join(args).lower():
            raise AssertionError(f"observe-inbound is read-only: {args}")
        if args[:2] != ["issue", "list"]:
            raise AssertionError(args)
        repo = args[args.index("-R") + 1]
        listed.append((args[0], repo))
        if repo != HEIMDALL:
            raise AssertionError(f"must survey heimdall only: {repo}")
        return json.dumps(
            [
                _issue(1, "hold inbox", ["bifrost:in", "verdict:hold"]),
                _issue(2, "pass not handed", ["bifrost:in", "verdict:pass"]),
                _issue(3, "ready handoff", ["bifrost:in", "work:ready", "pri:p2"]),
                _issue(4, "outbound path", ["bifrost:in", "bifrost:out"]),
                _issue(5, "ready only", ["work:ready", "pri:p2"]),
                _issue(6, "plain inbound", ["bifrost:in", "signal:feedback"]),
                _issue(7, "noise", ["verdict:hold"]),
            ]
        )

    payload = observe_inbound(run=run)
    assert payload["ok"] is True
    assert payload["atom"] == "observe-inbound"
    assert payload["heimdall"] == HEIMDALL
    assert listed == [("issue", HEIMDALL)]
    assert payload["counts"] == {
        "items": 3,
        "inbound": 3,
        "hold": 1,
        "pass": 1,
    }
    rows = [(row["number"], row["why"]) for row in payload["items"]]
    assert rows == [
        (1, ["inbound", "hold"]),
        (2, ["inbound", "pass"]),
        (6, ["inbound"]),
    ]
    for row in payload["items"]:
        assert set(row) == {"repo", "number", "title", "labels", "url", "why"}
        assert row["repo"] == HEIMDALL
        assert "bifrost:in" in row["labels"]
        assert "work:ready" not in row["labels"]
        assert "bifrost:out" not in row["labels"]
        assert "inbound" in row["why"]


def test_observe_inbound_heimdall_override() -> None:
    listed: list[str] = []

    def run(args: list[str]) -> str:
        if args[:1] == ["api"]:
            raise AssertionError(f"must not fetch catalog: {args}")
        if args[:2] == ["pr", "list"]:
            raise AssertionError(f"must not list PRs: {args}")
        repo = args[args.index("-R") + 1]
        listed.append(repo)
        if repo == "acme/heimdall" and args[0] == "issue":
            return json.dumps([_issue(1, "in", ["bifrost:in"])])
        return "[]"

    payload = observe_inbound(heimdall="acme/heimdall", run=run)
    assert payload["ok"] is True
    assert payload["heimdall"] == "acme/heimdall"
    assert listed == ["acme/heimdall"]
    assert payload["counts"]["inbound"] == 1
    assert payload["items"][0]["number"] == 1
    assert payload["items"][0]["repo"] == "acme/heimdall"


def test_observe_inbound_does_not_fetch_catalog(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*_args: object, **_kwargs: object) -> list[str]:
        raise AssertionError("observe-inbound must not fetch mill catalog")

    monkeypatch.setattr("heimdall.observe_queue.fetch_catalog", boom)

    def run(args: list[str]) -> str:
        if args[:1] == ["api"] or "repos.mikolaj92.yaml" in " ".join(args):
            raise AssertionError(f"must not fetch catalog: {args}")
        if "-R" in args:
            assert args[args.index("-R") + 1] == HEIMDALL
        if args[:2] == ["pr", "list"]:
            raise AssertionError(f"must not list PRs: {args}")
        return "[]"

    payload = observe_inbound(run=run)
    assert payload["ok"] is True
    assert payload["counts"]["items"] == 0
    assert "catalog" not in payload
    assert payload["heimdall"] == HEIMDALL


def test_observe_inbound_gh_failure_is_not_idle() -> None:
    def run(args: list[str]) -> str:
        if args[:1] == ["api"]:
            raise AssertionError(f"must not fetch catalog: {args}")
        raise GhError("Could not resolve to a Repository")

    payload = observe_inbound(run=run)
    assert payload["ok"] is False
    assert payload["atom"] == "observe-inbound"
    assert payload["error"] == "gh failed; not idle"
    assert payload["heimdall"] == HEIMDALL
    assert payload["failed"] == [
        {"repo": HEIMDALL, "error": "Could not resolve to a Repository"}
    ]
    assert "items" not in payload


def test_main_help(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        main(["--help"])
    assert exc.value.code == 0
    out = capsys.readouterr().out
    assert "observe-inbound" in out
    assert "--heimdall" in out


def test_main_emits_stubbed_survey(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    seen: list[str] = []

    def fake_observe(*, heimdall: str = HEIMDALL, run=None) -> dict:
        seen.append(heimdall)
        return {
            "ok": True,
            "atom": "observe-inbound",
            "heimdall": heimdall,
            "counts": {
                "items": 0,
                "inbound": 0,
                "hold": 0,
                "pass": 0,
            },
            "items": [],
        }

    monkeypatch.setattr("heimdall.observe_inbound.observe_inbound", fake_observe)
    assert main(["--heimdall", "acme/heimdall"]) == 0
    assert seen == ["acme/heimdall"]
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["atom"] == "observe-inbound"
    assert payload["heimdall"] == "acme/heimdall"


def test_fala_package_observe_inbound_after_influenzer() -> None:
    text = (Path(__file__).resolve().parents[1] / "fala-package.toml").read_text(
        encoding="utf-8"
    )
    assert 'command = ["uv", "run", "observe-inbound"]' in text
    assert 'conduction = ["observe_influenzer"]' in text
    assert 'id = "observe_inbound"' in text
    assert 'id = "github.observe_inbound"' in text
    assert "python3" not in text
    assert text.index('command = ["uv", "run", "observe-influenzer"]') < text.index(
        'command = ["uv", "run", "observe-inbound"]'
    )
