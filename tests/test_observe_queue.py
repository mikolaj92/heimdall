from __future__ import annotations

import json

import pytest

from heimdall.observe_queue import (
    HEIMDALL,
    GhError,
    fetch_catalog,
    keep_issue,
    mill_pr,
    observe,
    parse_catalog,
)

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


def test_parse_catalog_skips_heimdall_and_duplicates() -> None:
    names = parse_catalog(CATALOG_YAML)
    assert names == [
        "mikolaj92/lokay",
        "mikolaj92/Docxtor",
        "mikolaj92/reviewkit",
    ]
    assert HEIMDALL not in names
    assert "mikolaj92/heimdall" not in names


def test_parse_catalog_empty_fails_closed() -> None:
    with pytest.raises(GhError, match="no repos parsed"):
        parse_catalog("owner: mikolaj92\nrepos: []\n")


def test_catalog_cache_is_in_process_only() -> None:
    import heimdall.observe_queue as mod

    mod._catalog_cache = None
    calls: list[list[str]] = []

    def run(args: list[str]) -> str:
        calls.append(args)
        return CATALOG_YAML

    first = fetch_catalog(run=run)
    second = fetch_catalog(run=run)
    assert first == second == [
        "mikolaj92/lokay",
        "mikolaj92/Docxtor",
        "mikolaj92/reviewkit",
    ]
    assert len(calls) == 1
    assert calls[0][0] == "api"
    assert "repos.mikolaj92.yaml" in calls[0][-1]
    mod._catalog_cache = None


def test_heimdall_issue_filter() -> None:
    wanted = frozenset({"work:ready", "work:doing", "work:blocked"})
    assert keep_issue(["work:ready", "pri:p2"], wanted)
    assert keep_issue(["work:blocked"], wanted)
    assert not keep_issue(["work:done"], wanted)
    assert not keep_issue(["ai:ready"], wanted)
    assert not keep_issue([], wanted)


def test_mill_issue_filter() -> None:
    wanted = frozenset({"ai:ready", "ai:in-progress", "work:ready", "work:doing"})
    assert keep_issue(["ai:ready"], wanted)
    assert keep_issue(["ai:in-progress", "work:ready"], wanted)
    assert keep_issue(["work:doing"], wanted)
    assert not keep_issue(["work:blocked"], wanted)
    assert not keep_issue(["ai:blocked"], wanted)


def test_mill_pr_cheap_signals() -> None:
    assert mill_pr(["ai:pr-opened"])
    assert mill_pr(["ai:needs-review"])
    assert mill_pr(["ai:something-new"])
    assert mill_pr([], "ai/fix/12")
    assert not mill_pr(["bug"], "feature/login")
    assert not mill_pr([], "cursor/observe-queue")


def _issue(number: int, title: str, labels: list[str]) -> dict:
    return {
        "number": number,
        "title": title,
        "labels": [{"name": n} for n in labels],
        "url": f"https://github.com/example/repo/issues/{number}",
    }


def _pr(number: int, title: str, labels: list[str], head: str) -> dict:
    return {
        "number": number,
        "title": title,
        "labels": [{"name": n} for n in labels],
        "url": f"https://github.com/example/repo/pull/{number}",
        "headRefName": head,
    }


def test_observe_ok_filters_and_counts() -> None:
    import heimdall.observe_queue as mod

    mod._catalog_cache = None

    def run(args: list[str]) -> str:
        if args[:1] == ["api"]:
            return CATALOG_YAML
        repo = args[args.index("-R") + 1]
        kind = args[0]
        if repo == HEIMDALL and kind == "issue":
            return json.dumps(
                [
                    _issue(1, "ready", ["work:ready", "pri:p2"]),
                    _issue(2, "hold", ["verdict:hold"]),
                    _issue(3, "blocked", ["work:blocked"]),
                ]
            )
        if repo == HEIMDALL and kind == "pr":
            return json.dumps(
                [_pr(4, "qa", ["bifrost:in"], "cursor/foo")]
            )
        if repo == "mikolaj92/lokay" and kind == "issue":
            return json.dumps(
                [
                    _issue(10, "mill ready", ["ai:ready"]),
                    _issue(11, "noise", ["bug"]),
                ]
            )
        if repo == "mikolaj92/lokay" and kind == "pr":
            return json.dumps(
                [
                    _pr(12, "ai pr", ["ai:pr-opened"], "ai/fix/10"),
                    _pr(13, "human", ["enhancement"], "feature/x"),
                ]
            )
        if kind in {"issue", "pr"}:
            return "[]"
        raise AssertionError(args)

    payload = observe(run=run)
    assert payload["ok"] is True
    assert payload["atom"] == "observe-queue"
    assert HEIMDALL not in payload["catalog"]
    assert payload["counts"]["heimdall_issues"] == 2
    assert payload["counts"]["heimdall_pulls"] == 1
    assert payload["counts"]["mill_issues"] == 1
    assert payload["counts"]["mill_pulls"] == 1
    by_repo = {row["repo"]: row for row in payload["repos"]}
    assert [i["number"] for i in by_repo[HEIMDALL]["issues"]] == [1, 3]
    assert [p["number"] for p in by_repo["mikolaj92/lokay"]["pulls"]] == [12]
    assert "_head" not in by_repo["mikolaj92/lokay"]["pulls"][0]
    mod._catalog_cache = None


def test_observe_catalog_error_fails_closed() -> None:
    import heimdall.observe_queue as mod

    mod._catalog_cache = None

    def run(args: list[str]) -> str:
        raise GhError("API rate limit")

    payload = observe(run=run)
    assert payload["ok"] is False
    assert "catalog" in payload["error"]
    assert "repos" not in payload
    mod._catalog_cache = None


def test_observe_repo_error_does_not_pretend_idle() -> None:
    import heimdall.observe_queue as mod

    mod._catalog_cache = None

    def run(args: list[str]) -> str:
        if args[:1] == ["api"]:
            return CATALOG_YAML
        repo = args[args.index("-R") + 1]
        if repo == "mikolaj92/Docxtor":
            raise GhError("Could not resolve to a Repository")
        return "[]"

    payload = observe(run=run)
    assert payload["ok"] is False
    assert payload["error"] == "gh failed; not idle"
    assert payload["failed"] == [
        {"repo": "mikolaj92/Docxtor", "error": "Could not resolve to a Repository"}
    ]
    surveyed = {row["repo"] for row in payload["repos"]}
    assert "mikolaj92/Docxtor" not in surveyed
    assert HEIMDALL in surveyed
    assert payload["counts"]["issues"] == 0
    mod._catalog_cache = None
