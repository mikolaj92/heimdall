from __future__ import annotations

import json

from heimdall.dual_label_ready import dual_label
from heimdall.observe_queue import HEIMDALL, GhError, parse_catalog

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


def test_parse_catalog_excludes_heimdall() -> None:
    names = parse_catalog(CATALOG_YAML)
    assert names == [
        "mikolaj92/lokay",
        "mikolaj92/Docxtor",
        "mikolaj92/reviewkit",
    ]
    assert HEIMDALL not in names
    assert "mikolaj92/heimdall" not in names


def test_skip_heimdall_repo() -> None:
    _reset_catalog()
    calls: list[list[str]] = []

    def run(args: list[str]) -> str:
        calls.append(args)
        raise AssertionError("heimdall skip must not call gh")

    payload = dual_label(HEIMDALL, 7, run=run)
    assert payload["ok"] is True
    assert payload["atom"] == "dual-label-ready"
    assert payload["repo"] == HEIMDALL
    assert payload["issue"] == 7
    assert payload["skipped"] == "heimdall"
    assert payload["added"] == []
    assert payload["already"] == []
    assert calls == []
    _reset_catalog()


def test_add_ai_ready_when_work_ready_on_catalog() -> None:
    _reset_catalog()
    edits: list[list[str]] = []

    def run(args: list[str]) -> str:
        if args[:1] == ["api"]:
            return CATALOG_YAML
        if args[:2] == ["issue", "view"]:
            return json.dumps(
                {
                    "number": 10,
                    "labels": [{"name": "work:ready"}, {"name": "pri:p2"}],
                }
            )
        if args[:2] == ["issue", "edit"]:
            edits.append(args)
            return ""
        raise AssertionError(args)

    payload = dual_label("mikolaj92/lokay", 10, run=run)
    assert payload["ok"] is True
    assert payload["atom"] == "dual-label-ready"
    assert payload["repo"] == "mikolaj92/lokay"
    assert payload["issue"] == 10
    assert payload["added"] == ["ai:ready"]
    assert payload["already"] == []
    assert edits == [
        [
            "issue",
            "edit",
            "10",
            "-R",
            "mikolaj92/lokay",
            "--add-label",
            "ai:ready",
        ]
    ]
    _reset_catalog()


def test_noop_if_ai_ready_already() -> None:
    _reset_catalog()
    edits: list[list[str]] = []

    def run(args: list[str]) -> str:
        if args[:1] == ["api"]:
            return CATALOG_YAML
        if args[:2] == ["issue", "view"]:
            return json.dumps(
                {
                    "number": 10,
                    "labels": [{"name": "work:ready"}, {"name": "ai:ready"}],
                }
            )
        if args[:2] == ["issue", "edit"]:
            edits.append(args)
            return ""
        raise AssertionError(args)

    payload = dual_label("mikolaj92/lokay", 10, run=run)
    assert payload["ok"] is True
    assert payload["added"] == []
    assert payload["already"] == ["ai:ready"]
    assert edits == []
    _reset_catalog()


def test_refuse_non_catalog_repo() -> None:
    _reset_catalog()

    def run(args: list[str]) -> str:
        if args[:1] == ["api"]:
            return CATALOG_YAML
        raise AssertionError("must not touch issues on a non-catalog repo")

    payload = dual_label("octocat/Hello-World", 1, run=run)
    assert payload["ok"] is False
    assert payload["atom"] == "dual-label-ready"
    assert payload["repo"] == "octocat/Hello-World"
    assert payload["issue"] == 1
    assert payload["error"] == "not a mill-catalog repo"
    assert payload["added"] == []
    assert payload["already"] == []
    _reset_catalog()


def test_missing_work_ready_fails_closed() -> None:
    _reset_catalog()
    edits: list[list[str]] = []

    def run(args: list[str]) -> str:
        if args[:1] == ["api"]:
            return CATALOG_YAML
        if args[:2] == ["issue", "view"]:
            return json.dumps({"number": 10, "labels": [{"name": "pri:p2"}]})
        if args[:2] == ["issue", "edit"]:
            edits.append(args)
            return ""
        raise AssertionError(args)

    payload = dual_label("mikolaj92/lokay", 10, run=run)
    assert payload["ok"] is False
    assert payload["error"] == "missing work:ready"
    assert edits == []
    _reset_catalog()


def test_catalog_error_fails_closed() -> None:
    _reset_catalog()

    def run(args: list[str]) -> str:
        raise GhError("API rate limit")

    payload = dual_label("mikolaj92/lokay", 10, run=run)
    assert payload["ok"] is False
    assert "catalog" in payload["error"]
    _reset_catalog()


def test_issue_view_error_fails_closed() -> None:
    _reset_catalog()

    def run(args: list[str]) -> str:
        if args[:1] == ["api"]:
            return CATALOG_YAML
        raise GhError("Could not resolve to an issue")

    payload = dual_label("mikolaj92/lokay", 10, run=run)
    assert payload["ok"] is False
    assert payload["error"] == "Could not resolve to an issue"
    assert payload["added"] == []
    _reset_catalog()
