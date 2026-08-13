from __future__ import annotations

import json
from pathlib import Path

from heimdall.observe_blocked import keep_blocked, observe_blocked
from heimdall.observe_queue import HEIMDALL, GhError

CATALOG_YAML = """\
# Repos Lokay manages (mikolaj92 source / non-fork).
owner: mikolaj92
repos:
  - name: mikolaj92/lokay
    clone_path: /tmp/lokay
    priority: 100
  - name: mikolaj92/Docxtor
    clone_path: /tmp/Docxtor
    priority: 80
  - name: mikolaj92/heimdall
    clone_path: /tmp/heimdall
    priority: 1
  - name: "mikolaj92/reviewkit"
    clone_path: /tmp/reviewkit
"""


def _reset_catalog() -> None:
    import heimdall.observe_queue as mod

    mod._catalog_cache = None


def _issue(number: int, title: str, labels: list[str]) -> dict:
    return {
        "number": number,
        "title": title,
        "labels": [{"name": n} for n in labels],
        "url": f"https://github.com/example/repo/issues/{number}",
    }


def test_keep_blocked_heimdall_work_blocked_only() -> None:
    assert keep_blocked(["work:blocked"])
    assert keep_blocked(["work:blocked", "pri:p1"])
    assert not keep_blocked(["work:ready"])
    assert not keep_blocked(["work:doing"])
    assert not keep_blocked(["work:ready", "work:doing"])
    assert not keep_blocked(["ai:blocked"])
    assert not keep_blocked(["work:done"])
    assert not keep_blocked([])


def test_keep_blocked_mill_work_or_ai_blocked() -> None:
    assert keep_blocked(["work:blocked"], mill=True)
    assert keep_blocked(["ai:blocked"], mill=True)
    assert keep_blocked(["ai:blocked", "pri:p2"], mill=True)
    assert keep_blocked(["work:blocked", "ai:blocked"], mill=True)
    assert not keep_blocked(["work:ready"], mill=True)
    assert not keep_blocked(["work:doing"], mill=True)
    assert not keep_blocked(["ai:ready"], mill=True)
    assert not keep_blocked(["ai:in-progress"], mill=True)
    assert not keep_blocked(["work:done"], mill=True)
    assert not keep_blocked([], mill=True)


def test_observe_blocked_filters_and_counts() -> None:
    _reset_catalog()
    listed: list[tuple[str, str]] = []

    def run(args: list[str]) -> str:
        if args[:1] == ["api"]:
            return CATALOG_YAML
        if args[:2] == ["pr", "list"] or args[:2] == ["pr", "comment"]:
            raise AssertionError(f"observe-blocked must not touch PRs: {args}")
        if args[:2] == ["issue", "edit"] or "--add-label" in args:
            raise AssertionError(f"observe-blocked is read-only: {args}")
        if "influenzer" in " ".join(args).lower() or "mail" in " ".join(args).lower():
            raise AssertionError(f"observe-blocked is read-only: {args}")
        if args[:2] != ["issue", "list"]:
            raise AssertionError(args)
        repo = args[args.index("-R") + 1]
        listed.append((args[0], repo))
        if repo == HEIMDALL:
            return json.dumps(
                [
                    _issue(1, "stuck", ["work:blocked", "pri:p1"]),
                    _issue(2, "ready", ["work:ready", "pri:p2"]),
                    _issue(3, "doing", ["work:doing"]),
                    _issue(4, "mill label only", ["ai:blocked"]),
                    _issue(5, "also stuck", ["work:blocked"]),
                ]
            )
        if repo == "mikolaj92/lokay":
            return json.dumps(
                [
                    _issue(10, "mill blocked", ["work:blocked"]),
                    _issue(11, "mill ai blocked", ["ai:blocked"]),
                    _issue(12, "ready", ["work:ready", "ai:ready"]),
                    _issue(13, "doing", ["work:doing", "ai:in-progress"]),
                    _issue(14, "plain", ["bug"]),
                ]
            )
        if repo == "mikolaj92/Docxtor":
            return "[]"
        if repo == "mikolaj92/reviewkit":
            return json.dumps([_issue(20, "ai blocked", ["ai:blocked", "pri:p3"])])
        return "[]"

    payload = observe_blocked(run=run)
    assert payload["ok"] is True
    assert payload["atom"] == "observe-blocked"
    assert HEIMDALL not in payload["catalog"]
    assert "mikolaj92/heimdall" not in payload["catalog"]
    assert listed.count(("issue", HEIMDALL)) == 1
    assert ("pr", HEIMDALL) not in listed
    assert payload["counts"]["catalog"] == 3
    assert payload["counts"]["surveyed"] == 4
    assert payload["counts"]["heimdall_items"] == 2
    assert payload["counts"]["mill_items"] == 3
    assert payload["counts"]["items"] == 5
    rows = [(row["repo"], row["number"]) for row in payload["items"]]
    assert rows == [
        (HEIMDALL, 1),
        (HEIMDALL, 5),
        ("mikolaj92/lokay", 10),
        ("mikolaj92/lokay", 11),
        ("mikolaj92/reviewkit", 20),
    ]
    for row in payload["items"]:
        assert set(row) == {"repo", "number", "title", "labels", "url"}
        assert "work:ready" not in row["labels"]
        assert "work:doing" not in row["labels"]
        blocked = "work:blocked" in row["labels"] or "ai:blocked" in row["labels"]
        assert blocked
        if row["repo"] == HEIMDALL:
            assert "work:blocked" in row["labels"]
    _reset_catalog()


def test_observe_blocked_catalog_error_fails_closed() -> None:
    _reset_catalog()

    def run(args: list[str]) -> str:
        raise GhError("API rate limit")

    payload = observe_blocked(run=run)
    assert payload["ok"] is False
    assert payload["atom"] == "observe-blocked"
    assert "catalog" in payload["error"]
    assert "items" not in payload
    _reset_catalog()


def test_observe_blocked_repo_error_does_not_pretend_idle() -> None:
    _reset_catalog()

    def run(args: list[str]) -> str:
        if args[:1] == ["api"]:
            return CATALOG_YAML
        repo = args[args.index("-R") + 1]
        if repo == "mikolaj92/Docxtor":
            raise GhError("Could not resolve to a Repository")
        return "[]"

    payload = observe_blocked(run=run)
    assert payload["ok"] is False
    assert payload["error"] == "gh failed; not idle"
    assert payload["failed"] == [
        {"repo": "mikolaj92/Docxtor", "error": "Could not resolve to a Repository"}
    ]
    assert payload["counts"]["items"] == 0
    assert payload["counts"]["surveyed"] == 3
    _reset_catalog()


def test_fala_package_observe_blocked_after_outbound() -> None:
    text = (Path(__file__).resolve().parents[1] / "fala-package.toml").read_text(
        encoding="utf-8"
    )
    assert 'command = ["uv", "run", "observe-blocked"]' in text
    assert 'conduction = ["observe_outbound"]' in text
    assert 'id = "observe_blocked"' in text
    assert 'id = "github.observe_blocked"' in text
    assert "python3" not in text
    assert text.index('command = ["uv", "run", "observe-outbound"]') < text.index(
        'command = ["uv", "run", "observe-blocked"]'
    )
