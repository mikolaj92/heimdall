from __future__ import annotations

import json
from pathlib import Path

import pytest

from heimdall.cleared_close import (
    DEFAULT_TO,
    cleared_close,
    main,
    pointer_comment,
)
from heimdall.observe_queue import GhError

SOURCE = "mikolaj92/lokay"
URL = "https://github.com/mikolaj92/lokay/issues/4"
HANDOFF_URL = "https://github.com/mikolaj92/influenzer/issues/7"


def _view(
    number: int,
    state: str,
    *names: str,
    url: str | None = None,
) -> str:
    return json.dumps(
        {
            "number": number,
            "state": state,
            "labels": [{"name": n} for n in names],
            "url": url or f"https://github.com/mikolaj92/lokay/issues/{number}",
        }
    )


def _repo_of(args: list[str]) -> str:
    return args[args.index("-R") + 1]


def test_out_and_pass_closes_with_pointer() -> None:
    closes: list[list[str]] = []

    def run(args: list[str]) -> str:
        if args[:1] == ["api"]:
            raise AssertionError("must not fetch mill catalog")
        if args[:2] == ["issue", "view"]:
            number = int(args[2])
            repo = _repo_of(args)
            if number == 4 and repo == SOURCE:
                return _view(
                    4, "OPEN", "bifrost:out", "verdict:pass", "work:ready", url=URL
                )
            if number == 7 and repo == DEFAULT_TO:
                return _view(7, "OPEN", "bifrost:in", url=HANDOFF_URL)
            raise AssertionError(args)
        if args[:2] == ["issue", "close"]:
            closes.append(args)
            return ""
        if args[:2] == ["issue", "create"]:
            raise AssertionError("must not call influenzer-handoff")
        if args[:2] == ["issue", "edit"]:
            raise AssertionError("must not call out-apply")
        if args[:2] == ["pr", "close"]:
            raise AssertionError("must not close PRs")
        if args[:2] == ["issue", "comment"]:
            raise AssertionError("prefer issue close --comment")
        raise AssertionError(args)

    payload = cleared_close(SOURCE, 4, 7, run=run)
    assert payload == {
        "ok": True,
        "atom": "cleared-close",
        "repo": SOURCE,
        "issue": 4,
        "handoff": 7,
        "to_repo": DEFAULT_TO,
        "closed": True,
        "already": [],
        "url": URL,
    }
    assert len(closes) == 1
    assert closes[0][:5] == ["issue", "close", "4", "-R", SOURCE]
    comment = closes[0][closes[0].index("--comment") + 1]
    assert comment == "Handed off to mikolaj92/influenzer#7. Closed cleared outbound."
    assert "work:ready" not in closes[0]
    assert "ai:ready" not in closes[0]


def test_already_closed_is_idempotent() -> None:
    closes: list[list[str]] = []

    def run(args: list[str]) -> str:
        if args[:1] == ["api"]:
            raise AssertionError("must not fetch mill catalog")
        if args[:2] == ["issue", "view"]:
            number = int(args[2])
            if number == 4:
                return _view(4, "CLOSED", "bifrost:out", "verdict:pass", url=URL)
            raise AssertionError("must not view handoff when source is closed")
        if args[:2] == ["issue", "close"]:
            closes.append(args)
            return ""
        if args[:2] == ["issue", "comment"]:
            raise AssertionError("must not require a second comment")
        raise AssertionError(args)

    payload = cleared_close(SOURCE, 4, 7, run=run)
    assert payload["ok"] is True
    assert payload["atom"] == "cleared-close"
    assert payload["closed"] is False
    assert payload["already"] == ["closed"]
    assert payload["url"] == URL
    assert payload["handoff"] == 7
    assert payload["to_repo"] == DEFAULT_TO
    assert closes == []


def test_out_without_pass_fails_without_close() -> None:
    closes: list[list[str]] = []

    def run(args: list[str]) -> str:
        if args[:2] == ["issue", "view"]:
            return _view(4, "OPEN", "bifrost:out", "verdict:hold")
        if args[:2] == ["issue", "close"]:
            closes.append(args)
            return ""
        raise AssertionError(args)

    payload = cleared_close(SOURCE, 4, 7, run=run)
    assert payload["ok"] is False
    assert payload["atom"] == "cleared-close"
    assert payload["error"] == "missing verdict:pass"
    assert payload["repo"] == SOURCE
    assert payload["issue"] == 4
    assert closes == []


def test_pass_without_out_fails_without_close() -> None:
    closes: list[list[str]] = []

    def run(args: list[str]) -> str:
        if args[:2] == ["issue", "view"]:
            return _view(4, "OPEN", "verdict:pass", "work:ready")
        if args[:2] == ["issue", "close"]:
            closes.append(args)
            return ""
        raise AssertionError(args)

    payload = cleared_close(SOURCE, 4, 7, run=run)
    assert payload["ok"] is False
    assert payload["error"] == "missing bifrost:out"
    assert closes == []


def test_work_ready_with_out_and_pass_is_allowed() -> None:
    closes: list[list[str]] = []

    def run(args: list[str]) -> str:
        if args[:2] == ["issue", "view"]:
            number = int(args[2])
            repo = _repo_of(args)
            if number == 4 and repo == SOURCE:
                return _view(4, "OPEN", "bifrost:out", "verdict:pass", "work:ready", url=URL)
            if number == 7 and repo == DEFAULT_TO:
                return _view(7, "OPEN", "bifrost:in", url=HANDOFF_URL)
            raise AssertionError(args)
        if args[:2] == ["issue", "close"]:
            closes.append(args)
            return ""
        raise AssertionError(args)

    payload = cleared_close(SOURCE, 4, 7, run=run)
    assert payload["ok"] is True
    assert payload["closed"] is True
    assert len(closes) == 1


def test_missing_handoff_does_not_close() -> None:
    closes: list[list[str]] = []

    def run(args: list[str]) -> str:
        if args[:1] == ["api"]:
            raise AssertionError("must not fetch mill catalog")
        if args[:2] == ["issue", "view"]:
            number = int(args[2])
            repo = _repo_of(args)
            if number == 4 and repo == SOURCE:
                return _view(4, "OPEN", "bifrost:out", "verdict:pass", url=URL)
            if number == 7 and repo == DEFAULT_TO:
                raise GhError("Could not resolve to an issue")
            raise AssertionError(args)
        if args[:2] == ["issue", "close"]:
            closes.append(args)
            return ""
        if args[:2] == ["issue", "create"]:
            raise AssertionError("must not call influenzer-handoff")
        raise AssertionError(args)

    payload = cleared_close(SOURCE, 4, 7, run=run)
    assert payload["ok"] is False
    assert payload["atom"] == "cleared-close"
    assert payload["error"] == "Could not resolve to an issue"
    assert payload["repo"] == SOURCE
    assert payload["issue"] == 4
    assert closes == []


def test_closing_itself_fails_without_gh() -> None:
    def run(args: list[str]) -> str:
        raise AssertionError(f"must not call gh: {args}")

    payload = cleared_close(DEFAULT_TO, 7, 7, to_repo=DEFAULT_TO, run=run)
    assert payload["ok"] is False
    assert payload["atom"] == "cleared-close"
    assert payload["error"] == "closing itself"
    assert payload["repo"] == DEFAULT_TO
    assert payload["issue"] == 7
    assert payload["handoff"] == 7


def test_same_number_on_other_repo_is_not_self() -> None:
    closes: list[list[str]] = []

    def run(args: list[str]) -> str:
        if args[:2] == ["issue", "view"]:
            number = int(args[2])
            repo = _repo_of(args)
            if number == 7 and repo == SOURCE:
                return _view(
                    7,
                    "OPEN",
                    "bifrost:out",
                    "verdict:pass",
                    url="https://github.com/mikolaj92/lokay/issues/7",
                )
            if number == 7 and repo == DEFAULT_TO:
                return _view(7, "OPEN", "bifrost:in", url=HANDOFF_URL)
            raise AssertionError(args)
        if args[:2] == ["issue", "close"]:
            closes.append(args)
            return ""
        raise AssertionError(args)

    payload = cleared_close(SOURCE, 7, 7, run=run)
    assert payload["ok"] is True
    assert payload["closed"] is True
    assert payload["issue"] == 7
    assert payload["handoff"] == 7
    assert payload["repo"] == SOURCE
    assert payload["to_repo"] == DEFAULT_TO
    assert len(closes) == 1


def test_gh_close_failure_is_not_success() -> None:
    def run(args: list[str]) -> str:
        if args[:2] == ["issue", "view"]:
            number = int(args[2])
            repo = _repo_of(args)
            if number == 4 and repo == SOURCE:
                return _view(4, "OPEN", "bifrost:out", "verdict:pass")
            if number == 7 and repo == DEFAULT_TO:
                return _view(7, "OPEN", "bifrost:in")
            raise AssertionError(args)
        if args[:2] == ["issue", "close"]:
            raise GhError("HTTP 422: Validation Failed")
        raise AssertionError(args)

    payload = cleared_close(SOURCE, 4, 7, run=run)
    assert payload["ok"] is False
    assert payload["error"] == "HTTP 422: Validation Failed"
    assert payload["ok"] is not True
    assert payload.get("closed") is not True


def test_invalid_repo_shape_fails_without_gh() -> None:
    def run(args: list[str]) -> str:
        raise AssertionError(f"must not call gh: {args}")

    payload = cleared_close("not-a-repo", 4, 7, run=run)
    assert payload["ok"] is False
    assert "invalid repo" in payload["error"]
    assert payload["repo"] == "not-a-repo"
    assert payload["issue"] == 4


def test_invalid_to_repo_fails_without_gh() -> None:
    def run(args: list[str]) -> str:
        raise AssertionError(f"must not call gh: {args}")

    payload = cleared_close(SOURCE, 4, 7, to_repo="nope", run=run)
    assert payload["ok"] is False
    assert "invalid repo" in payload["error"]
    assert payload["issue"] == 4


def test_to_repo_override() -> None:
    closes: list[list[str]] = []
    dest = "acme/influenzer"

    def run(args: list[str]) -> str:
        if args[:1] == ["api"]:
            raise AssertionError("must not fetch mill catalog")
        if args[:2] == ["issue", "view"]:
            number = int(args[2])
            repo = _repo_of(args)
            if number == 4 and repo == SOURCE:
                return _view(4, "OPEN", "bifrost:out", "verdict:pass", url=URL)
            if number == 2 and repo == dest:
                return _view(
                    2,
                    "OPEN",
                    "bifrost:in",
                    url="https://github.com/acme/influenzer/issues/2",
                )
            raise AssertionError(args)
        if args[:2] == ["issue", "close"]:
            closes.append(args)
            return ""
        if args[:2] == ["issue", "create"]:
            raise AssertionError("must not call influenzer-handoff")
        raise AssertionError(args)

    payload = cleared_close(SOURCE, 4, 2, to_repo=dest, run=run)
    assert payload["ok"] is True
    assert payload["to_repo"] == dest
    assert payload["handoff"] == 2
    comment = closes[0][closes[0].index("--comment") + 1]
    assert comment == pointer_comment(dest, 2)


def test_extra_comment_appended_to_pointer() -> None:
    closes: list[list[str]] = []

    def run(args: list[str]) -> str:
        if args[:2] == ["issue", "view"]:
            number = int(args[2])
            repo = _repo_of(args)
            if number == 4 and repo == SOURCE:
                return _view(4, "OPEN", "bifrost:out", "verdict:pass")
            if number == 7 and repo == DEFAULT_TO:
                return _view(7, "OPEN", "bifrost:in")
            raise AssertionError(args)
        if args[:2] == ["issue", "close"]:
            closes.append(args)
            return ""
        raise AssertionError(args)

    payload = cleared_close(
        SOURCE, 4, 7, comment="Keep the signal notes.", run=run
    )
    assert payload["ok"] is True
    comment = closes[0][closes[0].index("--comment") + 1]
    assert comment == pointer_comment(DEFAULT_TO, 7, "Keep the signal notes.")
    assert comment.endswith("Keep the signal notes.")
    assert comment.startswith("Handed off to mikolaj92/influenzer#7.")


def test_fake_run_does_not_call_handoff_catalog_out_apply_or_pr_close() -> None:
    closes: list[list[str]] = []

    def run(args: list[str]) -> str:
        if args[:1] == ["api"]:
            raise AssertionError("must not fetch mill catalog")
        if args[:2] == ["issue", "create"]:
            raise AssertionError("must not call influenzer-handoff")
        if args[:2] == ["issue", "edit"] or args[:2] == ["pr", "edit"]:
            raise AssertionError("must not call out-apply")
        if args[:2] == ["pr", "close"]:
            raise AssertionError("must not close PRs")
        if args[:2] == ["issue", "view"]:
            number = int(args[2])
            repo = _repo_of(args)
            if number == 4 and repo == SOURCE:
                return _view(4, "OPEN", "bifrost:out", "verdict:pass", url=URL)
            if number == 7 and repo == DEFAULT_TO:
                return _view(7, "OPEN", "bifrost:in", url=HANDOFF_URL)
            raise AssertionError(args)
        if args[:2] == ["issue", "close"]:
            closes.append(args)
            return ""
        raise AssertionError(args)

    payload = cleared_close(SOURCE, 4, 7, run=run)
    assert payload["ok"] is True
    assert payload["closed"] is True
    assert closes[0][:2] == ["issue", "close"]
    assert closes[0][2] != "pr"


def test_main_help(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        main(["--help"])
    assert exc.value.code == 0
    out = capsys.readouterr().out
    assert "cleared-close" in out
    assert "--repo" in out
    assert "--issue" in out
    assert "--handoff" in out
    assert "--to-repo" in out
    assert "--pr" not in out


def test_main_rejects_pr_flag() -> None:
    with pytest.raises(SystemExit) as exc:
        main(["--repo", SOURCE, "--issue", "4", "--handoff", "7", "--pr", "9"])
    assert exc.value.code != 0


def test_fala_package_does_not_include_cleared_close() -> None:
    text = (Path(__file__).resolve().parents[1] / "fala-package.toml").read_text(
        encoding="utf-8"
    )
    assert "cleared-close" not in text
    assert "cleared_close" not in text
    assert 'command = ["uv", "run", "observe-queue"]' in text
    assert 'id = "monitor"' in text
    assert 'command = ["uv", "run", "observe-cleared"]' in text
