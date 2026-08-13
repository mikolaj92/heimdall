"""Close a superseded inbound triage issue after a new ready issue exists.

One job: if issue N is inbound (bifrost:in) and is not a Lokay handoff
(work:ready) and not outbound (bifrost:out), comment a pointer to ready
issue M, then close N. Fail closed. Does not apply work:ready, create
issues, wake the mill, or mail. Not on the Fala monitor path.
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from heimdall.craft_inbound import REPO_RE
from heimdall.observe_queue import GhError, GhFn, gh, gh_json, label_names

ATOM = "inbound-close"
INBOUND = "bifrost:in"
OUTBOUND = "bifrost:out"
WORK_READY = "work:ready"
DEFAULT_COMMENT = (
    "Superseded by #{ready}. Closed inbound; work lives on the ready issue."
)


def ok(**fields: Any) -> dict[str, Any]:
    return {"ok": True, "atom": ATOM, **fields}


def err(message: str, **fields: Any) -> dict[str, Any]:
    return {"ok": False, "atom": ATOM, "error": message, **fields}


def emit(payload: dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(payload, ensure_ascii=False) + "\n")


def emit_exit(payload: dict[str, Any]) -> int:
    emit(payload)
    return 0 if payload.get("ok") else 1


def pointer_comment(ready: int, extra: str | None = None) -> str:
    text = DEFAULT_COMMENT.format(ready=ready)
    note = (extra or "").strip()
    if note:
        return f"{text} {note}"
    return text


def view_issue(repo: str, issue: int, *, run: GhFn) -> dict[str, Any]:
    row = gh_json(
        [
            "issue",
            "view",
            str(issue),
            "-R",
            repo,
            "--json",
            "number,state,labels,url",
        ],
        run=run,
    )
    if not isinstance(row, dict):
        raise GhError(f"issue view for {repo}#{issue} was not an object")
    return row


def close_issue(repo: str, issue: int, comment: str, *, run: GhFn) -> None:
    run(
        [
            "issue",
            "close",
            str(issue),
            "-R",
            repo,
            "--comment",
            comment,
        ]
    )


def refuse_labels(labels: list[str]) -> str | None:
    if WORK_READY in labels:
        return "has work:ready"
    if OUTBOUND in labels:
        return "has bifrost:out"
    if INBOUND not in labels:
        return "missing bifrost:in"
    return None


def inbound_close(
    repo: str,
    issue: int,
    ready: int,
    *,
    comment: str | None = None,
    run: GhFn | None = None,
) -> dict[str, Any]:
    """Close inbound N with a pointer to ready M. Fail closed. Mill untouched."""
    run = run or gh
    repo = repo.strip()
    base: dict[str, Any] = {"repo": repo, "issue": issue, "ready": ready}

    if not REPO_RE.fullmatch(repo):
        return err(f"invalid repo: {repo}", **base)
    if issue == ready:
        return err("issue equals ready", **base)

    try:
        row = view_issue(repo, issue, run=run)
    except GhError as exc:
        return err(str(exc), **base)

    labels = label_names(row.get("labels"))
    blocked = refuse_labels(labels)
    if blocked:
        return err(blocked, **base)

    url = str(row.get("url") or "")
    state = str(row.get("state") or "").casefold()
    if state == "closed":
        return ok(
            repo=repo,
            issue=issue,
            ready=ready,
            closed=False,
            already=["closed"],
            url=url,
        )

    try:
        view_issue(repo, ready, run=run)
    except GhError as exc:
        return err(str(exc), **base)

    note = pointer_comment(ready, comment)
    try:
        close_issue(repo, issue, note, run=run)
    except GhError as exc:
        return err(str(exc), **base)

    return ok(
        repo=repo,
        issue=issue,
        ready=ready,
        closed=True,
        already=[],
        url=url,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="inbound-close",
        description=(
            "Close a superseded inbound triage issue after a new ready issue "
            "exists. Fail closed. Does not apply work:ready or wake the mill."
        ),
    )
    parser.add_argument("--repo", required=True, help="OWNER/NAME")
    parser.add_argument("--issue", required=True, type=int, help="Inbound issue number")
    parser.add_argument(
        "--ready",
        required=True,
        type=int,
        help="Ready issue number on the same repo",
    )
    parser.add_argument(
        "--comment",
        help="Extra sentence appended to the default pointer",
    )
    args = parser.parse_args(argv)
    return emit_exit(
        inbound_close(args.repo, args.issue, args.ready, comment=args.comment)
    )


if __name__ == "__main__":
    raise SystemExit(main())
