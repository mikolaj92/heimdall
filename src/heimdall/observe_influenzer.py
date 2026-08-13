"""Read-only JSON of open GitHub items on Influenzer.

One repo (default mikolaj92/influenzer): inbound bifrost:in, outbound that
must not ship (bifrost:out missing verdict:pass), work:blocked, verdict:hold,
and all open PRs. Does not fetch the mill catalog or survey heimdall. Does
not merge, comment, label, wake Influenzer tick, SSH, mail, or mill.
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from heimdall.observe_queue import (
    GhError,
    GhFn,
    gh,
    list_issues,
    list_pulls,
    write_fala_result,
)

ATOM = "observe-influenzer"
FALA_REACTION = "github.observe_influenzer"
INFLUENZER = "mikolaj92/influenzer"
INBOUND = "bifrost:in"
OUTBOUND = "bifrost:out"
PASS = "verdict:pass"
BLOCKED = "work:blocked"
HOLD = "verdict:hold"
WHY_INBOUND = "inbound"
WHY_OUTBOUND_HOLD = "outbound_hold"
WHY_BLOCKED = "blocked"
WHY_HOLD = "hold"
WHY_PULL = "pull"


def ok(**fields: Any) -> dict[str, Any]:
    return {"ok": True, "atom": ATOM, **fields}


def err(message: str, **fields: Any) -> dict[str, Any]:
    return {"ok": False, "atom": ATOM, "error": message, **fields}


def emit(payload: dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(payload, ensure_ascii=False) + "\n")
    write_fala_result(payload, kind=FALA_REACTION)


def emit_exit(payload: dict[str, Any]) -> int:
    emit(payload)
    return 0 if payload.get("ok") else 1


def why_issue(labels: list[str]) -> list[str]:
    """Classify a kept issue. Empty means drop. An issue may have several whys."""
    why: list[str] = []
    if INBOUND in labels:
        why.append(WHY_INBOUND)
    if OUTBOUND in labels and PASS not in labels:
        why.append(WHY_OUTBOUND_HOLD)
    if BLOCKED in labels:
        why.append(WHY_BLOCKED)
    if HOLD in labels:
        why.append(WHY_HOLD)
    return why


def as_item(repo: str, item: dict[str, Any], why: list[str]) -> dict[str, Any]:
    return {
        "repo": repo,
        "number": int(item["number"]),
        "title": str(item.get("title") or ""),
        "labels": list(item.get("labels") or []),
        "url": str(item.get("url") or ""),
        "why": list(why),
    }


def survey_repo(repo: str, *, run: GhFn) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for issue in list_issues(repo, run=run):
        why = why_issue(issue["labels"])
        if why:
            out.append(as_item(repo, issue, why))
    for pull in list_pulls(repo, run=run):
        pull.pop("_head", None)
        out.append(as_item(repo, pull, [WHY_PULL]))
    return out


def observe_influenzer(
    *,
    repo: str = INFLUENZER,
    run: GhFn | None = None,
) -> dict[str, Any]:
    """List Influenzer GitHub items. Fail closed on gh errors. One repo only."""
    run = run or gh
    try:
        items = survey_repo(repo, run=run)
    except GhError as exc:
        return err(
            "gh failed; not idle",
            repo=repo,
            failed=[{"repo": repo, "error": str(exc)}],
        )
    counts = {
        "items": len(items),
        "inbound": sum(1 for row in items if WHY_INBOUND in row["why"]),
        "outbound_hold": sum(1 for row in items if WHY_OUTBOUND_HOLD in row["why"]),
        "blocked": sum(1 for row in items if WHY_BLOCKED in row["why"]),
        "hold": sum(1 for row in items if WHY_HOLD in row["why"]),
        "pulls": sum(1 for row in items if WHY_PULL in row["why"]),
    }
    return ok(repo=repo, counts=counts, items=items)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="observe-influenzer",
        description=(
            "Print a JSON envelope of open GitHub items on Influenzer "
            "(inbound, outbound that must not ship, blocked, hold, and "
            "all open PRs). Read-only. One repo; does not fetch the mill catalog."
        ),
    )
    parser.add_argument(
        "--repo",
        default=INFLUENZER,
        help="Influenzer OWNER/NAME (one repo; never mill catalog)",
    )
    args = parser.parse_args(argv)
    return emit_exit(observe_influenzer(repo=args.repo))


if __name__ == "__main__":
    raise SystemExit(main())
