"""Apply one Heimdall verdict:* label on an issue or PR.

Taxonomy from labels.yml verdict namespace. One verdict:* at a time: add
the chosen label, remove other verdict:* taxonomy labels. Optional comment.
Does not wake the mill, merge, dual-label, mail, or call Influenzer.
Not on the Fala monitor path.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

from heimdall.observe_queue import GhError, GhFn, gh, gh_json, label_names

ATOM = "verdict-apply"
VERDICT_NAME_RE = re.compile(
    r"^- name:\s*[\"']?(verdict:[A-Za-z0-9_-]+)[\"']?\s*$"
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


def default_labels_yml() -> Path:
    here = Path.cwd() / "labels.yml"
    if here.is_file():
        return here
    return Path(__file__).resolve().parents[2] / "labels.yml"


def parse_verdict_labels(text: str) -> frozenset[str]:
    """Names under the verdict namespace in labels.yml."""
    names: list[str] = []
    for line in text.splitlines():
        match = VERDICT_NAME_RE.match(line.strip())
        if match:
            names.append(match.group(1))
    if not names:
        raise ValueError("no verdict labels in labels.yml")
    return frozenset(names)


def load_verdict_labels(path: Path | None = None) -> frozenset[str]:
    path = path or default_labels_yml()
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ValueError(f"labels.yml: {exc}") from exc
    return parse_verdict_labels(text)


def target_kind(issue: int | None, pr: int | None) -> tuple[str, int] | str:
    if issue is not None and pr is not None:
        return "use --issue or --pr, not both"
    if issue is not None:
        return ("issue", issue)
    if pr is not None:
        return ("pr", pr)
    return "missing --issue or --pr"


def view_target(kind: str, repo: str, number: int, *, run: GhFn) -> dict[str, Any]:
    row = gh_json(
        [kind, "view", str(number), "-R", repo, "--json", "number,labels"],
        run=run,
    )
    if not isinstance(row, dict):
        raise GhError(f"{kind} view for {repo}#{number} was not an object")
    return row


def edit_labels(
    kind: str,
    repo: str,
    number: int,
    add: list[str],
    remove: list[str],
    *,
    run: GhFn,
) -> None:
    args = [kind, "edit", str(number), "-R", repo]
    for lab in add:
        args.extend(["--add-label", lab])
    for lab in remove:
        args.extend(["--remove-label", lab])
    run(args)


def add_comment(
    kind: str,
    repo: str,
    number: int,
    body: str,
    *,
    run: GhFn,
) -> None:
    run([kind, "comment", str(number), "-R", repo, "--body", body])


def apply_verdict(
    repo: str,
    verdict: str,
    *,
    issue: int | None = None,
    pr: int | None = None,
    comment: str | None = None,
    allowed: frozenset[str] | None = None,
    labels_yml: Path | None = None,
    run: GhFn | None = None,
) -> dict[str, Any]:
    """Apply one verdict:* taxonomy label. Fail closed on gh / unknown verdict."""
    run = run or gh
    repo = repo.strip()
    verdict = verdict.strip()
    note = (comment or "").strip() or None
    base: dict[str, Any] = {"repo": repo, "added": [], "removed": []}

    picked = target_kind(issue, pr)
    if isinstance(picked, str):
        return err(picked, **base)
    kind, number = picked
    base[kind] = number

    if not repo:
        return err("missing repo", **base)

    if allowed is None:
        try:
            allowed = load_verdict_labels(labels_yml)
        except ValueError as exc:
            return err(str(exc), **base)

    if verdict not in allowed:
        return err(f"unknown verdict: {verdict}", **base)

    try:
        row = view_target(kind, repo, number, run=run)
    except GhError as exc:
        return err(str(exc), **base)

    labels = label_names(row.get("labels"))
    present = [lab for lab in labels if lab in allowed]
    add = [] if verdict in present else [verdict]
    remove = sorted(lab for lab in present if lab != verdict)

    try:
        if add or remove:
            edit_labels(kind, repo, number, add, remove, run=run)
    except GhError as exc:
        return err(str(exc), **base)

    if note:
        try:
            add_comment(kind, repo, number, note, run=run)
        except GhError as exc:
            return err(str(exc), repo=repo, added=add, removed=remove, **{kind: number})

    return ok(repo=repo, added=add, removed=remove, **{kind: number})


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="verdict-apply",
        description=(
            "Apply one Heimdall verdict:* taxonomy label on an issue or PR. "
            "Removes other verdict:* taxonomy labels. Does not wake the mill."
        ),
    )
    parser.add_argument("--repo", required=True, help="OWNER/NAME")
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--issue", type=int, help="Issue number")
    target.add_argument("--pr", type=int, help="Pull request number")
    parser.add_argument(
        "--verdict",
        required=True,
        help="verdict:* from labels.yml (pass/hold/reject/needs-scout)",
    )
    parser.add_argument("--comment", help="Optional comment body")
    args = parser.parse_args(argv)
    return emit_exit(
        apply_verdict(
            args.repo,
            args.verdict,
            issue=args.issue,
            pr=args.pr,
            comment=args.comment,
        )
    )


if __name__ == "__main__":
    raise SystemExit(main())
