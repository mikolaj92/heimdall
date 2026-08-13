from __future__ import annotations

import json
from pathlib import Path

from heimdall.observe_queue import GhError
from heimdall.out_apply import apply_out, parse_bifrost_labels
from heimdall.verdict_apply import parse_verdict_labels

BIFROST = frozenset({"bifrost:in", "bifrost:out"})
VERDICTS = frozenset(
    {
        "verdict:pass",
        "verdict:hold",
        "verdict:reject",
        "verdict:needs-scout",
    }
)
ARTIFACT = "https://github.com/mikolaj92/lokay/pull/12"

LABELS_YML = """\
namespaces:
  - name: bifrost
    labels:
      - name: bifrost:in
      - name: bifrost:out
  - name: verdict
    labels:
      - name: verdict:pass
      - name: verdict:hold
      - name: verdict:reject
      - name: verdict:needs-scout
  - name: work
    labels:
      - name: work:ready
"""


def _labels(*names: str) -> str:
    return json.dumps({"number": 4, "labels": [{"name": n} for n in names]})


def test_parse_bifrost_labels_from_taxonomy() -> None:
    assert parse_bifrost_labels(LABELS_YML) == BIFROST
    assert parse_verdict_labels(LABELS_YML) == VERDICTS


def test_parse_bifrost_labels_from_repo_labels_yml() -> None:
    text = (Path(__file__).resolve().parents[1] / "labels.yml").read_text(
        encoding="utf-8"
    )
    assert parse_bifrost_labels(text) == BIFROST


def test_missing_artifact_fails() -> None:
    def run(args: list[str]) -> str:
        raise AssertionError(f"must not call gh: {args}")

    payload = apply_out(
        "mikolaj92/heimdall",
        issue=4,
        artifact="",
        bifrost_allowed=BIFROST,
        verdict_allowed=VERDICTS,
        run=run,
    )
    assert payload == {
        "ok": False,
        "atom": "out-apply",
        "error": "missing artifact",
        "repo": "mikolaj92/heimdall",
        "issue": 4,
        "artifact": "",
        "added": [],
        "removed": [],
    }


def test_missing_artifact_none_fails() -> None:
    def run(args: list[str]) -> str:
        raise AssertionError(f"must not call gh: {args}")

    payload = apply_out(
        "mikolaj92/heimdall",
        issue=4,
        bifrost_allowed=BIFROST,
        verdict_allowed=VERDICTS,
        run=run,
    )
    assert payload["ok"] is False
    assert payload["error"] == "missing artifact"


def test_non_http_artifact_fails() -> None:
    def run(args: list[str]) -> str:
        raise AssertionError(f"must not call gh: {args}")

    payload = apply_out(
        "mikolaj92/heimdall",
        issue=4,
        artifact="ftp://example.com/ship",
        bifrost_allowed=BIFROST,
        verdict_allowed=VERDICTS,
        run=run,
    )
    assert payload["ok"] is False
    assert payload["error"] == "artifact must be an http(s) URL"
    assert payload["added"] == []
    assert payload["removed"] == []


def test_applies_out_and_pass() -> None:
    edits: list[list[str]] = []

    def run(args: list[str]) -> str:
        if args[:1] == ["api"]:
            raise AssertionError("must not fetch mill catalog")
        if args[:2] == ["issue", "view"]:
            return _labels("work:ready", "pri:p2")
        if args[:2] == ["issue", "edit"]:
            edits.append(args)
            return ""
        raise AssertionError(args)

    payload = apply_out(
        "mikolaj92/heimdall",
        issue=4,
        artifact=ARTIFACT,
        bifrost_allowed=BIFROST,
        verdict_allowed=VERDICTS,
        run=run,
    )
    assert payload == {
        "ok": True,
        "atom": "out-apply",
        "repo": "mikolaj92/heimdall",
        "issue": 4,
        "artifact": ARTIFACT,
        "added": ["bifrost:out", "verdict:pass"],
        "removed": [],
    }
    assert edits == [
        [
            "issue",
            "edit",
            "4",
            "-R",
            "mikolaj92/heimdall",
            "--add-label",
            "bifrost:out",
            "--add-label",
            "verdict:pass",
        ]
    ]


def test_replaces_hold() -> None:
    edits: list[list[str]] = []

    def run(args: list[str]) -> str:
        if args[:1] == ["api"]:
            raise AssertionError("must not fetch mill catalog")
        if args[:2] == ["issue", "view"]:
            return _labels("bifrost:in", "verdict:hold", "work:ready")
        if args[:2] == ["issue", "edit"]:
            edits.append(args)
            return ""
        raise AssertionError(args)

    payload = apply_out(
        "mikolaj92/heimdall",
        issue=4,
        artifact=ARTIFACT,
        bifrost_allowed=BIFROST,
        verdict_allowed=VERDICTS,
        run=run,
    )
    assert payload["ok"] is True
    assert payload["atom"] == "out-apply"
    assert payload["added"] == ["bifrost:out", "verdict:pass"]
    assert payload["removed"] == ["bifrost:in", "verdict:hold"]
    assert payload["artifact"] == ARTIFACT
    assert edits == [
        [
            "issue",
            "edit",
            "4",
            "-R",
            "mikolaj92/heimdall",
            "--add-label",
            "bifrost:out",
            "--add-label",
            "verdict:pass",
            "--remove-label",
            "bifrost:in",
            "--remove-label",
            "verdict:hold",
        ]
    ]


def test_unknown_target_fails_closed() -> None:
    def run(args: list[str]) -> str:
        raise GhError("Could not resolve to an issue")

    payload = apply_out(
        "mikolaj92/heimdall",
        issue=99,
        artifact=ARTIFACT,
        bifrost_allowed=BIFROST,
        verdict_allowed=VERDICTS,
        run=run,
    )
    assert payload["ok"] is False
    assert payload["atom"] == "out-apply"
    assert payload["error"] == "Could not resolve to an issue"
    assert payload["repo"] == "mikolaj92/heimdall"
    assert payload["issue"] == 99
    assert payload["artifact"] == ARTIFACT
    assert payload["added"] == []
    assert payload["removed"] == []


def test_applies_on_pr() -> None:
    edits: list[list[str]] = []

    def run(args: list[str]) -> str:
        if args[:1] == ["api"]:
            raise AssertionError("must not fetch mill catalog")
        if args[:2] == ["pr", "view"]:
            return _labels("verdict:hold", "bifrost:out")
        if args[:2] == ["pr", "edit"]:
            edits.append(args)
            return ""
        raise AssertionError(args)

    payload = apply_out(
        "mikolaj92/lokay",
        pr=9,
        artifact=ARTIFACT,
        bifrost_allowed=BIFROST,
        verdict_allowed=VERDICTS,
        run=run,
    )
    assert payload["ok"] is True
    assert payload["pr"] == 9
    assert "issue" not in payload
    assert payload["added"] == ["verdict:pass"]
    assert payload["removed"] == ["verdict:hold"]
    assert edits == [
        [
            "pr",
            "edit",
            "9",
            "-R",
            "mikolaj92/lokay",
            "--add-label",
            "verdict:pass",
            "--remove-label",
            "verdict:hold",
        ]
    ]


def test_comment_after_apply() -> None:
    calls: list[list[str]] = []

    def run(args: list[str]) -> str:
        calls.append(args)
        if args[:2] == ["issue", "view"]:
            return _labels("verdict:hold")
        if args[:2] == ["issue", "edit"]:
            return ""
        if args[:2] == ["issue", "comment"]:
            return ""
        raise AssertionError(args)

    payload = apply_out(
        "mikolaj92/heimdall",
        issue=4,
        artifact=ARTIFACT,
        comment="QA pass",
        bifrost_allowed=BIFROST,
        verdict_allowed=VERDICTS,
        run=run,
    )
    assert payload["ok"] is True
    assert [
        "issue",
        "comment",
        "4",
        "-R",
        "mikolaj92/heimdall",
        "--body",
        "QA pass",
    ] in calls


def test_fala_package_does_not_include_out_apply() -> None:
    text = (Path(__file__).resolve().parents[1] / "fala-package.toml").read_text(
        encoding="utf-8"
    )
    assert "out-apply" not in text
    assert "out_apply" not in text
    assert 'id = "monitor"' in text
    assert 'command = ["uv", "run", "observe-queue"]' in text
