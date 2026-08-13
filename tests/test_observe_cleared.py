from __future__ import annotations

import json
from pathlib import Path

import pytest

from heimdall.observe_queue import HEIMDALL, GhError
from heimdall.observe_cleared import keep_cleared, main, observe_cleared

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


def test_keep_cleared_out_plus_pass() -> None:
    assert keep_cleared(["bifrost:out", "verdict:pass"])
    assert keep_cleared(["verdict:pass", "bifrost:out", "story:ship"])


def test_keep_cleared_out_without_pass_dropped() -> None:
    assert not keep_cleared(["bifrost:out"])
    assert not keep_cleared(["bifrost:out", "story:ship"])
    assert not keep_cleared(["bifrost:out", "verdict:hold"])
    assert not keep_cleared(["bifrost:out", "verdict:reject"])
    assert not keep_cleared(["bifrost:out", "verdict:needs-scout"])


def test_keep_cleared_pass_without_out_dropped() -> None:
    assert not keep_cleared(["verdict:pass"])
    assert not keep_cleared(["verdict:pass", "story:ship"])
    assert not keep_cleared(["verdict:pass", "bifrost:in"])


def test_keep_cleared_hold_reject_not_kept_even_with_out() -> None:
    assert not keep_cleared(["bifrost:out", "verdict:hold"])
    assert not keep_cleared(["bifrost:out", "verdict:reject"])
    assert not keep_cleared(["bifrost:out", "verdict:hold", "story:ship"])
    assert not keep_cleared(["verdict:reject", "bifrost:out"])


def test_keep_cleared_not_out_dropped() -> None:
    assert not keep_cleared([])
    assert not keep_cleared(["bifrost:in"])
    assert not keep_cleared(["verdict:hold"])
    assert not keep_cleared(["work:ready", "pri:p2"])


def test_observe_cleared_filters_and_counts() -> None:
    _reset_catalog()
    listed: list[tuple[str, str]] = []

    def run(args: list[str]) -> str:
        if args[:1] == ["api"]:
            return CATALOG_YAML
        if args[:2] == ["issue", "edit"] or args[:2] == ["pr", "comment"]:
            raise AssertionError(f"observe-cleared is read-only: {args}")
        joined = " ".join(args).lower()
        if "--add-label" in args or "influenzer" in joined or "influenzer-handoff" in joined:
            raise AssertionError(f"observe-cleared is read-only: {args}")
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
                    _issue(8, "pass only", ["verdict:pass"]),
                ]
            )
        if repo == HEIMDALL and args[0] == "pr":
            return json.dumps(
                [
                    _pr(5, "needs scout", ["bifrost:out", "verdict:needs-scout"]),
                    _pr(6, "ok to post", ["bifrost:out", "verdict:pass"]),
                    _pr(7, "noise", ["enhancement"]),
                    _pr(9, "reject", ["bifrost:out", "verdict:reject"]),
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

    payload = observe_cleared(run=run)
    assert payload["ok"] is True
    assert payload["atom"] == "observe-cleared"
    assert HEIMDALL not in payload["catalog"]
    assert "mikolaj92/heimdall" not in payload["catalog"]
    heimdall_lists = [kind for kind, repo in listed if repo == HEIMDALL]
    assert heimdall_lists == ["issue", "pr"]
    assert listed.count(("issue", HEIMDALL)) == 1
    assert listed.count(("pr", HEIMDALL)) == 1
    assert payload["counts"]["catalog"] == 3
    assert payload["counts"]["surveyed"] == 4
    assert payload["counts"]["heimdall_items"] == 2
    assert payload["counts"]["mill_items"] == 1
    assert payload["counts"]["items"] == 3
    rows = [(row["repo"], row["number"], row["kind"]) for row in payload["items"]]
    assert rows == [
        (HEIMDALL, 2, "issue"),
        (HEIMDALL, 6, "pull"),
        ("mikolaj92/lokay", 11, "issue"),
    ]
    for row in payload["items"]:
        assert set(row) == {"repo", "number", "title", "labels", "url", "kind"}
        assert row["kind"] in {"issue", "pull"}
        assert "bifrost:out" in row["labels"]
        assert "verdict:pass" in row["labels"]
        assert "_head" not in row
    _reset_catalog()


def test_observe_cleared_catalog_error_fails_closed() -> None:
    _reset_catalog()

    def run(args: list[str]) -> str:
        raise GhError("API rate limit")

    payload = observe_cleared(run=run)
    assert payload["ok"] is False
    assert payload["atom"] == "observe-cleared"
    assert "catalog" in payload["error"]
    assert "items" not in payload
    _reset_catalog()


def test_observe_cleared_repo_error_does_not_pretend_idle() -> None:
    _reset_catalog()

    def run(args: list[str]) -> str:
        if args[:1] == ["api"]:
            return CATALOG_YAML
        repo = args[args.index("-R") + 1]
        if repo == "mikolaj92/Docxtor":
            raise GhError("Could not resolve to a Repository")
        return "[]"

    payload = observe_cleared(run=run)
    assert payload["ok"] is False
    assert payload["error"] == "gh failed; not idle"
    assert payload["failed"] == [
        {"repo": "mikolaj92/Docxtor", "error": "Could not resolve to a Repository"}
    ]
    assert payload["counts"]["items"] == 0
    assert payload["counts"]["surveyed"] == 3
    _reset_catalog()


def test_main_help(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        main(["--help"])
    assert exc.value.code == 0
    out = capsys.readouterr().out
    assert "observe-cleared" in out
    assert "--heimdall" in out


def test_fala_package_observe_cleared_after_inbound() -> None:
    text = (Path(__file__).resolve().parents[1] / "fala-package.toml").read_text(
        encoding="utf-8"
    )
    assert 'command = ["uv", "run", "observe-cleared"]' in text
    assert 'conduction = ["observe_inbound"]' in text
    assert 'id = "observe_cleared"' in text
    assert 'id = "github.observe_cleared"' in text
    assert "python3" not in text
    assert "influenzer-handoff" not in text
    assert "out-apply" not in text
    assert text.index('command = ["uv", "run", "observe-inbound"]') < text.index(
        'command = ["uv", "run", "observe-cleared"]'
    )
