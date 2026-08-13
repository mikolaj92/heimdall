from __future__ import annotations

from pathlib import Path

from heimdall.craft_ready import craft_from_text, craft_ready, issue_body
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


def _spec(**overrides: object) -> dict:
    data: dict = {
        "title": "Add craft-ready atom",
        "problem": "Heimdall has no kit atom that files a complete work:ready issue.",
        "scope": "One atom. Do not add this mutator to the Fala monitor path.",
        "repo": "mikolaj92/lokay",
        "acceptance": "`uv run craft-ready --file spec.json` creates the issue.",
        "constraints": "None",
        "artifact_qa": "PR plus pytest for missing field, heimdall skip, catalog, gh error.",
        "pri": "pri:p2",
    }
    data.update(overrides)
    return data


def test_missing_field_fails() -> None:
    calls: list[list[str]] = []

    def run(args: list[str]) -> str:
        calls.append(args)
        raise AssertionError("must not call gh when a field is missing")

    spec = _spec()
    del spec["acceptance"]
    payload = craft_ready(spec, run=run)
    assert payload["ok"] is False
    assert payload["atom"] == "craft-ready"
    assert "acceptance" in payload["error"]
    assert calls == []

    empty = _spec(problem="  ")
    payload = craft_ready(empty, run=run)
    assert payload["ok"] is False
    assert "problem" in payload["error"]

    stub = _spec(scope="Lokay will figure it out")
    payload = craft_ready(stub, run=run)
    assert payload["ok"] is False
    assert "stub" in payload["error"]
    assert calls == []


def test_heimdall_skip_ai_ready() -> None:
    _reset_catalog()
    creates: list[list[str]] = []

    def run(args: list[str]) -> str:
        if args[:1] == ["api"]:
            raise AssertionError("heimdall must not fetch mill catalog")
        if args[:2] == ["issue", "create"]:
            creates.append(args)
            assert "ai:ready" not in args
            return "https://github.com/mikolaj92/heimdall/issues/7\n"
        raise AssertionError(args)

    payload = craft_ready(_spec(repo=HEIMDALL), run=run)
    assert payload["ok"] is True
    assert payload["atom"] == "craft-ready"
    assert payload["repo"] == HEIMDALL
    assert payload["issue"] == 7
    assert payload["url"] == "https://github.com/mikolaj92/heimdall/issues/7"
    assert payload["labels"] == [
        "work:ready",
        "pri:p2",
        "bifrost:in",
        "verdict:pass",
    ]
    assert "ai:ready" not in payload["labels"]
    assert creates
    assert "--label" in creates[0]
    assert "ai:ready" not in creates[0]
    _reset_catalog()


def test_catalog_gets_ai_ready() -> None:
    _reset_catalog()
    creates: list[list[str]] = []

    def run(args: list[str]) -> str:
        if args[:1] == ["api"]:
            assert "repos.mikolaj92.yaml" in args[-1]
            return CATALOG_YAML
        if args[:2] == ["issue", "create"]:
            creates.append(args)
            return "https://github.com/mikolaj92/lokay/issues/42\n"
        raise AssertionError(args)

    payload = craft_ready(_spec(repo="mikolaj92/lokay"), run=run)
    assert payload["ok"] is True
    assert payload["atom"] == "craft-ready"
    assert payload["repo"] == "mikolaj92/lokay"
    assert payload["issue"] == 42
    assert payload["url"] == "https://github.com/mikolaj92/lokay/issues/42"
    assert payload["labels"] == [
        "work:ready",
        "pri:p2",
        "bifrost:in",
        "verdict:pass",
        "ai:ready",
    ]
    assert creates[0][creates[0].index("-R") + 1] == "mikolaj92/lokay"
    assert "ai:ready" in creates[0]
    assert "work:ready" in creates[0]
    body = creates[0][creates[0].index("--body") + 1]
    assert "### Problem" in body
    assert "### Artifact / QA" in body
    _reset_catalog()


def test_gh_error_fail_closed() -> None:
    _reset_catalog()
    creates: list[list[str]] = []

    def run(args: list[str]) -> str:
        if args[:1] == ["api"]:
            return CATALOG_YAML
        if args[:2] == ["issue", "create"]:
            creates.append(args)
            raise GhError("HTTP 422: Validation Failed")
        raise AssertionError(args)

    payload = craft_ready(_spec(), run=run)
    assert payload["ok"] is False
    assert payload["atom"] == "craft-ready"
    assert payload["error"] == "HTTP 422: Validation Failed"
    assert payload["repo"] == "mikolaj92/lokay"
    assert "issue" not in payload
    assert "url" not in payload
    assert creates
    _reset_catalog()


def test_catalog_error_fails_closed_before_create() -> None:
    _reset_catalog()
    creates: list[list[str]] = []

    def run(args: list[str]) -> str:
        if args[:2] == ["issue", "create"]:
            creates.append(args)
            return "https://github.com/mikolaj92/lokay/issues/1\n"
        raise GhError("API rate limit")

    payload = craft_ready(_spec(), run=run)
    assert payload["ok"] is False
    assert "catalog" in payload["error"]
    assert creates == []
    _reset_catalog()


def test_issue_body_matches_work_ready_headings() -> None:
    body = issue_body(_spec())
    for heading in (
        "### Problem",
        "### Scope",
        "### Repo",
        "### Acceptance",
        "### Constraints",
        "### Artifact / QA",
    ):
        assert heading in body


def test_craft_from_text_invalid_json() -> None:
    payload = craft_from_text("not-json")
    assert payload["ok"] is False
    assert "invalid json" in payload["error"]


def test_fala_package_does_not_include_craft_ready() -> None:
    text = (Path(__file__).resolve().parents[1] / "fala-package.toml").read_text(
        encoding="utf-8"
    )
    assert "craft-ready" not in text
    assert "craft_ready" not in text
    assert 'command = ["uv", "run", "observe-queue"]' in text
    assert 'id = "monitor"' in text
