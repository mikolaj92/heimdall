"""Small GitHub issue primitives shared by close atoms."""

from __future__ import annotations

from typing import Any

from heimdall.observe_queue import GhError, GhFn, gh_json


def view_issue(repo: str, number: int, *, run: GhFn) -> dict[str, Any]:
    row = gh_json(
        ["issue", "view", str(number), "-R", repo, "--json", "number,state,labels,url"],
        run=run,
    )
    if not isinstance(row, dict):
        raise GhError(f"issue view for {repo}#{number} was not an object")
    return row


def close_with_comment(
    repo: str, number: int, comment: str, *, run: GhFn
) -> None:
    run(["issue", "close", str(number), "-R", repo, "--comment", comment])
