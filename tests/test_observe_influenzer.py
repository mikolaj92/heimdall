from __future__ import annotations

import json
from pathlib import Path

import pytest

from heimdall.observe_influenzer import (
    INFLUENZER,
    main,
    observe_influenzer,
    why_issue,
)
from heimdall.observe_queue import GhError


def _issue(number: int, title: str, labels: list[str]) -> dict:
    return {
        "number": number,
        "title": title,
        "labels": [{"name": n} for n in labels],
        "url": f"https://github.com/example/repo/issues/{number}",
    }


def _pr(number: int, title: str, labels: list[str], head: str = "cursor/x") -> dict:
    return {
        "number": number,
        "title": title,
        "labels": [{"name": n} for n in labels],
        "url": f"https://github.com/example/repo/pull/{number}",
        "headRefName": head,
    }


def test_why_issue_inbound() -> None:
    assert why_issue(["bifrost:in"]) == ["inbound"]
    assert why_issue(["bifrost:in", "signal:feedback"]) == ["inbound"]


def test_why_issue_outbound_hold_without_pass() -> None:
    assert why_issue(["bifrost:out"]) == ["outbound_hold"]
    assert why_issue(["bifrost:out", "story:ship"]) == ["outbound_hold"]
    assert why_issue(["bifrost:out", "verdict:hold"]) == ["outbound_hold", "hold"]


def test_why_issue_outbound_plus_pass_not_outbound_hold() -> None:
    assert why_issue(["bifrost:out", "verdict:pass"]) == []
    assert why_issue(["bifrost:out", "verdict:pass", "work:blocked"]) == ["blocked"]


def test_why_issue_blocked_and_hold() -> None:
    assert why_issue(["work:blocked"]) == ["blocked"]
    assert why_issue(["verdict:hold"]) == ["hold"]
    assert why_issue(["bifrost:in", "verdict:hold"]) == ["inbound", "hold"]
    assert why_issue(["work:ready"]) == []
    assert why_issue([]) == []


def test_observe_influenzer_filters_and_counts() -> None:
    listed: list[tuple[str, str]] = []

    def run(args: list[str]) -> str:
        if args[:1] == ["api"]:
            raise AssertionError(f"observe-influenzer must not fetch catalog: {args}")
        if args[:2] == ["issue", "edit"] or args[:2] == ["pr", "comment"]:
            raise AssertionError(f"observe-influenzer is read-only: {args}")
        if "--add-label" in args or "influenzer-handoff" in " ".join(args):
            raise AssertionError(f"observe-influenzer is read-only: {args}")
        if args[:2] not in (["issue", "list"], ["pr", "list"]):
            raise AssertionError(args)
        repo = args[args.index("-R") + 1]
        listed.append((args[0], repo))
        if repo != INFLUENZER:
            raise AssertionError(f"must survey Influenzer only: {repo}")
        if args[0] == "issue":
            return json.dumps(
                [
                    _issue(1, "feedback", ["bifrost:in", "signal:feedback"]),
                    _issue(2, "shipped", ["bifrost:out", "verdict:pass"]),
                    _issue(3, "draft", ["bifrost:out", "story:ship"]),
                    _issue(4, "stuck", ["work:blocked"]),
                    _issue(5, "waiting", ["verdict:hold"]),
                    _issue(6, "in and hold", ["bifrost:in", "verdict:hold"]),
                    _issue(7, "pass and blocked", ["bifrost:out", "verdict:pass", "work:blocked"]),
                    _issue(8, "noise", ["work:ready", "pri:p2"]),
                ]
            )
        return json.dumps(
            [
                _pr(9, "human", ["enhancement"], "feature/copy"),
                _pr(10, "cursor", ["bifrost:in"], "cursor/foo"),
            ]
        )

    payload = observe_influenzer(run=run)
    assert payload["ok"] is True
    assert payload["atom"] == "observe-influenzer"
    assert payload["repo"] == INFLUENZER
    assert listed == [("issue", INFLUENZER), ("pr", INFLUENZER)]
    assert payload["counts"] == {
        "items": 8,
        "inbound": 2,
        "outbound_hold": 1,
        "blocked": 2,
        "hold": 2,
        "pulls": 2,
    }
    rows = [(row["number"], row["why"]) for row in payload["items"]]
    assert rows == [
        (1, ["inbound"]),
        (3, ["outbound_hold"]),
        (4, ["blocked"]),
        (5, ["hold"]),
        (6, ["inbound", "hold"]),
        (7, ["blocked"]),
        (9, ["pull"]),
        (10, ["pull"]),
    ]
    for row in payload["items"]:
        assert set(row) == {"repo", "number", "title", "labels", "url", "why"}
        assert row["repo"] == INFLUENZER
        assert "_head" not in row
        if "pull" in row["why"]:
            assert row["why"] == ["pull"]


def test_observe_influenzer_repo_override() -> None:
    listed: list[str] = []

    def run(args: list[str]) -> str:
        if args[:1] == ["api"]:
            raise AssertionError(f"must not fetch catalog: {args}")
        repo = args[args.index("-R") + 1]
        listed.append(repo)
        if repo == "acme/influenzer" and args[0] == "issue":
            return json.dumps([_issue(1, "in", ["bifrost:in"])])
        return "[]"

    payload = observe_influenzer(repo="acme/influenzer", run=run)
    assert payload["ok"] is True
    assert payload["repo"] == "acme/influenzer"
    assert listed == ["acme/influenzer", "acme/influenzer"]
    assert payload["counts"]["inbound"] == 1
    assert payload["items"][0]["number"] == 1


def test_observe_influenzer_does_not_fetch_catalog(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*_args: object, **_kwargs: object) -> list[str]:
        raise AssertionError("observe-influenzer must not fetch mill catalog")

    monkeypatch.setattr("heimdall.observe_queue.fetch_catalog", boom)

    def run(args: list[str]) -> str:
        if args[:1] == ["api"] or "repos.mikolaj92.yaml" in " ".join(args):
            raise AssertionError(f"must not fetch catalog: {args}")
        if "-R" in args:
            assert args[args.index("-R") + 1] == INFLUENZER
        return "[]"

    payload = observe_influenzer(run=run)
    assert payload["ok"] is True
    assert payload["counts"]["items"] == 0
    assert "catalog" not in payload
    assert payload["repo"] == INFLUENZER


def test_observe_influenzer_gh_failure_is_not_idle() -> None:
    def run(args: list[str]) -> str:
        if args[:1] == ["api"]:
            raise AssertionError(f"must not fetch catalog: {args}")
        raise GhError("Could not resolve to a Repository")

    payload = observe_influenzer(run=run)
    assert payload["ok"] is False
    assert payload["atom"] == "observe-influenzer"
    assert payload["error"] == "gh failed; not idle"
    assert payload["repo"] == INFLUENZER
    assert payload["failed"] == [
        {"repo": INFLUENZER, "error": "Could not resolve to a Repository"}
    ]
    assert "items" not in payload


def test_main_help(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        main(["--help"])
    assert exc.value.code == 0
    out = capsys.readouterr().out
    assert "observe-influenzer" in out
    assert "--repo" in out


def test_main_emits_stubbed_survey(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    seen: list[str] = []

    def fake_observe(*, repo: str = INFLUENZER, run=None) -> dict:
        seen.append(repo)
        return {
            "ok": True,
            "atom": "observe-influenzer",
            "repo": repo,
            "counts": {
                "items": 0,
                "inbound": 0,
                "outbound_hold": 0,
                "blocked": 0,
                "hold": 0,
                "pulls": 0,
            },
            "items": [],
        }

    monkeypatch.setattr("heimdall.observe_influenzer.observe_influenzer", fake_observe)
    assert main(["--repo", "acme/influenzer"]) == 0
    assert seen == ["acme/influenzer"]
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["atom"] == "observe-influenzer"
    assert payload["repo"] == "acme/influenzer"


def test_fala_package_observe_influenzer_after_blocked() -> None:
    text = (Path(__file__).resolve().parents[1] / "fala-package.toml").read_text(
        encoding="utf-8"
    )
    assert 'command = ["uv", "run", "observe-influenzer"]' in text
    assert 'conduction = ["observe_blocked"]' in text
    assert 'id = "observe_influenzer"' in text
    assert 'id = "github.observe_influenzer"' in text
    assert "python3" not in text
    assert text.index('command = ["uv", "run", "observe-blocked"]') < text.index(
        'command = ["uv", "run", "observe-influenzer"]'
    )
