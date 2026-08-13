"""Apply mill ai:ready when a catalog issue already has Heimdall work:ready.

Catalog is lokay repos.mikolaj92.yaml (never heimdall). Mapping lives here, not
in labels.yml. No-op on mikolaj92/heimdall. Idempotent if ai:ready is present.
Does not wake the mill, SSH mini, open probe issues, or send mail.
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
    gh_json,
    label_names,
)

ATOM = "dual-label-ready"
WORK_READY = "work:ready"
AI_READY = "ai:ready"


def ok(**fields: Any) -> dict[str, Any]:
    return {"ok": True, "atom": ATOM, **fields}


def err(message: str, **fields: Any) -> dict[str, Any]:
    return {"ok": False, "atom": ATOM, "error": message, **fields}


def emit(payload: dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(payload, ensure_ascii=False) + "\n")


def emit_exit(payload: dict[str, Any]) -> int:
    emit(payload)
    return 0 if payload.get("ok") else 1


def is_heimdall(repo: str, heimdall: str = HEIMDALL) -> bool:
    return repo.lower() == heimdall.lower()


def in_catalog(repo: str, catalog: list[str]) -> bool:
    key = repo.lower()
    return any(name.lower() == key for name in catalog)


def view_issue(repo: str, issue: int, *, run: GhFn) -> dict[str, Any]:
    row = gh_json(
        [
            "issue",
            "view",
            str(issue),
            "-R",
            repo,
            "--json",
            "number,labels",
        ],
        run=run,
    )
    if not isinstance(row, dict):
        raise GhError(f"issue view for {repo}#{issue} was not an object")
    return row


def add_label(repo: str, issue: int, label: str, *, run: GhFn) -> None:
    run(
        [
            "issue",
            "edit",
            str(issue),
            "-R",
            repo,
            "--add-label",
            label,
        ]
    )


def dual_label(
    repo: str,
    issue: int,
    *,
    heimdall: str = HEIMDALL,
    run: GhFn | None = None,
) -> dict[str, Any]:
    """If catalog issue has work:ready, apply ai:ready. Fail closed on gh errors."""
    run = run or gh
    repo = repo.strip()
    base = {"repo": repo, "issue": issue, "added": [], "already": []}

    if is_heimdall(repo, heimdall):
        return ok(**base, skipped="heimdall")

    try:
        catalog = fetch_catalog(run=run, exclude=heimdall)
    except GhError as exc:
        return err(f"catalog: {exc}", **base)

    if not in_catalog(repo, catalog):
        return err("not a mill-catalog repo", **base)

    try:
        row = view_issue(repo, issue, run=run)
    except GhError as exc:
        return err(str(exc), **base)

    labels = label_names(row.get("labels"))
    if WORK_READY not in labels:
        return err("missing work:ready", **base, labels=labels)

    if AI_READY in labels:
        return ok(repo=repo, issue=issue, added=[], already=[AI_READY])

    try:
        add_label(repo, issue, AI_READY, run=run)
    except GhError as exc:
        return err(str(exc), **base)

    return ok(repo=repo, issue=issue, added=[AI_READY], already=[])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="dual-label-ready",
        description=(
            "On a mill-catalog repo, if the issue has work:ready, also apply "
            "ai:ready. No-op on heimdall."
        ),
    )
    parser.add_argument("--repo", required=True, help="OWNER/NAME")
    parser.add_argument("--issue", required=True, type=int, help="Issue number")
    args = parser.parse_args(argv)
    import heimdall.observe_queue as observe_queue

    observe_queue._catalog_cache = None
    return emit_exit(dual_label(args.repo, args.issue))


if __name__ == "__main__":
    raise SystemExit(main())
