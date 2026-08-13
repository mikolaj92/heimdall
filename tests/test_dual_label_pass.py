from __future__ import annotations

import json
from pathlib import Path

from heimdall.dual_label_pass import dual_label_pass
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


def _issue(number: int, labels: list[str]) -> dict:
    return {
        "number": number,
        "title": f"issue {number}",
        "labels": [{"name": n} for n in labels],
        "url": f"https://github.com/example/repo/issues/{number}",
    }


def test_pass_dual_labels_catalog_work_ready_only() -> None:
    _reset_catalog()
    edits: list[list[str]] = []
    listed: list[str] = []
    viewed: list[tuple[str, str]] = []

    def run(args: list[str]) -> str:
        if args[:1] == ["api"]:
            return CATALOG_YAML
        if args[:2] == ["issue", "list"]:
            repo = args[args.index("-R") + 1]
            listed.append(repo)
            if repo == "mikolaj92/lokay":
                return json.dumps(
                    [
                        _issue(10, ["work:ready", "pri:p2"]),
                        _issue(11, ["work:doing"]),
                        _issue(12, ["work:ready", "ai:ready"]),
                        _issue(13, ["ai:ready"]),
                    ]
                )
            if repo == "mikolaj92/Docxtor":
                return json.dumps([_issue(1, ["work:ready"])])
            return "[]"
        if args[:2] == ["issue", "view"]:
            repo = args[args.index("-R") + 1]
            number = args[2]
            viewed.append((repo, number))
            if repo == "mikolaj92/lokay" and number == "10":
                return json.dumps(
                    {"number": 10, "labels": [{"name": "work:ready"}, {"name": "pri:p2"}]}
                )
            if repo == "mikolaj92/lokay" and number == "12":
                return json.dumps(
                    {
                        "number": 12,
                        "labels": [{"name": "work:ready"}, {"name": "ai:ready"}],
                    }
                )
            if repo == "mikolaj92/Docxtor" and number == "1":
                return json.dumps({"number": 1, "labels": [{"name": "work:ready"}]})
            raise AssertionError(args)
        if args[:2] == ["issue", "edit"]:
            edits.append(args)
            return ""
        raise AssertionError(args)

    payload = dual_label_pass(run=run)
    assert payload["ok"] is True
    assert payload["atom"] == "dual-label-pass"
    assert HEIMDALL not in payload["catalog"]
    assert HEIMDALL not in listed
    assert payload["added"] == [
        {"repo": "mikolaj92/lokay", "issue": 10, "added": ["ai:ready"]},
        {"repo": "mikolaj92/Docxtor", "issue": 1, "added": ["ai:ready"]},
    ]
    assert payload["already"] == [
        {"repo": "mikolaj92/lokay", "issue": 12, "already": ["ai:ready"]},
    ]
    assert payload["counts"]["considered"] == 3
    assert payload["counts"]["added"] == 2
    assert payload["counts"]["already"] == 1
    assert viewed == [
        ("mikolaj92/lokay", "10"),
        ("mikolaj92/lokay", "12"),
        ("mikolaj92/Docxtor", "1"),
    ]
    assert edits == [
        [
            "issue",
            "edit",
            "10",
            "-R",
            "mikolaj92/lokay",
            "--add-label",
            "ai:ready",
        ],
        [
            "issue",
            "edit",
            "1",
            "-R",
            "mikolaj92/Docxtor",
            "--add-label",
            "ai:ready",
        ],
    ]
    _reset_catalog()


def test_pass_skips_heimdall(monkeypatch) -> None:
    _reset_catalog()
    listed: list[str] = []
    edits: list[list[str]] = []

    monkeypatch.setattr(
        "heimdall.dual_label_pass.fetch_catalog",
        lambda *, run, exclude="": [HEIMDALL, "mikolaj92/lokay"],
    )

    def run(args: list[str]) -> str:
        if args[:1] == ["api"]:
            return CATALOG_YAML
        if args[:2] == ["issue", "list"]:
            repo = args[args.index("-R") + 1]
            listed.append(repo)
            assert repo != HEIMDALL
            return json.dumps([_issue(10, ["work:ready"])])
        if args[:2] == ["issue", "view"]:
            repo = args[args.index("-R") + 1]
            assert repo != HEIMDALL
            return json.dumps({"number": 10, "labels": [{"name": "work:ready"}]})
        if args[:2] == ["issue", "edit"]:
            edits.append(args)
            assert HEIMDALL not in args
            return ""
        raise AssertionError(args)

    payload = dual_label_pass(run=run)
    assert payload["ok"] is True
    assert payload["skipped"] == [{"repo": HEIMDALL, "skipped": "heimdall"}]
    assert listed == ["mikolaj92/lokay"]
    assert payload["added"] == [
        {"repo": "mikolaj92/lokay", "issue": 10, "added": ["ai:ready"]}
    ]
    assert all(HEIMDALL not in args for args in edits)
    _reset_catalog()


def test_pass_catalog_error_fails_closed() -> None:
    _reset_catalog()

    def run(args: list[str]) -> str:
        raise GhError("API rate limit")

    payload = dual_label_pass(run=run)
    assert payload["ok"] is False
    assert payload["atom"] == "dual-label-pass"
    assert "catalog" in payload["error"]
    assert "added" not in payload
    _reset_catalog()


def test_pass_repo_list_error_fails_closed() -> None:
    _reset_catalog()
    edits: list[list[str]] = []

    def run(args: list[str]) -> str:
        if args[:1] == ["api"]:
            return CATALOG_YAML
        if args[:2] == ["issue", "list"]:
            repo = args[args.index("-R") + 1]
            if repo == "mikolaj92/Docxtor":
                raise GhError("Could not resolve to a Repository")
            return "[]"
        if args[:2] == ["issue", "edit"]:
            edits.append(args)
            return ""
        raise AssertionError(args)

    payload = dual_label_pass(run=run)
    assert payload["ok"] is False
    assert payload["error"] == "gh failed; not idle"
    assert payload["failed"] == [
        {"repo": "mikolaj92/Docxtor", "error": "Could not resolve to a Repository"}
    ]
    assert edits == []
    _reset_catalog()


def test_pass_dual_label_error_fails_closed() -> None:
    _reset_catalog()
    edits: list[list[str]] = []

    def run(args: list[str]) -> str:
        if args[:1] == ["api"]:
            return CATALOG_YAML
        if args[:2] == ["issue", "list"]:
            repo = args[args.index("-R") + 1]
            if repo == "mikolaj92/lokay":
                return json.dumps([_issue(10, ["work:ready"])])
            return "[]"
        if args[:2] == ["issue", "view"]:
            raise GhError("Could not resolve to an issue")
        if args[:2] == ["issue", "edit"]:
            edits.append(args)
            return ""
        raise AssertionError(args)

    payload = dual_label_pass(run=run)
    assert payload["ok"] is False
    assert payload["error"] == "gh failed; not idle"
    assert payload["failed"] == [
        {
            "repo": "mikolaj92/lokay",
            "issue": 10,
            "error": "Could not resolve to an issue",
        }
    ]
    assert edits == []
    _reset_catalog()


def test_fala_package_declares_monitor_path() -> None:
    text = (Path(__file__).resolve().parents[1] / "fala-package.toml").read_text(
        encoding="utf-8"
    )
    assert 'version = "2"' in text
    assert 'id = "monitor"' in text
    assert 'command = ["uv", "run", "observe-queue"]' in text
    assert 'command = ["uv", "run", "dual-label-pass"]' in text
    assert 'conduction = ["observe"]' in text
    assert "python3" not in text


def test_write_fala_result_when_hosted(tmp_path, monkeypatch) -> None:
    from heimdall.observe_queue import write_fala_result

    monkeypatch.setenv("FALA_EFFECTOR_OUTPUT_DIR", str(tmp_path))
    write_fala_result({"ok": True, "atom": "dual-label-pass"}, kind="github.dual_label")
    data = json.loads((tmp_path / "result.json").read_text(encoding="utf-8"))
    assert data["values"]["atom"] == "dual-label-pass"
    assert data["reactions"][0]["kind"] == "github.dual_label"
