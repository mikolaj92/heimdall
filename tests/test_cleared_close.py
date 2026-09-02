from __future__ import annotations

import json

from heimdall.cleared_close import cleared_close, main
from heimdall.observe_queue import GhError

SOURCE = "mikolaj92/heimdall"
DEST = "mikolaj92/influenzer"


def row(repo: str, number: int, state: str = "OPEN", *labels: str) -> str:
    return json.dumps({"number": number, "state": state, "labels": [{"name": x} for x in labels], "url": f"https://github.com/{repo}/issues/{number}"})


def test_closes_outbound_pass_with_handoff_pointer() -> None:
    calls: list[list[str]] = []
    def run(args: list[str]) -> str:
        calls.append(args)
        if args[:2] == ["issue", "view"]:
            repo = args[args.index("-R") + 1]
            return row(repo, int(args[2]), "OPEN", *( ["bifrost:out", "verdict:pass", "work:ready"] if repo == SOURCE else [] ))
        if args[:2] == ["issue", "close"]:
            return ""
        raise AssertionError(args)
    payload = cleared_close(SOURCE, 1, 7, run=run)
    assert payload["ok"] is True and payload["closed"] is True
    assert calls[-1][:3] == ["issue", "close", "1"]
    assert f"{DEST}#7" in calls[-1][-1]


def test_already_closed_is_idempotent() -> None:
    calls: list[list[str]] = []
    def run(args: list[str]) -> str:
        calls.append(args); return row(SOURCE, 1, "CLOSED", "bifrost:out", "verdict:pass")
    payload = cleared_close(SOURCE, 1, 7, run=run)
    assert payload["ok"] is True and payload["already"] == ["closed"]
    assert len(calls) == 1


def test_requires_out_and_pass_but_allows_work_ready() -> None:
    for labels in ((), ("bifrost:out",), ("verdict:pass",)):
        def run(args: list[str], labs: tuple[str, ...] = labels) -> str:
            return row(SOURCE, 1, "OPEN", *labs)
        assert cleared_close(SOURCE, 1, 7, run=run)["ok"] is False


def test_same_target_invalid_repos_and_view_error_fail_closed() -> None:
    assert cleared_close(SOURCE, 1, 1, to_repo=SOURCE, run=lambda _: "")["ok"] is False
    assert cleared_close("bad", 1, 7, run=lambda _: "")["ok"] is False
    assert cleared_close(SOURCE, 1, 7, to_repo="bad", run=lambda _: "")["ok"] is False
    payload = cleared_close(SOURCE, 1, 7, run=lambda _: (_ for _ in ()).throw(GhError("view failed")))
    assert payload["ok"] is False and payload["error"] == "view failed"


def test_missing_handoff_and_close_error_fail_closed() -> None:
    calls = 0
    def missing(args: list[str]) -> str:
        nonlocal calls
        calls += 1
        if calls == 1:
            return row(SOURCE, 1, "OPEN", "bifrost:out", "verdict:pass")
        raise GhError("handoff missing")
    assert cleared_close(SOURCE, 1, 7, run=missing)["ok"] is False
    def close_error(args: list[str]) -> str:
        if args[:2] == ["issue", "view"]:
            repo = args[args.index("-R") + 1]
            return row(repo, int(args[2]), "OPEN", *( ["bifrost:out", "verdict:pass"] if repo == SOURCE else [] ))
        raise GhError("close failed")
    payload = cleared_close(SOURCE, 1, 7, run=close_error)
    assert payload["ok"] is False and payload["error"] == "close failed"


def test_cli_help(capsys) -> None:
    try:
        main(["--help"])
    except SystemExit as exc:
        assert exc.code == 0
    assert "--handoff" in capsys.readouterr().out
