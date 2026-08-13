"""Promote an existing complete issue to work:ready.

One job: if the issue body+labels already satisfy ISSUE_CRAFT.md, apply
work:ready. Mill catalog (lokay repos.mikolaj92.yaml, never heimdall) also
gets ai:ready by calling dual_label after work:ready is present. Fail closed
on stubs, missing fields, or blocking verdicts. Does not create a second
issue, remove bifrost:in, comment, or wake the mill. Not on the Fala monitor
path.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from typing import Any

from heimdall.craft_ready import (
    BLOCKING_VERDICT,
    HEADINGS,
    PRI_LABELS,
    REQUIRED,
    REPO_RE,
    is_stub,
    validate,
)
from heimdall.dual_label_ready import WORK_READY, add_label, dual_label, is_heimdall
from heimdall.observe_queue import HEIMDALL, GhError, GhFn, gh, gh_json, label_names

ATOM = "ready-apply"
HEADING_RE = re.compile(r"^###\s+(.+?)\s*$", re.MULTILINE)
HEADING_TO_KEY = {heading: key for key, heading in HEADINGS}
NO_RESPONSE = "_No response_"


def ok(**fields: Any) -> dict[str, Any]:
    return {"ok": True, "atom": ATOM, **fields}


def err(message: str, **fields: Any) -> dict[str, Any]:
    return {"ok": False, "atom": ATOM, "error": message, **fields}


def emit(payload: dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(payload, ensure_ascii=False) + "\n")


def emit_exit(payload: dict[str, Any]) -> int:
    emit(payload)
    return 0 if payload.get("ok") else 1


def parse_craft_sections(body: str) -> dict[str, str]:
    """Map ISSUE_CRAFT headings that are present to stripped section bodies."""
    text = (body or "").replace("\r\n", "\n").replace("\r", "\n")
    matches = list(HEADING_RE.finditer(text))
    sections: dict[str, str] = {}
    for i, match in enumerate(matches):
        key = HEADING_TO_KEY.get(match.group(1).strip())
        if key is None:
            continue
        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        value = text[start:end].strip()
        if value == NO_RESPONSE:
            value = ""
        sections[key] = value
    return sections


def pick_unique(labels: list[str], allowed: frozenset[str], kind: str) -> tuple[str, None] | tuple[None, str]:
    found = [lab for lab in labels if lab in allowed]
    if not found:
        return None, f"missing or empty: {kind}"
    if len(found) > 1:
        return None, f"multiple {kind}"
    return found[0], None


def view_issue(repo: str, issue: int, *, run: GhFn) -> dict[str, Any]:
    row = gh_json(
        [
            "issue",
            "view",
            str(issue),
            "-R",
            repo,
            "--json",
            "number,title,body,labels",
        ],
        run=run,
    )
    if not isinstance(row, dict):
        raise GhError(f"issue view for {repo}#{issue} was not an object")
    return row


def spec_from_issue(
    repo: str,
    title: str,
    body: str,
    labels: list[str],
) -> dict[str, Any] | str:
    """Build a craft-ready spec, or an error string."""
    sections = parse_craft_sections(body)
    body_repo: str | None
    if "repo" in sections:
        body_repo = sections["repo"].splitlines()[0].strip() if sections["repo"] else ""
        if body_repo and body_repo.casefold() != repo.casefold():
            return "repo mismatch"
    else:
        body_repo = None
    pri, pri_err = pick_unique(labels, PRI_LABELS, "pri")
    if pri_err:
        return pri_err
    verdicts = [lab for lab in labels if lab.startswith("verdict:")]
    if len(verdicts) > 1:
        return "multiple verdict"

    spec: dict[str, Any] = {}
    for key in REQUIRED:
        if key == "title":
            spec["title"] = (title or "").strip()
        elif key == "pri":
            spec["pri"] = pri or ""
        elif key == "repo":
            spec["repo"] = repo if body_repo is None else body_repo
        else:
            spec[key] = sections.get(key, "")
    if verdicts:
        spec["verdict"] = verdicts[0]
    return spec


def ready_apply(
    repo: str,
    issue: int,
    *,
    heimdall: str = HEIMDALL,
    run: GhFn | None = None,
) -> dict[str, Any]:
    """Apply work:ready on a complete existing issue. Fail closed on craft/gh errors."""
    run = run or gh
    repo = repo.strip()
    base: dict[str, Any] = {"repo": repo, "issue": issue, "added": [], "already": []}

    if not REPO_RE.fullmatch(repo):
        return err(f"invalid repo: {repo}", **base)

    try:
        row = view_issue(repo, issue, run=run)
    except GhError as exc:
        return err(str(exc), **base)

    labels = label_names(row.get("labels"))
    built = spec_from_issue(
        repo,
        str(row.get("title") or ""),
        str(row.get("body") or ""),
        labels,
    )
    if isinstance(built, str):
        return err(built, **base, labels=labels)
    # Craft rules live in craft_ready.validate (REQUIRED / is_stub / BLOCKING_VERDICT).
    message = validate(built)
    if message:
        return err(message, **base, labels=labels)

    added: list[str] = []
    already: list[str] = []
    if WORK_READY in labels:
        already.append(WORK_READY)
    else:
        try:
            add_label(repo, issue, WORK_READY, run=run)
        except GhError as exc:
            return err(str(exc), **base, labels=labels)
        added.append(WORK_READY)
        labels = [*labels, WORK_READY]

    if not is_heimdall(repo, heimdall):
        mill = dual_label(repo, issue, heimdall=heimdall, run=run)
        if mill.get("ok"):
            for lab in mill.get("added") or []:
                if lab not in added:
                    added.append(lab)
                if lab not in labels:
                    labels.append(lab)
            for lab in mill.get("already") or []:
                if lab not in already:
                    already.append(lab)
        elif mill.get("error") != "not a mill-catalog repo":
            return err(
                str(mill.get("error") or "dual_label"),
                repo=repo,
                issue=issue,
                added=added,
                already=already,
                labels=labels,
            )

    return ok(
        repo=repo,
        issue=issue,
        added=added,
        already=already,
        labels=labels,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="ready-apply",
        description=(
            "Promote an existing complete issue to work:ready. Fail closed on "
            "stubs or blocking verdicts. Does not create a second issue or "
            "wake the mill."
        ),
    )
    parser.add_argument("--repo", required=True, help="OWNER/NAME")
    parser.add_argument("--issue", required=True, type=int, help="Issue number")
    parser.add_argument(
        "--heimdall",
        default=HEIMDALL,
        help="Heimdall OWNER/NAME (catalog exclude; work:ready only)",
    )
    args = parser.parse_args(argv)
    import heimdall.observe_queue as observe_queue

    observe_queue._catalog_cache = None
    return emit_exit(
        ready_apply(args.repo, args.issue, heimdall=args.heimdall)
    )


if __name__ == "__main__":
    raise SystemExit(main())
