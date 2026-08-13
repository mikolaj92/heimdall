"""Close the mill dual-label gap after observe.

Surveys mill catalog itself (Fala subprocess adapters do not pipe stdout).
For catalog issues that already have work:ready, runs dual_label() so ai:ready
is applied. No-op on heimdall. Does not wake the mill, SSH, open probes, or
merge PRs.
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from heimdall.dual_label_ready import dual_label, is_heimdall
from heimdall.observe_queue import (
    HEIMDALL,
    GhError,
    GhFn,
    fetch_catalog,
    gh,
    list_issues,
    write_fala_result,
)

ATOM = "dual-label-pass"
FALA_REACTION = "github.dual_label"
WORK_READY = "work:ready"


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


def dual_label_pass(
    *,
    heimdall: str = HEIMDALL,
    run: GhFn | None = None,
) -> dict[str, Any]:
    """Apply ai:ready on catalog work:ready issues. Fail closed on gh errors."""
    run = run or gh
    added: list[dict[str, Any]] = []
    already: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    failed: list[dict[str, Any]] = []
    considered = 0

    try:
        catalog = fetch_catalog(run=run, exclude=heimdall)
    except GhError as exc:
        return err(f"catalog: {exc}")

    for repo in catalog:
        if is_heimdall(repo, heimdall):
            skipped.append({"repo": repo, "skipped": "heimdall"})
            continue
        try:
            issues = list_issues(repo, run=run)
        except GhError as exc:
            failed.append({"repo": repo, "error": str(exc)})
            continue
        for issue in issues:
            if WORK_READY not in issue["labels"]:
                continue
            considered += 1
            payload = dual_label(repo, int(issue["number"]), heimdall=heimdall, run=run)
            row = {"repo": repo, "issue": int(issue["number"])}
            if payload.get("skipped") == "heimdall":
                skipped.append({**row, "skipped": "heimdall"})
                continue
            if not payload.get("ok"):
                failed.append({**row, "error": str(payload.get("error") or "dual_label")})
                continue
            if payload.get("added"):
                added.append({**row, "added": list(payload["added"])})
            else:
                already.append({**row, "already": list(payload.get("already") or [])})

    fields = {
        "heimdall": heimdall,
        "catalog": catalog,
        "added": added,
        "already": already,
        "skipped": skipped,
        "counts": {
            "catalog": len(catalog),
            "considered": considered,
            "added": len(added),
            "already": len(already),
            "skipped": len(skipped),
        },
    }
    if failed:
        return err("gh failed; not idle", failed=failed, **fields)
    return ok(**fields)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="dual-label-pass",
        description=(
            "On mill-catalog repos, apply ai:ready to open issues that already "
            "have work:ready. No-op on heimdall. Does not wake the mill."
        ),
    )
    parser.add_argument(
        "--heimdall",
        default=HEIMDALL,
        help="Heimdall OWNER/NAME (never dual-labeled)",
    )
    args = parser.parse_args(argv)
    import heimdall.observe_queue as observe_queue

    observe_queue._catalog_cache = None
    return emit_exit(dual_label_pass(heimdall=args.heimdall))


if __name__ == "__main__":
    raise SystemExit(main())
