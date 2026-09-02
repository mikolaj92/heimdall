"""Close a superseded inbound issue after a ready issue exists.

One job: close an open bifrost:in issue that has not itself become a handoff,
and point to the existing work:ready issue. Does not label, create, wake the
mill, or run on the Fala monitor path.
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from heimdall.craft_inbound import REPO_RE
from heimdall.issue_close import close_with_comment, view_issue
from heimdall.observe_queue import GhError, GhFn, gh, label_names

ATOM = "inbound-close"
IN = "bifrost:in"
OUT = "bifrost:out"
READY = "work:ready"


def result(ok: bool, **fields: Any) -> dict[str, Any]:
    return {"ok": ok, "atom": ATOM, **fields}


def emit_exit(payload: dict[str, Any]) -> int:
    sys.stdout.write(json.dumps(payload, ensure_ascii=False) + "\n")
    return 0 if payload["ok"] else 1


def inbound_close(
    repo: str,
    issue: int,
    ready: int,
    *,
    run: GhFn | None = None,
) -> dict[str, Any]:
    run = run or gh
    repo = (repo or "").strip()
    base: dict[str, Any] = {
        "repo": repo,
        "issue": issue,
        "ready": ready,
        "closed": False,
        "already": [],
        "url": None,
    }
    if not REPO_RE.fullmatch(repo):
        return result(False, error=f"invalid repo: {repo}", **base)
    if issue <= 0 or ready <= 0:
        return result(False, error="issue numbers must be positive", **base)
    if issue == ready:
        return result(False, error="inbound and ready issue must differ", **base)

    try:
        source = view_issue(repo, issue, run=run)
    except GhError as exc:
        return result(False, error=str(exc), **base)
    base["url"] = str(source.get("url") or "") or None
    if str(source.get("state") or "").casefold() == "closed":
        base["already"] = ["closed"]
        return result(True, **base)

    labels = label_names(source.get("labels"))
    if IN not in labels:
        return result(False, error=f"source is not {IN}", **base)
    if READY in labels:
        return result(False, error=f"source already has {READY}", **base)
    if OUT in labels:
        return result(False, error=f"source has {OUT}", **base)

    try:
        destination = view_issue(repo, ready, run=run)
    except GhError as exc:
        return result(False, error=str(exc), **base)
    if READY not in label_names(destination.get("labels")):
        return result(False, error=f"ready issue is not {READY}", **base)
    ready_url = str(destination.get("url") or f"https://github.com/{repo}/issues/{ready}")
    try:
        close_with_comment(
            repo,
            issue,
            f"Superseded by ready issue #{ready}: {ready_url}",
            run=run,
        )
    except GhError as exc:
        return result(False, error=str(exc), **base)
    base["closed"] = True
    return result(True, **base)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog=ATOM,
        description="Close a superseded bifrost:in issue after work:ready exists.",
    )
    parser.add_argument("--repo", required=True, help="OWNER/NAME")
    parser.add_argument("--issue", required=True, type=int, help="Inbound issue")
    parser.add_argument("--ready", required=True, type=int, help="Ready issue")
    args = parser.parse_args(argv)
    return emit_exit(inbound_close(args.repo, args.issue, args.ready))


if __name__ == "__main__":
    raise SystemExit(main())
