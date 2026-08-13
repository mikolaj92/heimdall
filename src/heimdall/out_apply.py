"""Mark an issue or PR as outbound that may ship.

Applies bifrost:out and verdict:pass together from labels.yml. Replaces other
verdict:* and other bifrost:* so there is one direction (out) and one gate
(pass). Fail closed unless an http(s) artifact URL is provided. Optional
comment. Does not wake the mill, mail, dual-label, or call Influenzer
(Influenzer reads verdict:pass). Not on the Fala monitor path.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from heimdall.observe_queue import GhError, GhFn, gh, label_names
from heimdall.verdict_apply import (
    add_comment,
    default_labels_yml,
    edit_labels,
    parse_verdict_labels,
    target_kind,
    view_target,
)

ATOM = "out-apply"
OUT = "bifrost:out"
PASS = "verdict:pass"
BIFROST_NAME_RE = re.compile(
    r"^- name:\s*[\"']?(bifrost:[A-Za-z0-9_-]+)[\"']?\s*$"
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


def parse_bifrost_labels(text: str) -> frozenset[str]:
    """Names under the bifrost namespace in labels.yml."""
    names: list[str] = []
    for line in text.splitlines():
        match = BIFROST_NAME_RE.match(line.strip())
        if match:
            names.append(match.group(1))
    if not names:
        raise ValueError("no bifrost labels in labels.yml")
    return frozenset(names)


def load_allowed(
    path: Path | None = None,
) -> tuple[frozenset[str], frozenset[str]]:
    path = path or default_labels_yml()
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ValueError(f"labels.yml: {exc}") from exc
    return parse_bifrost_labels(text), parse_verdict_labels(text)


def check_artifact(value: str | None) -> str | None:
    """Error if missing/empty or not an http(s) URL; else None."""
    url = (value or "").strip()
    if not url:
        return "missing artifact"
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        return "artifact must be an http(s) URL"
    return None


def ns_plan(
    labels: list[str], chosen: str, allowed: frozenset[str]
) -> tuple[list[str], list[str]]:
    """Add chosen if absent; remove other taxonomy labels in the same namespace."""
    present = [lab for lab in labels if lab in allowed]
    add = [] if chosen in present else [chosen]
    remove = sorted(lab for lab in present if lab != chosen)
    return add, remove


def apply_out(
    repo: str,
    *,
    artifact: str | None = None,
    issue: int | None = None,
    pr: int | None = None,
    comment: str | None = None,
    bifrost_allowed: frozenset[str] | None = None,
    verdict_allowed: frozenset[str] | None = None,
    labels_yml: Path | None = None,
    run: GhFn | None = None,
) -> dict[str, Any]:
    """Apply bifrost:out + verdict:pass. Fail closed without an artifact URL."""
    run = run or gh
    repo = repo.strip()
    url = (artifact or "").strip()
    note = (comment or "").strip() or None
    base: dict[str, Any] = {
        "repo": repo,
        "artifact": url,
        "added": [],
        "removed": [],
    }

    picked = target_kind(issue, pr)
    if isinstance(picked, str):
        return err(picked, **base)
    kind, number = picked
    base[kind] = number

    if not repo:
        return err("missing repo", **base)

    artifact_err = check_artifact(url)
    if artifact_err:
        return err(artifact_err, **base)

    if bifrost_allowed is None or verdict_allowed is None:
        try:
            loaded_bifrost, loaded_verdict = load_allowed(labels_yml)
        except ValueError as exc:
            return err(str(exc), **base)
        bifrost_allowed = bifrost_allowed or loaded_bifrost
        verdict_allowed = verdict_allowed or loaded_verdict

    if OUT not in bifrost_allowed:
        return err(f"unknown bifrost: {OUT}", **base)
    if PASS not in verdict_allowed:
        return err(f"unknown verdict: {PASS}", **base)

    try:
        row = view_target(kind, repo, number, run=run)
    except GhError as exc:
        return err(str(exc), **base)

    labels = label_names(row.get("labels"))
    add_out, remove_out = ns_plan(labels, OUT, bifrost_allowed)
    add_pass, remove_pass = ns_plan(labels, PASS, verdict_allowed)
    add = add_out + add_pass
    remove = sorted(remove_out + remove_pass)

    try:
        if add or remove:
            edit_labels(kind, repo, number, add, remove, run=run)
    except GhError as exc:
        return err(str(exc), **base)

    if note:
        try:
            add_comment(kind, repo, number, note, run=run)
        except GhError as exc:
            return err(
                str(exc),
                repo=repo,
                artifact=url,
                added=add,
                removed=remove,
                **{kind: number},
            )

    return ok(repo=repo, artifact=url, added=add, removed=remove, **{kind: number})


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="out-apply",
        description=(
            "Mark an issue or PR as outbound that may ship: apply bifrost:out "
            "and verdict:pass. Requires an http(s) artifact URL. Does not wake "
            "the mill or call Influenzer."
        ),
    )
    parser.add_argument("--repo", required=True, help="OWNER/NAME")
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--issue", type=int, help="Issue number")
    target.add_argument("--pr", type=int, help="Pull request number")
    parser.add_argument(
        "--artifact",
        required=True,
        help="http(s) artifact URL (required for verdict:pass on outbound)",
    )
    parser.add_argument("--comment", help="Optional comment body")
    args = parser.parse_args(argv)
    return emit_exit(
        apply_out(
            args.repo,
            artifact=args.artifact,
            issue=args.issue,
            pr=args.pr,
            comment=args.comment,
        )
    )


if __name__ == "__main__":
    raise SystemExit(main())
