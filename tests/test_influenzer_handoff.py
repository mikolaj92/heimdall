from __future__ import annotations

import json
from pathlib import Path

from heimdall.influenzer_handoff import (
    DEFAULT_TO,
    handoff,
    parse_story_labels,
)
from heimdall.observe_queue import GhError

STORIES = frozenset(
    {
        "story:major",
        "story:ship",
        "story:explore",
        "story:issue",
        "story:decision",
        "story:failure",
    }
)
ARTIFACT = "https://github.com/mikolaj92/lokay/pull/12"
INFLUENZER_URL = "https://github.com/mikolaj92/influenzer/issues/7"


def _labels(*names: str) -> str:
    return json.dumps({"number": 4, "labels": [{"name": n} for n in names]})


def _created(url: str = INFLUENZER_URL) -> str:
    return url + "\n"


def test_parse_story_labels_from_repo_labels_yml() -> None:
    text = (Path(__file__).resolve().parents[1] / "labels.yml").read_text(
        encoding="utf-8"
    )
    assert parse_story_labels(text) == STORIES


def test_missing_artifact_fails() -> None:
    def run(args: list[str]) -> str:
        raise AssertionError(f"must not call gh: {args}")

    payload = handoff(
        "mikolaj92/lokay",
        issue=4,
        artifact="",
        story="story:ship",
        stories=STORIES,
        run=run,
    )
    assert payload == {
        "ok": False,
        "atom": "influenzer-handoff",
        "error": "missing artifact",
        "from": "mikolaj92/lokay",
        "to": DEFAULT_TO,
        "artifact": "",
    }


def test_non_http_artifact_fails() -> None:
    def run(args: list[str]) -> str:
        raise AssertionError(f"must not call gh: {args}")

    payload = handoff(
        "mikolaj92/lokay",
        issue=4,
        artifact="ftp://example.com/ship",
        story="story:ship",
        stories=STORIES,
        run=run,
    )
    assert payload["ok"] is False
    assert payload["atom"] == "influenzer-handoff"
    assert payload["error"] == "artifact must be an http(s) URL"
    assert payload["artifact"] == "ftp://example.com/ship"


def test_unknown_story_fails() -> None:
    def run(args: list[str]) -> str:
        raise AssertionError(f"must not call gh: {args}")

    payload = handoff(
        "mikolaj92/lokay",
        issue=4,
        artifact=ARTIFACT,
        story="story:vibes",
        stories=STORIES,
        run=run,
    )
    assert payload["ok"] is False
    assert payload["error"] == "unknown story: story:vibes"


def test_source_not_out_and_pass_fails() -> None:
    creates: list[list[str]] = []

    def run(args: list[str]) -> str:
        if args[:1] == ["api"]:
            raise AssertionError("must not fetch mill catalog")
        if args[:2] == ["issue", "edit"] or args[:2] == ["pr", "edit"]:
            raise AssertionError("must not call out-apply")
        if args[:2] == ["issue", "view"]:
            return _labels("bifrost:out", "verdict:hold")
        if args[:2] == ["issue", "create"]:
            creates.append(args)
            return _created()
        raise AssertionError(args)

    payload = handoff(
        "mikolaj92/lokay",
        issue=4,
        artifact=ARTIFACT,
        story="story:ship",
        stories=STORIES,
        run=run,
    )
    assert payload["ok"] is False
    assert payload["atom"] == "influenzer-handoff"
    assert payload["error"] == "source is not bifrost:out + verdict:pass"
    assert creates == []


def test_source_pass_without_out_fails() -> None:
    creates: list[list[str]] = []

    def run(args: list[str]) -> str:
        if args[:2] == ["issue", "view"]:
            return _labels("verdict:pass", "work:ready")
        if args[:2] == ["issue", "create"]:
            creates.append(args)
            return _created()
        raise AssertionError(args)

    payload = handoff(
        "mikolaj92/lokay",
        issue=4,
        artifact=ARTIFACT,
        story="story:ship",
        stories=STORIES,
        run=run,
    )
    assert payload["ok"] is False
    assert payload["error"] == "source is not bifrost:out + verdict:pass"
    assert creates == []


def test_files_influenzer_inbound_without_work_ready() -> None:
    creates: list[list[str]] = []

    def run(args: list[str]) -> str:
        if args[:1] == ["api"]:
            raise AssertionError("must not fetch mill catalog")
        if args[:2] == ["issue", "edit"] or args[:2] == ["pr", "edit"]:
            raise AssertionError("must not call out-apply")
        if args[:2] == ["issue", "view"]:
            return _labels("bifrost:out", "verdict:pass", "story:ship")
        if args[:2] == ["issue", "create"]:
            creates.append(args)
            return _created()
        raise AssertionError(args)

    payload = handoff(
        "mikolaj92/lokay",
        issue=4,
        artifact=ARTIFACT,
        story="story:ship",
        comment="QA passed; sell the ship.",
        stories=STORIES,
        run=run,
    )
    assert payload == {
        "ok": True,
        "atom": "influenzer-handoff",
        "from": "mikolaj92/lokay",
        "to": DEFAULT_TO,
        "issue": 7,
        "url": INFLUENZER_URL.rstrip("\n"),
        "artifact": ARTIFACT,
    }
    assert len(creates) == 1
    create = creates[0]
    assert create[:2] == ["issue", "create"]
    assert create[create.index("-R") + 1] == DEFAULT_TO
    labels: list[str] = []
    i = 0
    while i < len(create):
        if create[i] == "--label":
            labels.append(create[i + 1])
            i += 2
            continue
        i += 1
    assert labels == [
        "bifrost:in",
        "source:github",
        "signal:feedback",
        "verdict:hold",
    ]
    assert "work:ready" not in labels
    assert "ai:ready" not in labels
    assert "story:ship" not in labels
    body = create[create.index("--body") + 1]
    assert "### Signal" in body
    assert "QA passed; sell the ship." in body
    assert "story:ship" in body
    assert ARTIFACT in body
    assert "### Proposed verdict" in body
    assert "verdict:hold" in body
    title = create[create.index("--title") + 1]
    assert "story:ship" in title
    assert "mikolaj92/lokay#4" in title


def test_files_from_pr() -> None:
    creates: list[list[str]] = []

    def run(args: list[str]) -> str:
        if args[:2] == ["pr", "view"]:
            return _labels("bifrost:out", "verdict:pass")
        if args[:2] == ["issue", "create"]:
            creates.append(args)
            return _created()
        if args[:2] == ["issue", "edit"] or args[:2] == ["pr", "edit"]:
            raise AssertionError("must not call out-apply")
        raise AssertionError(args)

    payload = handoff(
        "mikolaj92/heimdall",
        pr=9,
        artifact=ARTIFACT,
        story="story:ship",
        stories=STORIES,
        run=run,
    )
    assert payload["ok"] is True
    assert payload["issue"] == 7
    assert "pr" not in payload
    assert creates[0][creates[0].index("-R") + 1] == DEFAULT_TO
    body = creates[0][creates[0].index("--body") + 1]
    assert "https://github.com/mikolaj92/heimdall/pull/9" in body


def test_to_repo_override() -> None:
    creates: list[list[str]] = []

    def run(args: list[str]) -> str:
        if args[:2] == ["issue", "view"]:
            return _labels("bifrost:out", "verdict:pass")
        if args[:2] == ["issue", "create"]:
            creates.append(args)
            return "https://github.com/acme/influenzer/issues/2\n"
        raise AssertionError(args)

    payload = handoff(
        "mikolaj92/lokay",
        issue=4,
        artifact=ARTIFACT,
        story="story:ship",
        to_repo="acme/influenzer",
        stories=STORIES,
        run=run,
    )
    assert payload["ok"] is True
    assert payload["to"] == "acme/influenzer"
    assert payload["issue"] == 2
    assert creates[0][creates[0].index("-R") + 1] == "acme/influenzer"


def test_gh_error_fail_closed() -> None:
    def run(args: list[str]) -> str:
        if args[:2] == ["issue", "view"]:
            raise GhError("Could not resolve to an issue")
        raise AssertionError(args)

    payload = handoff(
        "mikolaj92/lokay",
        issue=99,
        artifact=ARTIFACT,
        story="story:ship",
        stories=STORIES,
        run=run,
    )
    assert payload["ok"] is False
    assert payload["atom"] == "influenzer-handoff"
    assert payload["error"] == "Could not resolve to an issue"
    assert "issue" not in payload
    assert "url" not in payload


def test_create_gh_error_fail_closed() -> None:
    creates: list[list[str]] = []

    def run(args: list[str]) -> str:
        if args[:2] == ["issue", "view"]:
            return _labels("bifrost:out", "verdict:pass")
        if args[:2] == ["issue", "create"]:
            creates.append(args)
            raise GhError("HTTP 422: Validation Failed")
        raise AssertionError(args)

    payload = handoff(
        "mikolaj92/lokay",
        issue=4,
        artifact=ARTIFACT,
        story="story:ship",
        stories=STORIES,
        run=run,
    )
    assert payload["ok"] is False
    assert payload["error"] == "HTTP 422: Validation Failed"
    assert payload["from"] == "mikolaj92/lokay"
    assert payload["to"] == DEFAULT_TO
    assert "issue" not in payload
    assert creates


def test_fala_package_does_not_include_influenzer_handoff() -> None:
    text = (Path(__file__).resolve().parents[1] / "fala-package.toml").read_text(
        encoding="utf-8"
    )
    assert "influenzer-handoff" not in text
    assert "influenzer_handoff" not in text
    assert 'id = "monitor"' in text
    assert 'command = ["uv", "run", "observe-queue"]' in text
