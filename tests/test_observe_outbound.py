from __future__ import annotations

import json
from pathlib import Path

from heimdall.observe_queue import HEIMDALL, GhError
from heimdall.observe_outbound import keep_outbound, observe_outbound

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


def _pr(number: int, title: str, labels: list[str], head: str = "cursor/x") -> dict:
    return {
        "number": number,
        "title": title,
        "labels": [{"name": n} for n in labels],
        "url": f"https://github.com/example/repo/pull/{number}",
        "headRefName": head,
    }


def test_keep_outbound_out_without_pass() -> None:
    assert keep_outbound(["bifrost:out"])
    assert keep_outbound(["bifrost:out", "story:ship"])
    assert keep_outbound(["bifrost:out", "verdict:hold"])
    assert keep_outbound(["bifrost:out", "verdict:reject"])
    assert keep_outbound(["bifrost:out", "verdict:needs-scout"])


def test_keep_outbound_out_plus_pass_dropped() -> None:
    assert not keep_outbound(["bifrost:out", "verdict:pass"])
    assert not keep_outbound(["verdict:pass", "bifrost:out", "story:ship"])


def test_keep_outbound_not_out_dropped() -> None:
    assert not keep_outbound([])
    assert not keep_outbound(["bifrost:in"])
    assert not keep_outbound(["verdict:hold"])
    assert not keep_outbound(["verdict:pass"])
    assert not keep_outbound(["work:ready", "pri:p2"])


def test_observe_outbound_filters_and_counts() -> None:
    _reset_catalog()
    listed: list[tuple[str, str]] = []

    def run(args: list[str]) -> str:
        if args[:1] == ["api"]:
            return CATALOG_YAML
        if args[:2] == ["issue", "edit"] or args[:2] == ["pr", "comment"]:
            raise AssertionError(f"observe-outbound is read-only: {args}")
        if "--add-label" in args or "influenzer" in " ".join(args).lower():
            raise AssertionError(f"observe-outbound is read-only: {args}")
        if args[:2] not in (["issue", "list"], ["pr", "list"]):
            raise AssertionError(args)
        repo = args[args.index("-R") + 1]
        listed.append((args[0], repo))
        if repo == HEIMDALL and args[0] == "issue":
            return json.dumps(
                [
                    _issue(1, "draft", ["bifrost:out", "story:ship"]),
                    _issue(2, "shipped", ["bifrost:out", "verdict:pass"]),
                    _issue(3, "inbound", ["bifrost:in", "signal:feedback"]),
                    _issue(4, "hold", ["bifrost:out", "verdict:hold"]),
                ]
            )
        if repo == HEIMDALL and args[0] == "pr":
            return json.dumps(
                [
                    _pr(5, "needs scout", ["bifrost:out", "verdict:needs-scout"]),
                    _pr(6, "ok to post", ["bifrost:out", "verdict:pass"]),
                    _pr(7, "noise", ["enhancement"]),
                ]
            )
        if repo == "mikolaj92/lokay" and args[0] == "issue":
            return json.dumps(
                [
                    _issue(10, "mill out", ["bifrost:out", "verdict:reject"]),
                    _issue(11, "mill pass", ["bifrost:out", "verdict:pass"]),
                    _issue(12, "ready", ["work:ready"]),
                ]
            )
        if repo == "mikolaj92/lokay" and args[0] == "pr":
            return json.dumps(
                [_pr(13, "mill draft pr", ["bifrost:out"], "ai/fix/1")]
            )
        if repo == "mikolaj92/Docxtor":
            return "[]"
        if repo == "mikolaj92/reviewkit" and args[0] == "issue":
            return json.dumps([_issue(20, "plain", ["bug"])])
        return "[]"

    payload = observe_outbound(run=run)
    assert payload["ok"] is True
    assert payload["atom"] == "observe-outbound"
    assert HEIMDALL not in payload["catalog"]
    assert "mikolaj92/heimdall" not in payload["catalog"]
    heimdall_lists = [kind for kind, repo in listed if repo == HEIMDALL]
    assert heimdall_lists == ["issue", "pr"]
    assert listed.count(("issue", HEIMDALL)) == 1
    assert listed.count(("pr", HEIMDALL)) == 1
    assert payload["counts"]["catalog"] == 3
    assert payload["counts"]["surveyed"] == 4
    assert payload["counts"]["heimdall_items"] == 3
    assert payload["counts"]["mill_items"] == 2
    assert payload["counts"]["items"] == 5
    rows = [(row["repo"], row["number"], row["kind"]) for row in payload["items"]]
    assert rows == [
        (HEIMDALL, 1, "issue"),
        (HEIMDALL, 4, "issue"),
        (HEIMDALL, 5, "pull"),
        ("mikolaj92/lokay", 10, "issue"),
        ("mikolaj92/lokay", 13, "pull"),
    ]
    for row in payload["items"]:
        assert set(row) == {"repo", "number", "title", "labels", "url", "kind"}
        assert row["kind"] in {"issue", "pull"}
        assert "bifrost:out" in row["labels"]
        assert "verdict:pass" not in row["labels"]
        assert "_head" not in row
    _reset_catalog()


def test_observe_outbound_catalog_error_fails_closed() -> None:
    _reset_catalog()

    def run(args: list[str]) -> str:
        raise GhError("API rate limit")

    payload = observe_outbound(run=run)
    assert payload["ok"] is False
    assert payload["atom"] == "observe-outbound"
    assert "catalog" in payload["error"]
    assert "items" not in payload
    _reset_catalog()


def test_observe_outbound_repo_error_does_not_pretend_idle() -> None:
    _reset_catalog()

    def run(args: list[str]) -> str:
        if args[:1] == ["api"]:
            return CATALOG_YAML
        repo = args[args.index("-R") + 1]
        if repo == "mikolaj92/Docxtor":
            raise GhError("Could not resolve to a Repository")
        return "[]"

    payload = observe_outbound(run=run)
    assert payload["ok"] is False
    assert payload["error"] == "gh failed; not idle"
    assert payload["failed"] == [
        {"repo": "mikolaj92/Docxtor", "error": "Could not resolve to a Repository"}
    ]
    assert payload["counts"]["items"] == 0
    assert payload["counts"]["surveyed"] == 3
    _reset_catalog()


def test_fala_package_observe_outbound_after_verdict() -> None:
    text = (Path(__file__).resolve().parents[1] / "fala-package.toml").read_text(
        encoding="utf-8"
    )
    assert 'command = ["uv", "run", "observe-outbound"]' in text
    assert 'conduction = ["observe_verdict"]' in text
    assert 'id = "observe_outbound"' in text
    assert 'id = "github.observe_outbound"' in text
    assert "python3" not in text
    assert text.index('id = "observe_verdict"') < text.index(
        'command = ["uv", "run", "observe-outbound"]'
    )
