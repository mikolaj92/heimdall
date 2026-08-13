"""File a bifrost:in triage issue on Influenzer after QA outbound+pass.

Given a source issue/PR that already has bifrost:out + verdict:pass and an
http(s) artifact URL, craft-inbound on mikolaj92/influenzer (or --to-repo)
so Influenzer can sell. Never work:ready or ai:ready. Does not call
out-apply, wake the mill, or sit on the Fala monitor path.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

from heimdall.craft_inbound import REPO_RE, craft_inbound, default_labels_yml
from heimdall.observe_queue import GhError, GhFn, gh, label_names
from heimdall.out_apply import OUT, PASS, check_artifact
from heimdall.verdict_apply import target_kind, view_target

ATOM = "influenzer-handoff"
DEFAULT_TO = "mikolaj92/influenzer"
SIGNAL = "signal:feedback"
SOURCE = "source:github"
HOLD = "verdict:hold"
STORY_NAME_RE = re.compile(
    r"^- name:\s*[\"']?(story:[A-Za-z0-9_-]+)[\"']?\s*$"
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


def parse_story_labels(text: str) -> frozenset[str]:
    """Names under the story namespace in labels.yml."""
    names: list[str] = []
    for line in text.splitlines():
        match = STORY_NAME_RE.match(line.strip())
        if match:
            names.append(match.group(1))
    if not names:
        raise ValueError("no story labels in labels.yml")
    return frozenset(names)


def load_story_labels(path: Path | None = None) -> frozenset[str]:
    path = path or default_labels_yml()
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ValueError(f"labels.yml: {exc}") from exc
    return parse_story_labels(text)


def source_url(repo: str, kind: str, number: int) -> str:
    slug = "pull" if kind == "pr" else "issues"
    return f"https://github.com/{repo}/{slug}/{number}"


def inbound_spec(
    *,
    dest: str,
    source_repo: str,
    kind: str,
    number: int,
    story: str,
    artifact: str,
    comment: str | None,
) -> dict[str, Any]:
    note = (comment or "").strip()
    parts: list[str] = []
    if note:
        parts.append(note)
    parts.append(story)
    parts.append(artifact)
    ref = f"{source_repo}#{number}"
    return {
        "title": f"{story} from {ref}",
        "signal": SIGNAL,
        "source": SOURCE,
        "summary": "\n\n".join(parts),
        "fit": (
            f"In scope for Influenzer to sell. Source {source_url(source_repo, kind, number)} "
            f"({ref}) already {OUT} + {PASS}. Not engineering; never work:ready."
        ),
        "proposed_verdict": HOLD,
        "repo": dest,
    }


def handoff(
    repo: str,
    *,
    artifact: str | None = None,
    story: str | None = None,
    issue: int | None = None,
    pr: int | None = None,
    comment: str | None = None,
    to_repo: str | None = None,
    stories: frozenset[str] | None = None,
    labels_yml: Path | None = None,
    run: GhFn | None = None,
) -> dict[str, Any]:
    """File influenzer inbound from a source that already passed outbound."""
    run = run or gh
    repo = (repo or "").strip()
    dest = (to_repo or DEFAULT_TO).strip()
    url = (artifact or "").strip()
    chosen = (story or "").strip()
    base: dict[str, Any] = {"from": repo, "to": dest, "artifact": url}

    picked = target_kind(issue, pr)
    if isinstance(picked, str):
        return err(picked, **base)
    kind, number = picked

    if not repo:
        return err("missing repo", **base)
    if not dest:
        return err("missing or empty: repo", **base)
    if not REPO_RE.fullmatch(dest):
        return err(f"invalid repo: {dest}", **base)

    artifact_err = check_artifact(url)
    if artifact_err:
        return err(artifact_err, **base)

    if stories is None:
        try:
            stories = load_story_labels(labels_yml)
        except ValueError as exc:
            return err(str(exc), **base)
    if not chosen:
        return err("missing story", **base)
    if chosen not in stories:
        return err(f"unknown story: {chosen}", **base)

    try:
        row = view_target(kind, repo, number, run=run)
    except GhError as exc:
        return err(str(exc), **base)

    labels = label_names(row.get("labels"))
    if OUT not in labels or PASS not in labels:
        return err(f"source is not {OUT} + {PASS}", **base)

    spec = inbound_spec(
        dest=dest,
        source_repo=repo,
        kind=kind,
        number=number,
        story=chosen,
        artifact=url,
        comment=comment,
    )
    filed = craft_inbound(spec, run=run, labels_yml=labels_yml)
    if not filed.get("ok"):
        return err(str(filed.get("error") or "craft-inbound failed"), **base)
    return ok(
        **{
            "from": repo,
            "to": dest,
            "issue": filed["issue"],
            "url": filed["url"],
            "artifact": url,
        }
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="influenzer-handoff",
        description=(
            "File a bifrost:in triage issue on Influenzer after a source "
            "issue/PR already has bifrost:out + verdict:pass. Reuses "
            "craft-inbound. Never work:ready. Does not call out-apply or "
            "wake the mill."
        ),
    )
    parser.add_argument("--repo", required=True, help="OWNER/NAME of the source")
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--issue", type=int, help="Source issue number")
    target.add_argument("--pr", type=int, help="Source pull request number")
    parser.add_argument(
        "--artifact",
        required=True,
        help="http(s) artifact URL (required; source must already be outbound+pass)",
    )
    parser.add_argument(
        "--story",
        required=True,
        help="story:* from labels.yml (required; body only, not a label on Influenzer)",
    )
    parser.add_argument(
        "--to-repo",
        default=DEFAULT_TO,
        help=f"Influenzer repo (default {DEFAULT_TO})",
    )
    parser.add_argument("--comment", help="Optional Signal summary")
    args = parser.parse_args(argv)
    return emit_exit(
        handoff(
            args.repo,
            artifact=args.artifact,
            story=args.story,
            issue=args.issue,
            pr=args.pr,
            comment=args.comment,
            to_repo=args.to_repo,
        )
    )


if __name__ == "__main__":
    raise SystemExit(main())
