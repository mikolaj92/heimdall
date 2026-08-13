"""Read-only JSON of Heimdall's inbound triage queue.

Open issues with bifrost:in that are not yet a Lokay handoff (work:ready)
and not outbound (bifrost:out). GitHub stand-in until mail is wired. One
repo (default mikolaj92/heimdall). Does not fetch the mill catalog or
survey Influenzer. Does not merge, comment, label, apply work:ready, wake
the mill, SSH, mail, or call craft-inbound / craft-ready.
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from heimdall.observe_queue import (
    HEIMDALL,
    GhError,
    GhFn,
    gh,
    list_issues,
    write_fala_result,
)

ATOM = "observe-inbound"
FALA_REACTION = "github.observe_inbound"
INBOUND = "bifrost:in"
OUTBOUND = "bifrost:out"
READY = "work:ready"
HOLD = "verdict:hold"
PASS = "verdict:pass"
WHY_INBOUND = "inbound"
WHY_HOLD = "hold"
WHY_PASS = "pass"


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


def keep_inbound(labels: list[str]) -> bool:
    """Keep bifrost:in that is not yet a Lokay handoff and not outbound."""
    return INBOUND in labels and READY not in labels and OUTBOUND not in labels


def why_inbound(labels: list[str]) -> list[str]:
    """Classify a kept issue. Always inbound; hold/pass if those verdicts."""
    why = [WHY_INBOUND]
    if HOLD in labels:
        why.append(WHY_HOLD)
    if PASS in labels:
        why.append(WHY_PASS)
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
        if keep_inbound(issue["labels"]):
            out.append(as_item(repo, issue, why_inbound(issue["labels"])))
    return out


def observe_inbound(
    *,
    heimdall: str = HEIMDALL,
    run: GhFn | None = None,
) -> dict[str, Any]:
    """List Heimdall inbound triage issues. Fail closed on gh errors. One repo only."""
    run = run or gh
    try:
        items = survey_repo(heimdall, run=run)
    except GhError as exc:
        return err(
            "gh failed; not idle",
            heimdall=heimdall,
            failed=[{"repo": heimdall, "error": str(exc)}],
        )
    counts = {
        "items": len(items),
        "inbound": sum(1 for row in items if WHY_INBOUND in row["why"]),
        "hold": sum(1 for row in items if WHY_HOLD in row["why"]),
        "pass": sum(1 for row in items if WHY_PASS in row["why"]),
    }
    return ok(heimdall=heimdall, counts=counts, items=items)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="observe-inbound",
        description=(
            "Print a JSON envelope of open Heimdall issues in the inbound "
            "triage queue (bifrost:in, not work:ready, not bifrost:out). "
            "Read-only. One repo; does not fetch the mill catalog."
        ),
    )
    parser.add_argument(
        "--heimdall",
        default=HEIMDALL,
        help="Heimdall OWNER/NAME (one repo; never mill catalog)",
    )
    args = parser.parse_args(argv)
    return emit_exit(observe_inbound(heimdall=args.heimdall))


if __name__ == "__main__":
    raise SystemExit(main())
