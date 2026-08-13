"""Read-only JSON of outbound GitHub items that may ship.

Open issues and PRs labeled bifrost:out and verdict:pass. Heimdall plus mill
catalog (lokay repos.mikolaj92.yaml, never heimdall twice). Does not merge,
comment, label, wake the mill, mail, probe, or call Influenzer.
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
    fetch_catalog,
    gh,
    list_issues,
    list_pulls,
    write_fala_result,
)

ATOM = "observe-cleared"
FALA_REACTION = "github.observe_cleared"
OUTBOUND = "bifrost:out"
PASS = "verdict:pass"


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


def keep_cleared(labels: list[str]) -> bool:
    """Keep bifrost:out that may ship — verdict:pass is present."""
    return OUTBOUND in labels and PASS in labels


def as_cleared(repo: str, item: dict[str, Any], *, kind: str) -> dict[str, Any]:
    return {
        "repo": repo,
        "number": int(item["number"]),
        "title": str(item.get("title") or ""),
        "labels": list(item.get("labels") or []),
        "url": str(item.get("url") or ""),
        "kind": kind,
    }


def survey_repo(repo: str, *, run: GhFn) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for issue in list_issues(repo, run=run):
        if keep_cleared(issue["labels"]):
            out.append(as_cleared(repo, issue, kind="issue"))
    for pull in list_pulls(repo, run=run):
        pull.pop("_head", None)
        if keep_cleared(pull["labels"]):
            out.append(as_cleared(repo, pull, kind="pull"))
    return out


def observe_cleared(
    *,
    heimdall: str = HEIMDALL,
    run: GhFn | None = None,
) -> dict[str, Any]:
    """List outbound items that may ship. Fail closed on gh errors."""
    run = run or gh
    failed: list[dict[str, str]] = []
    items: list[dict[str, Any]] = []
    surveyed = 0

    try:
        catalog = fetch_catalog(run=run, exclude=heimdall)
    except GhError as exc:
        return err(f"catalog: {exc}")

    try:
        items.extend(survey_repo(heimdall, run=run))
        surveyed += 1
    except GhError as exc:
        failed.append({"repo": heimdall, "error": str(exc)})

    for name in catalog:
        if name.lower() == heimdall.lower():
            continue
        try:
            items.extend(survey_repo(name, run=run))
            surveyed += 1
        except GhError as exc:
            failed.append({"repo": name, "error": str(exc)})

    heimdall_n = sum(1 for row in items if row["repo"].lower() == heimdall.lower())
    mill_n = len(items) - heimdall_n
    counts = {
        "catalog": len(catalog),
        "surveyed": surveyed,
        "items": len(items),
        "heimdall_items": heimdall_n,
        "mill_items": mill_n,
    }
    fields = {
        "heimdall": heimdall,
        "catalog": catalog,
        "counts": counts,
        "items": items,
    }
    if failed:
        return err("gh failed; not idle", failed=failed, **fields)
    return ok(**fields)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="observe-cleared",
        description=(
            "Print a JSON envelope of open GitHub items that claim outbound "
            "(bifrost:out) and may ship (verdict:pass). Read-only."
        ),
    )
    parser.add_argument(
        "--heimdall",
        default=HEIMDALL,
        help="Heimdall OWNER/NAME (never added to the mill catalog)",
    )
    args = parser.parse_args(argv)
    import heimdall.observe_queue as observe_queue

    observe_queue._catalog_cache = None
    return emit_exit(observe_cleared(heimdall=args.heimdall))


if __name__ == "__main__":
    raise SystemExit(main())
