"""Close a cleared source issue after an Influenzer handoff exists.

One job: close an open bifrost:out + verdict:pass source and point to its
existing handoff issue. Does not create, label, hand off, merge, or run on the
Fala monitor path.
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from heimdall.craft_inbound import REPO_RE
from heimdall.influenzer_handoff import DEFAULT_TO
from heimdall.issue_close import close_with_comment, view_issue
from heimdall.observe_queue import GhError, GhFn, gh, label_names
from heimdall.out_apply import OUT, PASS

ATOM = "cleared-close"


def result(ok: bool, **fields: Any) -> dict[str, Any]:
    return {"ok": ok, "atom": ATOM, **fields}


def emit_exit(payload: dict[str, Any]) -> int:
    sys.stdout.write(json.dumps(payload, ensure_ascii=False) + "\n")
    return 0 if payload["ok"] else 1


def cleared_close(
    repo: str,
    issue: int,
    handoff: int,
    *,
    to_repo: str = DEFAULT_TO,
    run: GhFn | None = None,
) -> dict[str, Any]:
    run = run or gh
    repo = (repo or "").strip()
    to_repo = (to_repo or "").strip()
    base: dict[str, Any] = {
        "repo": repo,
        "issue": issue,
        "handoff": handoff,
        "to_repo": to_repo,
        "closed": False,
        "already": [],
        "url": None,
    }
    if not REPO_RE.fullmatch(repo):
        return result(False, error=f"invalid repo: {repo}", **base)
    if not REPO_RE.fullmatch(to_repo):
        return result(False, error=f"invalid to_repo: {to_repo}", **base)
    if issue <= 0 or handoff <= 0:
        return result(False, error="issue numbers must be positive", **base)
    if repo.casefold() == to_repo.casefold() and issue == handoff:
        return result(False, error="source and handoff issue must differ", **base)

    try:
        source = view_issue(repo, issue, run=run)
    except GhError as exc:
        return result(False, error=str(exc), **base)
    base["url"] = str(source.get("url") or "") or None
    if str(source.get("state") or "").casefold() == "closed":
        base["already"] = ["closed"]
        return result(True, **base)

    labels = label_names(source.get("labels"))
    if OUT not in labels or PASS not in labels:
        return result(False, error=f"source is not {OUT} + {PASS}", **base)

    try:
        destination = view_issue(to_repo, handoff, run=run)
    except GhError as exc:
        return result(False, error=str(exc), **base)
    handoff_url = str(
        destination.get("url") or f"https://github.com/{to_repo}/issues/{handoff}"
    )
    try:
        close_with_comment(
            repo,
            issue,
            f"Handed off to {to_repo}#{handoff}: {handoff_url}",
            run=run,
        )
    except GhError as exc:
        return result(False, error=str(exc), **base)
    base["closed"] = True
    return result(True, **base)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog=ATOM,
        description="Close a cleared source after its Influenzer handoff exists.",
    )
    parser.add_argument("--repo", required=True, help="OWNER/NAME of source")
    parser.add_argument("--issue", required=True, type=int, help="Source issue")
    parser.add_argument("--handoff", required=True, type=int, help="Handoff issue")
    parser.add_argument("--to-repo", default=DEFAULT_TO, help="Handoff OWNER/NAME")
    args = parser.parse_args(argv)
    return emit_exit(
        cleared_close(
            args.repo,
            args.issue,
            args.handoff,
            to_repo=args.to_repo,
        )
    )


if __name__ == "__main__":
    raise SystemExit(main())
