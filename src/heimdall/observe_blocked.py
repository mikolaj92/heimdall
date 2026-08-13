"""Read-only JSON of open GitHub issues that are stuck.

Heimdall: issues with work:blocked.
Mill catalog (lokay repos.mikolaj92.yaml, never heimdall twice): issues with
work:blocked or ai:blocked (mill-owned; not in labels.yml). work:ready and
work:doing are not blocked. Does not merge, comment, label, wake the mill,
or mail.
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
    write_fala_result,
)

ATOM = "observe-blocked"
FALA_REACTION = "github.observe_blocked"
BLOCKED = "work:blocked"
MILL_BLOCKED = "ai:blocked"


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


def keep_blocked(labels: list[str], *, mill: bool = False) -> bool:
    """Keep stuck issues. work:ready / work:doing are not blocked."""
    if BLOCKED in labels:
        return True
    return mill and MILL_BLOCKED in labels


def as_blocked(repo: str, item: dict[str, Any]) -> dict[str, Any]:
    return {
        "repo": repo,
        "number": int(item["number"]),
        "title": str(item.get("title") or ""),
        "labels": list(item.get("labels") or []),
        "url": str(item.get("url") or ""),
    }


def survey_repo(repo: str, *, mill: bool, run: GhFn) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for issue in list_issues(repo, run=run):
        if keep_blocked(issue["labels"], mill=mill):
            out.append(as_blocked(repo, issue))
    return out


def observe_blocked(
    *,
    heimdall: str = HEIMDALL,
    run: GhFn | None = None,
) -> dict[str, Any]:
    """List stuck open issues. Fail closed on gh errors."""
    run = run or gh
    failed: list[dict[str, str]] = []
    items: list[dict[str, Any]] = []
    surveyed = 0

    try:
        catalog = fetch_catalog(run=run, exclude=heimdall)
    except GhError as exc:
        return err(f"catalog: {exc}")

    try:
        items.extend(survey_repo(heimdall, mill=False, run=run))
        surveyed += 1
    except GhError as exc:
        failed.append({"repo": heimdall, "error": str(exc)})

    for name in catalog:
        if name.lower() == heimdall.lower():
            continue
        try:
            items.extend(survey_repo(name, mill=True, run=run))
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
        prog="observe-blocked",
        description=(
            "Print a JSON envelope of open GitHub issues that are stuck "
            "(work:blocked; mill catalog also ai:blocked). Read-only."
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
    return emit_exit(observe_blocked(heimdall=args.heimdall))


if __name__ == "__main__":
    raise SystemExit(main())
