"""Read-only JSON of open PRs Heimdall should look at for QA/verdict.

Heimdall: all open PRs (the gate's own mill/Grok-Bot handoffs).
Mill catalog (lokay repos.mikolaj92.yaml, never heimdall): mill-looking
open PRs (mill_pr: ai: labels or ai/ head). Does not merge, comment,
label, wake the mill, or invent policy.
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
    list_pulls,
    mill_pr,
    write_fala_result,
)

ATOM = "observe-verdict"
FALA_REACTION = "github.observe_verdict"


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


def as_pull(repo: str, pull: dict[str, Any]) -> dict[str, Any]:
    return {
        "repo": repo,
        "number": int(pull["number"]),
        "title": str(pull.get("title") or ""),
        "labels": list(pull.get("labels") or []),
        "url": str(pull.get("url") or ""),
    }


def keep_verdict_pr(kind: str, labels: list[str], head: str) -> bool:
    """Heimdall: every open PR. Mill catalog: mill_pr cheap signal only."""
    if kind == "heimdall":
        return True
    return mill_pr(labels, head)


def survey_pulls(repo: str, *, kind: str, run: GhFn) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for pull in list_pulls(repo, run=run):
        head = str(pull.pop("_head", "") or "")
        if keep_verdict_pr(kind, pull["labels"], head):
            out.append(as_pull(repo, pull))
    return out


def observe_verdict(
    *,
    heimdall: str = HEIMDALL,
    run: GhFn | None = None,
) -> dict[str, Any]:
    """List open PRs for QA/verdict. Fail closed on gh errors — never idle."""
    run = run or gh
    failed: list[dict[str, str]] = []
    pulls: list[dict[str, Any]] = []
    surveyed = 0

    try:
        catalog = fetch_catalog(run=run, exclude=heimdall)
    except GhError as exc:
        return err(f"catalog: {exc}")

    try:
        pulls.extend(survey_pulls(heimdall, kind="heimdall", run=run))
        surveyed += 1
    except GhError as exc:
        failed.append({"repo": heimdall, "error": str(exc)})

    for name in catalog:
        if name.lower() == heimdall.lower():
            continue
        try:
            pulls.extend(survey_pulls(name, kind="mill", run=run))
            surveyed += 1
        except GhError as exc:
            failed.append({"repo": name, "error": str(exc)})

    heimdall_n = sum(1 for p in pulls if p["repo"].lower() == heimdall.lower())
    mill_n = len(pulls) - heimdall_n
    counts = {
        "catalog": len(catalog),
        "surveyed": surveyed,
        "pulls": len(pulls),
        "heimdall_pulls": heimdall_n,
        "mill_pulls": mill_n,
    }
    fields = {
        "heimdall": heimdall,
        "catalog": catalog,
        "counts": counts,
        "pulls": pulls,
    }
    if failed:
        return err("gh failed; not idle", failed=failed, **fields)
    return ok(**fields)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="observe-verdict",
        description=(
            "Print a JSON envelope of open PRs Heimdall should look at "
            "for QA/verdict. Read-only."
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
    return emit_exit(observe_verdict(heimdall=args.heimdall))


if __name__ == "__main__":
    raise SystemExit(main())
