from __future__ import annotations

import json
from pathlib import Path

import pytest

from heimdall.inbound_close import inbound_close, main, pointer_comment
from heimdall.observe_queue import HEIMDALL, GhError

URL = "https://github.com/mikolaj92/heimdall/issues/3"
READY_URL = "https://github.com/mikolaj92/heimdall/issues/12"


def _view(number: int, state: str, *names: str, url: str | None = None) -> str:
    return json.dumps(
        {
            "number": number,
            "state": state,
            "labels": [{"name": n} for n in names],
            "url": url or f"https://github.com/mikolaj92/heimdall/issues/{number}",
        }
    )


def test_inbound_closes_with_pointer() -> None:
    closes: list[list[str]] = []

    def run(args: list[str]) -> str:
        if args[:1] == ["api"]:
            raise AssertionError("must not fetch mill catalog")
        if args[:2] == ["issue", "view"]:
            number = int(args[2])
            if number == 3:
                return _view(3, "OPEN", "bifrost:in", "verdict:hold", url=URL)
            if number == 12:
                return _view(12, "OPEN", "work:ready", url=READY_URL)
            raise AssertionError(args)
        if args[:2] == ["issue", "close"]:
            closes.append(args)
            return ""
        if args[:2] == ["issue", "create"]:
            raise AssertionError("must not create issues")
        if args[:2] == ["issue", "edit"]:
            raise AssertionError("must not edit labels")
        if args[:2] == ["issue", "comment"]:
            raise AssertionError("prefer issue close --comment")
        raise AssertionError(args)

    payload = inbound_close(HEIMDALL, 3, 12, run=run)
    assert payload == {
        "ok": True,
        "atom": "inbound-close",
        "repo": HEIMDALL,
        "issue": 3,
        "ready": 12,
        "closed": True,
        "already": [],
        "url": URL,
    }
    assert len(closes) == 1
    assert closes[0][:5] == ["issue", "close", "3", "-R", HEIMDALL]
    comment = closes[0][closes[0].index("--comment") + 1]
    assert comment == (
        "Superseded by #12. Closed inbound; work lives on the ready issue."
    )
    assert "work:ready" not in closes[0]
    assert "ai:ready" not in closes[0]


def test_already_closed_is_idempotent() -> None:
    closes: list[list[str]] = []

    def run(args: list[str]) -> str:
        if args[:1] == ["api"]:
            raise AssertionError("must not fetch mill catalog")
        if args[:2] == ["issue", "view"]:
            number = int(args[2])
            if number == 3:
                return _view(3, "CLOSED", "bifrost:in", url=URL)
            raise AssertionError("must not view ready when inbound is closed")
        if args[:2] == ["issue", "close"]:
            closes.append(args)
            return ""
        raise AssertionError(args)

    payload = inbound_close(HEIMDALL, 3, 12, run=run)
    assert payload["ok"] is True
    assert payload["atom"] == "inbound-close"
    assert payload["closed"] is False
    assert payload["already"] == ["closed"]
    assert payload["url"] == URL
    assert closes == []


def test_has_work_ready_fails_without_close() -> None:
    closes: list[list[str]] = []

    def run(args: list[str]) -> str:
        if args[:2] == ["issue", "view"]:
            return _view(3, "OPEN", "bifrost:in", "work:ready")
        if args[:2] == ["issue", "close"]:
            closes.append(args)
            return ""
        raise AssertionError(args)

    payload = inbound_close(HEIMDALL, 3, 12, run=run)
    assert payload["ok"] is False
    assert payload["atom"] == "inbound-close"
    assert payload["error"] == "has work:ready"
    assert payload["repo"] == HEIMDALL
    assert payload["issue"] == 3
    assert closes == []


def test_missing_bifrost_in_fails_without_close() -> None:
    closes: list[list[str]] = []

    def run(args: list[str]) -> str:
        if args[:2] == ["issue", "view"]:
            return _view(3, "OPEN", "verdict:hold")
        if args[:2] == ["issue", "close"]:
            closes.append(args)
            return ""
        raise AssertionError(args)

    payload = inbound_close(HEIMDALL, 3, 12, run=run)
    assert payload["ok"] is False
    assert payload["error"] == "missing bifrost:in"
    assert closes == []


def test_has_bifrost_out_fails_without_close() -> None:
    closes: list[list[str]] = []

    def run(args: list[str]) -> str:
        if args[:2] == ["issue", "view"]:
            return _view(3, "OPEN", "bifrost:in", "bifrost:out")
        if args[:2] == ["issue", "close"]:
            closes.append(args)
            return ""
        raise AssertionError(args)

    payload = inbound_close(HEIMDALL, 3, 12, run=run)
    assert payload["ok"] is False
    assert payload["error"] == "has bifrost:out"
    assert closes == []


def test_issue_equals_ready_fails_without_gh() -> None:
    def run(args: list[str]) -> str:
        raise AssertionError(f"must not call gh: {args}")

    payload = inbound_close(HEIMDALL, 7, 7, run=run)
    assert payload["ok"] is False
    assert payload["atom"] == "inbound-close"
    assert payload["error"] == "issue equals ready"
    assert payload["repo"] == HEIMDALL
    assert payload["issue"] == 7
    assert payload["ready"] == 7


def test_ready_view_fails_does_not_close() -> None:
    closes: list[list[str]] = []

    def run(args: list[str]) -> str:
        if args[:1] == ["api"]:
            raise AssertionError("must not fetch mill catalog")
        if args[:2] == ["issue", "view"]:
            number = int(args[2])
            if number == 3:
                return _view(3, "OPEN", "bifrost:in")
            if number == 12:
                raise GhError("Could not resolve to an issue")
            raise AssertionError(args)
        if args[:2] == ["issue", "close"]:
            closes.append(args)
            return ""
        raise AssertionError(args)

    payload = inbound_close(HEIMDALL, 3, 12, run=run)
    assert payload["ok"] is False
    assert payload["atom"] == "inbound-close"
    assert payload["error"] == "Could not resolve to an issue"
    assert payload["repo"] == HEIMDALL
    assert payload["issue"] == 3
    assert closes == []


def test_gh_close_failure_is_not_success() -> None:
    def run(args: list[str]) -> str:
        if args[:2] == ["issue", "view"]:
            number = int(args[2])
            if number == 3:
                return _view(3, "OPEN", "bifrost:in")
            if number == 12:
                return _view(12, "OPEN", "work:ready")
            raise AssertionError(args)
        if args[:2] == ["issue", "close"]:
            raise GhError("HTTP 422: Validation Failed")
        raise AssertionError(args)

    payload = inbound_close(HEIMDALL, 3, 12, run=run)
    assert payload["ok"] is False
    assert payload["error"] == "HTTP 422: Validation Failed"
    assert payload["ok"] is not True
    assert payload.get("closed") is not True


def test_invalid_repo_shape_fails_without_gh() -> None:
    def run(args: list[str]) -> str:
        raise AssertionError(f"must not call gh: {args}")

    payload = inbound_close("not-a-repo", 3, 12, run=run)
    assert payload["ok"] is False
    assert "invalid repo" in payload["error"]
    assert payload["repo"] == "not-a-repo"
    assert payload["issue"] == 3


def test_extra_comment_appended_to_pointer() -> None:
    closes: list[list[str]] = []

    def run(args: list[str]) -> str:
        if args[:2] == ["issue", "view"]:
            number = int(args[2])
            if number == 3:
                return _view(3, "OPEN", "bifrost:in")
            if number == 12:
                return _view(12, "OPEN", "work:ready")
            raise AssertionError(args)
        if args[:2] == ["issue", "close"]:
            closes.append(args)
            return ""
        raise AssertionError(args)

    payload = inbound_close(HEIMDALL, 3, 12, comment="Keep the signal notes.", run=run)
    assert payload["ok"] is True
    comment = closes[0][closes[0].index("--comment") + 1]
    assert comment == pointer_comment(12, "Keep the signal notes.")
    assert comment.endswith("Keep the signal notes.")
    assert comment.startswith("Superseded by #12.")


def test_catalog_repo_does_not_fetch_catalog_or_dual_label() -> None:
    closes: list[list[str]] = []

    def run(args: list[str]) -> str:
        if args[:1] == ["api"]:
            raise AssertionError("must not fetch mill catalog")
        if args[:2] == ["issue", "view"]:
            number = int(args[2])
            if number == 3:
                return _view(
                    3,
                    "OPEN",
                    "bifrost:in",
                    url="https://github.com/mikolaj92/lokay/issues/3",
                )
            if number == 12:
                return _view(
                    12,
                    "OPEN",
                    "work:ready",
                    url="https://github.com/mikolaj92/lokay/issues/12",
                )
            raise AssertionError(args)
        if args[:2] == ["issue", "close"]:
            closes.append(args)
            return ""
        if args[:2] == ["issue", "create"]:
            raise AssertionError("must not call craft-ready")
        if args[:2] == ["issue", "edit"]:
            raise AssertionError("must not dual-label")
        raise AssertionError(args)

    payload = inbound_close("mikolaj92/lokay", 3, 12, run=run)
    assert payload["ok"] is True
    assert payload["closed"] is True
    assert payload["repo"] == "mikolaj92/lokay"
    assert "ai:ready" not in (closes[0] if closes else [])
    assert "work:ready" not in closes[0]


def test_main_help(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        main(["--help"])
    assert exc.value.code == 0
    out = capsys.readouterr().out
    assert "inbound-close" in out
    assert "--repo" in out
    assert "--issue" in out
    assert "--ready" in out


def test_fala_package_does_not_include_inbound_close() -> None:
    text = (Path(__file__).resolve().parents[1] / "fala-package.toml").read_text(
        encoding="utf-8"
    )
    assert "inbound-close" not in text
    assert "inbound_close" not in text
    assert 'command = ["uv", "run", "observe-queue"]' in text
    assert 'id = "monitor"' in text
