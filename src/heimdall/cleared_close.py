"""Close a cleared outbound issue after an Influenzer inbound exists.

One job: if issue N has bifrost:out and verdict:pass, and handoff issue M
exists on --to-repo, comment a pointer, then close N. Fail closed. Does
not call Influenzer, apply labels, create issues, wake the mill, or mail.
Issues only. Not on the Fala monitor path.
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from heimdall.craft_inbound import REPO_RE
from heimdall.observe_queue import GhError, GhFn, gh, gh_json, label_names

ATOM = "cleared-close"
OUT = "bifrost:out"
PASS = "verdict:pass"
DEFAULT_TO = "mikolaj92/influenzer"
DEFAULT_COMMENT = "Handed off to {to_repo}#{handoff}. Closed cleared outbound."


def ok(**fields: Any) -> dict[str, Any]:
    return {"ok": True, "atom": ATOM, **fields}


def err(message: str, **fields: Any) -> dict[str, Any]:
    return {"ok": False, "atom": ATOM, "error": message, **fields}


def emit(payload: dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(payload, ensure_ascii=False) + "\n")


def emit_exit(payload: dict[str, Any]) -> int:
    emit(payload)
    return 0 if payload.get("ok") else 1


def pointer_comment(to_repo: str, handoff: int, extra: str | None = None) -> str:
    text = DEFAULT_COMMENT.format(to_repo=to_repo, handoff=handoff)
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
    if OUT not in labels:
        return "missing bifrost:out"
    if PASS not in labels:
        return "missing verdict:pass"
    return None


def cleared_close(
    repo: str,
    issue: int,
    handoff: int,
    *,
    to_repo: str | None = None,
    comment: str | None = None,
    run: GhFn | None = None,
) -> dict[str, Any]:
    """Close cleared outbound N with a pointer to handoff M. Mill untouched."""
    run = run or gh
    repo = repo.strip()
    dest = (to_repo or DEFAULT_TO).strip()
    base: dict[str, Any] = {
        "repo": repo,
        "issue": issue,
        "handoff": handoff,
        "to_repo": dest,
    }

    if not REPO_RE.fullmatch(repo):
        return err(f"invalid repo: {repo}", **base)
    if not REPO_RE.fullmatch(dest):
        return err(f"invalid repo: {dest}", **base)
    if issue == handoff and repo.casefold() == dest.casefold():
        return err("closing itself", **base)

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
            handoff=handoff,
            to_repo=dest,
            closed=False,
            already=["closed"],
            url=url,
        )

    try:
        view_issue(dest, handoff, run=run)
    except GhError as exc:
        return err(str(exc), **base)

    note = pointer_comment(dest, handoff, comment)
    try:
        close_issue(repo, issue, note, run=run)
    except GhError as exc:
        return err(str(exc), **base)

    return ok(
        repo=repo,
        issue=issue,
        handoff=handoff,
        to_repo=dest,
        closed=True,
        already=[],
        url=url,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="cleared-close",
        description=(
            "Close a cleared outbound issue after an Influenzer inbound "
            "exists. Fail closed. Does not call Influenzer or wake the mill. "
            "Issues only; not on the Fala monitor path."
        ),
    )
    parser.add_argument("--repo", required=True, help="OWNER/NAME of the source")
    parser.add_argument("--issue", required=True, type=int, help="Source issue number")
    parser.add_argument(
        "--handoff",
        required=True,
        type=int,
        help="Influenzer inbound issue number on --to-repo",
    )
    parser.add_argument(
        "--to-repo",
        default=DEFAULT_TO,
        help=f"Repo where the handoff issue lives (default {DEFAULT_TO})",
    )
    parser.add_argument(
        "--comment",
        help="Extra sentence appended to the default pointer",
    )
    args = parser.parse_args(argv)
    return emit_exit(
        cleared_close(
            args.repo,
            args.issue,
            args.handoff,
            to_repo=args.to_repo,
            comment=args.comment,
        )
    )


if __name__ == "__main__":
    raise SystemExit(main())
