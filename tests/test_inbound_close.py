from __future__ import annotations

import json

from heimdall.inbound_close import inbound_close, main
from heimdall.observe_queue import GhError

REPO = "mikolaj92/heimdall"


def row(number: int, state: str = "OPEN", *labels: str) -> str:
    return json.dumps({"number": number, "state": state, "labels": [{"name": x} for x in labels], "url": f"https://github.com/{REPO}/issues/{number}"})


def test_closes_inbound_with_pointer() -> None:
    calls: list[list[str]] = []
    def run(args: list[str]) -> str:
        calls.append(args)
        if args[:2] == ["issue", "view"]:
            return row(int(args[2]), "OPEN", *( ["bifrost:in"] if args[2] == "1" else ["work:ready"] ))
        if args[:2] == ["issue", "close"]:
            return ""
        raise AssertionError(args)
    payload = inbound_close(REPO, 1, 2, run=run)
    assert payload["ok"] is True and payload["closed"] is True
    close = calls[-1]
    assert close[:3] == ["issue", "close", "1"]
    assert "--comment" in close and "#2" in close[-1]
    assert all(args[:2] != ["issue", "edit"] for args in calls)


def test_already_closed_is_idempotent() -> None:
    calls: list[list[str]] = []
    def run(args: list[str]) -> str:
        calls.append(args); return row(1, "CLOSED", "bifrost:in")
    payload = inbound_close(REPO, 1, 2, run=run)
    assert payload["ok"] is True and payload["already"] == ["closed"]
    assert len(calls) == 1


def test_rejects_source_states_and_same_number() -> None:
    assert inbound_close(REPO, 2, 2, run=lambda _: "")["ok"] is False
    for labels in ((), ("work:ready", "bifrost:in"), ("bifrost:in", "bifrost:out")):
        def run(args: list[str], labs: tuple[str, ...] = labels) -> str:
            return row(1, "OPEN", *labs)
        assert inbound_close(REPO, 1, 2, run=run)["ok"] is False


def test_rejects_missing_ready_and_gh_close_error() -> None:
    def not_ready(args: list[str]) -> str:
        return row(int(args[2]), "OPEN", *( ["bifrost:in"] if args[2] == "1" else [] ))
    assert inbound_close(REPO, 1, 2, run=not_ready)["ok"] is False
    def close_error(args: list[str]) -> str:
        if args[:2] == ["issue", "view"]:
            return row(int(args[2]), "OPEN", *( ["bifrost:in"] if args[2] == "1" else ["work:ready"] ))
        raise GhError("close failed")
    payload = inbound_close(REPO, 1, 2, run=close_error)
    assert payload["ok"] is False and payload["error"] == "close failed"


def test_invalid_repo_and_view_error_fail_closed() -> None:
    assert inbound_close("bad", 1, 2, run=lambda _: "")["ok"] is False
    payload = inbound_close(REPO, 1, 2, run=lambda _: (_ for _ in ()).throw(GhError("view failed")))
    assert payload["ok"] is False and payload["error"] == "view failed"


def test_cli_help(capsys) -> None:
    try:
        main(["--help"])
    except SystemExit as exc:
        assert exc.code == 0
    assert "--ready" in capsys.readouterr().out
