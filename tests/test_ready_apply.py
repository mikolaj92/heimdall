from __future__ import annotations

import json
from pathlib import Path

import pytest

from heimdall.craft_ready import issue_body
from heimdall.observe_queue import HEIMDALL, GhError
from heimdall.ready_apply import main, ready_apply

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
        "title": "Promote inbound to work:ready",
        "problem": "An existing complete issue has no mutator that applies work:ready.",
        "scope": "One atom. Do not add this mutator to the Fala monitor path.",
        "repo": "mikolaj92/lokay",
        "acceptance": "`uv run ready-apply --repo OWNER/NAME --issue N` labels work:ready.",
        "constraints": "None",
        "artifact_qa": "PR plus pytest for incomplete, hold, heimdall skip, catalog, gh error.",
        "pri": "pri:p2",
    }
    data.update(overrides)
    return data


def _view(number: int, spec: dict, *label_names: str) -> str:
    return json.dumps(
        {
            "number": number,
            "title": spec["title"],
            "body": issue_body(spec),
            "labels": [{"name": n} for n in label_names],
        }
    )


def test_complete_body_adds_work_ready() -> None:
    spec = _spec(repo=HEIMDALL)
    edits: list[list[str]] = []

    def run(args: list[str]) -> str:
        if args[:1] == ["api"]:
            raise AssertionError("heimdall must not fetch mill catalog")
        if args[:2] == ["issue", "view"]:
            return _view(7, spec, "pri:p2", "bifrost:in")
        if args[:2] == ["issue", "edit"]:
            edits.append(args)
            return ""
        if args[:2] == ["issue", "create"]:
            raise AssertionError("must not create a second issue")
        raise AssertionError(args)

    payload = ready_apply(HEIMDALL, 7, run=run)
    assert payload["ok"] is True
    assert payload["atom"] == "ready-apply"
    assert payload["repo"] == HEIMDALL
    assert payload["issue"] == 7
    assert payload["added"] == ["work:ready"]
    assert payload["already"] == []
    assert "work:ready" in payload["labels"]
    assert "ai:ready" not in payload["added"]
    assert "ai:ready" not in payload["labels"]
    assert edits == [
        [
            "issue",
            "edit",
            "7",
            "-R",
            HEIMDALL,
            "--add-label",
            "work:ready",
        ]
    ]


def test_heimdall_does_not_add_ai_ready_or_fetch_catalog() -> None:
    _reset_catalog()
    spec = _spec(repo=HEIMDALL)
    apis: list[list[str]] = []

    def run(args: list[str]) -> str:
        if args[:1] == ["api"]:
            apis.append(args)
            raise AssertionError("heimdall promote must not fetch mill catalog")
        if args[:2] == ["issue", "view"]:
            return _view(7, spec, "pri:p2")
        if args[:2] == ["issue", "edit"]:
            return ""
        raise AssertionError(args)

    payload = ready_apply(HEIMDALL, 7, run=run)
    assert payload["ok"] is True
    assert "ai:ready" not in payload["added"]
    assert "ai:ready" not in payload.get("already", [])
    assert apis == []
    _reset_catalog()


def test_catalog_adds_work_ready_then_dual_label_ai_ready() -> None:
    _reset_catalog()
    spec = _spec(repo="mikolaj92/lokay")
    labels = ["pri:p2", "bifrost:in"]
    edits: list[list[str]] = []

    def run(args: list[str]) -> str:
        if args[:1] == ["api"]:
            assert "repos.mikolaj92.yaml" in args[-1]
            return CATALOG_YAML
        if args[:2] == ["issue", "view"]:
            return json.dumps(
                {
                    "number": 10,
                    "title": spec["title"],
                    "body": issue_body(spec),
                    "labels": [{"name": n} for n in labels],
                }
            )
        if args[:2] == ["issue", "edit"]:
            edits.append(args)
            lab = args[args.index("--add-label") + 1]
            if lab not in labels:
                labels.append(lab)
            return ""
        if args[:2] == ["issue", "create"]:
            raise AssertionError("must not create a second issue")
        raise AssertionError(args)

    payload = ready_apply("mikolaj92/lokay", 10, run=run)
    assert payload["ok"] is True
    assert payload["atom"] == "ready-apply"
    assert payload["repo"] == "mikolaj92/lokay"
    assert payload["issue"] == 10
    assert payload["added"] == ["work:ready", "ai:ready"]
    assert payload["already"] == []
    assert "work:ready" in payload["labels"]
    assert "ai:ready" in payload["labels"]
    assert [args[args.index("--add-label") + 1] for args in edits] == [
        "work:ready",
        "ai:ready",
    ]
    _reset_catalog()


def test_catalog_calls_dual_label_after_work_ready(monkeypatch: pytest.MonkeyPatch) -> None:
    spec = _spec(repo="mikolaj92/lokay")
    edits: list[list[str]] = []
    dual_calls: list[tuple[str, int]] = []

    def run(args: list[str]) -> str:
        if args[:1] == ["api"]:
            raise AssertionError("ready-apply must not fetch catalog itself")
        if args[:2] == ["issue", "view"]:
            return _view(10, spec, "pri:p2")
        if args[:2] == ["issue", "edit"]:
            edits.append(args)
            return ""
        raise AssertionError(args)

    def fake_dual(repo: str, issue: int, *, heimdall: str = HEIMDALL, run=None):
        dual_calls.append((repo, issue))
        assert edits, "work:ready must be present before dual_label"
        assert edits[0][edits[0].index("--add-label") + 1] == "work:ready"
        return {
            "ok": True,
            "atom": "dual-label-ready",
            "repo": repo,
            "issue": issue,
            "added": ["ai:ready"],
            "already": [],
        }

    monkeypatch.setattr("heimdall.ready_apply.dual_label", fake_dual)
    payload = ready_apply("mikolaj92/lokay", 10, run=run)
    assert payload["ok"] is True
    assert dual_calls == [("mikolaj92/lokay", 10)]
    assert payload["added"] == ["work:ready", "ai:ready"]


def test_incomplete_body_fails_without_edit() -> None:
    spec = _spec(repo=HEIMDALL)
    body = issue_body(spec).replace("### Acceptance\n\n", "### Notes\n\n")
    edits: list[list[str]] = []

    def run(args: list[str]) -> str:
        if args[:2] == ["issue", "view"]:
            return json.dumps(
                {
                    "number": 7,
                    "title": spec["title"],
                    "body": body,
                    "labels": [{"name": "pri:p2"}],
                }
            )
        if args[:2] == ["issue", "edit"]:
            edits.append(args)
            return ""
        raise AssertionError(args)

    payload = ready_apply(HEIMDALL, 7, run=run)
    assert payload["ok"] is False
    assert payload["atom"] == "ready-apply"
    assert "acceptance" in payload["error"]
    assert edits == []


def test_stub_body_fails_without_edit() -> None:
    spec = _spec(repo=HEIMDALL, scope="Lokay will figure it out")
    edits: list[list[str]] = []

    def run(args: list[str]) -> str:
        if args[:2] == ["issue", "view"]:
            return _view(7, spec, "pri:p2")
        if args[:2] == ["issue", "edit"]:
            edits.append(args)
            return ""
        raise AssertionError(args)

    payload = ready_apply(HEIMDALL, 7, run=run)
    assert payload["ok"] is False
    assert "stub" in payload["error"]
    assert edits == []

    spec_tbd = _spec(repo=HEIMDALL, problem="tbd")
    payload = ready_apply(HEIMDALL, 7, run=lambda args: _view(7, spec_tbd, "pri:p2"))
    assert payload["ok"] is False
    assert "stub" in payload["error"]


def test_bifrost_in_with_verdict_hold_fails_without_work_ready() -> None:
    spec = _spec(repo=HEIMDALL)
    edits: list[list[str]] = []

    def run(args: list[str]) -> str:
        if args[:2] == ["issue", "view"]:
            return _view(7, spec, "pri:p2", "bifrost:in", "verdict:hold")
        if args[:2] == ["issue", "edit"]:
            edits.append(args)
            return ""
        raise AssertionError(args)

    payload = ready_apply(HEIMDALL, 7, run=run)
    assert payload["ok"] is False
    assert payload["atom"] == "ready-apply"
    assert "verdict:hold" in payload["error"]
    assert "work:ready" not in payload.get("added", [])
    assert edits == []


def test_already_work_ready_is_idempotent() -> None:
    spec = _spec(repo=HEIMDALL)
    edits: list[list[str]] = []

    def run(args: list[str]) -> str:
        if args[:1] == ["api"]:
            raise AssertionError("heimdall must not fetch mill catalog")
        if args[:2] == ["issue", "view"]:
            return _view(7, spec, "work:ready", "pri:p2", "bifrost:in")
        if args[:2] == ["issue", "edit"]:
            edits.append(args)
            return ""
        raise AssertionError(args)

    payload = ready_apply(HEIMDALL, 7, run=run)
    assert payload["ok"] is True
    assert payload["added"] == []
    assert payload["already"] == ["work:ready"]
    assert "work:ready" in payload["labels"]
    assert edits == []


def test_already_work_ready_still_dual_labels_catalog() -> None:
    _reset_catalog()
    spec = _spec(repo="mikolaj92/lokay")
    labels = ["work:ready", "pri:p2"]
    edits: list[list[str]] = []

    def run(args: list[str]) -> str:
        if args[:1] == ["api"]:
            return CATALOG_YAML
        if args[:2] == ["issue", "view"]:
            return json.dumps(
                {
                    "number": 10,
                    "title": spec["title"],
                    "body": issue_body(spec),
                    "labels": [{"name": n} for n in labels],
                }
            )
        if args[:2] == ["issue", "edit"]:
            edits.append(args)
            lab = args[args.index("--add-label") + 1]
            if lab not in labels:
                labels.append(lab)
            return ""
        raise AssertionError(args)

    payload = ready_apply("mikolaj92/lokay", 10, run=run)
    assert payload["ok"] is True
    assert payload["already"] == ["work:ready"]
    assert payload["added"] == ["ai:ready"]
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


def test_missing_repo_heading_uses_cli_repo() -> None:
    spec = _spec(repo=HEIMDALL)
    chunks = [
        f"### {heading}\n\n{spec[key]}"
        for key, heading in (
            ("problem", "Problem"),
            ("scope", "Scope"),
            ("acceptance", "Acceptance"),
            ("constraints", "Constraints"),
            ("artifact_qa", "Artifact / QA"),
        )
    ]
    body = "\n\n".join(chunks) + "\n"
    edits: list[list[str]] = []

    def run(args: list[str]) -> str:
        if args[:1] == ["api"]:
            raise AssertionError("heimdall must not fetch mill catalog")
        if args[:2] == ["issue", "view"]:
            return json.dumps(
                {
                    "number": 7,
                    "title": spec["title"],
                    "body": body,
                    "labels": [{"name": "pri:p2"}],
                }
            )
        if args[:2] == ["issue", "edit"]:
            edits.append(args)
            return ""
        raise AssertionError(args)

    payload = ready_apply(HEIMDALL, 7, run=run)
    assert payload["ok"] is True
    assert payload["added"] == ["work:ready"]
    assert edits


def test_missing_pri_fails_without_edit() -> None:
    spec = _spec(repo=HEIMDALL)
    edits: list[list[str]] = []

    def run(args: list[str]) -> str:
        if args[:2] == ["issue", "view"]:
            return _view(7, spec, "bifrost:in")
        if args[:2] == ["issue", "edit"]:
            edits.append(args)
            return ""
        raise AssertionError(args)

    payload = ready_apply(HEIMDALL, 7, run=run)
    assert payload["ok"] is False
    assert "pri" in payload["error"]
    assert edits == []


def test_repo_mismatch_fails_closed() -> None:
    spec = _spec(repo="mikolaj92/lokay")
    edits: list[list[str]] = []

    def run(args: list[str]) -> str:
        if args[:2] == ["issue", "view"]:
            return _view(7, spec, "pri:p2")
        if args[:2] == ["issue", "edit"]:
            edits.append(args)
            return ""
        raise AssertionError(args)

    payload = ready_apply(HEIMDALL, 7, run=run)
    assert payload["ok"] is False
    assert payload["error"] == "repo mismatch"
    assert payload["repo"] == HEIMDALL
    assert payload["issue"] == 7
    assert edits == []


def test_gh_view_error_is_not_success() -> None:
    def run(args: list[str]) -> str:
        raise GhError("Could not resolve to an issue")

    payload = ready_apply(HEIMDALL, 7, run=run)
    assert payload["ok"] is False
    assert payload["atom"] == "ready-apply"
    assert payload["error"] == "Could not resolve to an issue"
    assert payload["repo"] == HEIMDALL
    assert payload["issue"] == 7


def test_gh_edit_error_is_not_success() -> None:
    spec = _spec(repo=HEIMDALL)

    def run(args: list[str]) -> str:
        if args[:2] == ["issue", "view"]:
            return _view(7, spec, "pri:p2")
        raise GhError("HTTP 422: Validation Failed")

    payload = ready_apply(HEIMDALL, 7, run=run)
    assert payload["ok"] is False
    assert payload["error"] == "HTTP 422: Validation Failed"
    assert payload["ok"] is not True


def test_invalid_repo_shape_fails_without_gh() -> None:
    def run(args: list[str]) -> str:
        raise AssertionError(f"must not call gh: {args}")

    payload = ready_apply("not-a-repo", 7, run=run)
    assert payload["ok"] is False
    assert "invalid repo" in payload["error"]
    assert payload["repo"] == "not-a-repo"
    assert payload["issue"] == 7


def test_non_catalog_gets_work_ready_only() -> None:
    _reset_catalog()
    spec = _spec(repo="octocat/Hello-World")
    edits: list[list[str]] = []

    def run(args: list[str]) -> str:
        if args[:1] == ["api"]:
            return CATALOG_YAML
        if args[:2] == ["issue", "view"]:
            return _view(1, spec, "pri:p2")
        if args[:2] == ["issue", "edit"]:
            edits.append(args)
            return ""
        raise AssertionError(args)

    payload = ready_apply("octocat/Hello-World", 1, run=run)
    assert payload["ok"] is True
    assert payload["added"] == ["work:ready"]
    assert "ai:ready" not in payload["added"]
    assert [args[args.index("--add-label") + 1] for args in edits] == ["work:ready"]
    _reset_catalog()


def test_catalog_error_after_work_ready_is_not_success() -> None:
    _reset_catalog()
    spec = _spec(repo="mikolaj92/lokay")
    edits: list[list[str]] = []

    def run(args: list[str]) -> str:
        if args[:1] == ["api"]:
            raise GhError("API rate limit")
        if args[:2] == ["issue", "view"]:
            return _view(10, spec, "pri:p2")
        if args[:2] == ["issue", "edit"]:
            edits.append(args)
            return ""
        raise AssertionError(args)

    payload = ready_apply("mikolaj92/lokay", 10, run=run)
    assert payload["ok"] is False
    assert "catalog" in payload["error"]
    assert payload["added"] == ["work:ready"]
    assert edits
    _reset_catalog()


def test_main_help(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        main(["--help"])
    assert exc.value.code == 0
    out = capsys.readouterr().out
    assert "ready-apply" in out
    assert "--repo" in out
    assert "--issue" in out
    assert "--heimdall" in out


def test_fala_package_does_not_include_ready_apply() -> None:
    text = (Path(__file__).resolve().parents[1] / "fala-package.toml").read_text(
        encoding="utf-8"
    )
    assert "ready-apply" not in text
    assert "ready_apply" not in text
    assert 'command = ["uv", "run", "observe-queue"]' in text
    assert 'id = "monitor"' in text
