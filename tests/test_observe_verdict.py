from __future__ import annotations

import json
from pathlib import Path

from heimdall.observe_queue import HEIMDALL, GhError
from heimdall.observe_verdict import keep_verdict_pr, observe_verdict

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


def _pr(number: int, title: str, labels: list[str], head: str) -> dict:
    return {
        "number": number,
        "title": title,
        "labels": [{"name": n} for n in labels],
        "url": f"https://github.com/example/repo/pull/{number}",
        "headRefName": head,
    }


def test_keep_verdict_pr_heimdall_all_open() -> None:
    assert keep_verdict_pr("heimdall", ["bug"], "feature/login")
    assert keep_verdict_pr("heimdall", [], "cursor/observe-verdict")
    assert keep_verdict_pr("heimdall", ["ai:pr-opened"], "ai/fix/1")


def test_keep_verdict_pr_mill_cheap_signals() -> None:
    assert keep_verdict_pr("mill", ["ai:pr-opened"], "ai/fix/12")
    assert keep_verdict_pr("mill", ["ai:needs-review"], "feature/x")
    assert keep_verdict_pr("mill", ["ai:something-new"], "main")
    assert keep_verdict_pr("mill", [], "ai/fix/12")
    assert not keep_verdict_pr("mill", ["bug"], "feature/login")
    assert not keep_verdict_pr("mill", ["enhancement"], "cursor/human")
    assert not keep_verdict_pr("mill", [], "cursor/observe-queue")


def test_observe_verdict_filters_and_counts() -> None:
    _reset_catalog()
    listed: list[str] = []

    def run(args: list[str]) -> str:
        if args[:1] == ["api"]:
            return CATALOG_YAML
        if args[:2] == ["issue", "list"] or args[:2] == ["issue", "edit"]:
            raise AssertionError(f"observe-verdict must not touch issues: {args}")
        if args[:2] == ["pr", "comment"] or "--add-label" in args:
            raise AssertionError(f"observe-verdict is read-only: {args}")
        if args[:2] != ["pr", "list"]:
            raise AssertionError(args)
        repo = args[args.index("-R") + 1]
        listed.append(repo)
        if repo == HEIMDALL:
            return json.dumps(
                [
                    _pr(4, "qa", ["bifrost:in"], "cursor/foo"),
                    _pr(5, "human", ["enhancement"], "feature/login"),
                ]
            )
        if repo == "mikolaj92/lokay":
            return json.dumps(
                [
                    _pr(12, "ai pr", ["ai:pr-opened"], "ai/fix/10"),
                    _pr(13, "human", ["enhancement"], "feature/x"),
                    _pr(14, "ai head", [], "ai/repair/11"),
                ]
            )
        if repo == "mikolaj92/Docxtor":
            return json.dumps([_pr(2, "noise", ["bug"], "cursor/docs")])
        return "[]"

    payload = observe_verdict(run=run)
    assert payload["ok"] is True
    assert payload["atom"] == "observe-verdict"
    assert HEIMDALL not in payload["catalog"]
    assert HEIMDALL in listed
    assert "mikolaj92/heimdall" not in payload["catalog"]
    assert payload["counts"]["heimdall_pulls"] == 2
    assert payload["counts"]["mill_pulls"] == 2
    assert payload["counts"]["pulls"] == 4
    assert payload["counts"]["catalog"] == 3
    assert payload["counts"]["surveyed"] == 4
    numbers = [(row["repo"], row["number"]) for row in payload["pulls"]]
    assert numbers == [
        (HEIMDALL, 4),
        (HEIMDALL, 5),
        ("mikolaj92/lokay", 12),
        ("mikolaj92/lokay", 14),
    ]
    for row in payload["pulls"]:
        assert set(row) == {"repo", "number", "title", "labels", "url"}
        assert "_head" not in row
    _reset_catalog()


def test_observe_verdict_catalog_error_fails_closed() -> None:
    _reset_catalog()

    def run(args: list[str]) -> str:
        raise GhError("API rate limit")

    payload = observe_verdict(run=run)
    assert payload["ok"] is False
    assert payload["atom"] == "observe-verdict"
    assert "catalog" in payload["error"]
    assert "pulls" not in payload
    _reset_catalog()


def test_observe_verdict_repo_error_does_not_pretend_idle() -> None:
    _reset_catalog()

    def run(args: list[str]) -> str:
        if args[:1] == ["api"]:
            return CATALOG_YAML
        repo = args[args.index("-R") + 1]
        if repo == "mikolaj92/Docxtor":
            raise GhError("Could not resolve to a Repository")
        return "[]"

    payload = observe_verdict(run=run)
    assert payload["ok"] is False
    assert payload["error"] == "gh failed; not idle"
    assert payload["failed"] == [
        {"repo": "mikolaj92/Docxtor", "error": "Could not resolve to a Repository"}
    ]
    assert payload["counts"]["pulls"] == 0
    surveyed_ok = payload["counts"]["surveyed"]
    assert surveyed_ok == 3
    _reset_catalog()


def test_fala_package_observe_verdict_after_dual_label() -> None:
    text = (Path(__file__).resolve().parents[1] / "fala-package.toml").read_text(
        encoding="utf-8"
    )
    assert 'command = ["uv", "run", "observe-verdict"]' in text
    assert 'conduction = ["dual_label"]' in text
    assert 'id = "observe_verdict"' in text
    assert 'id = "github.observe_verdict"' in text
    assert "python3" not in text
