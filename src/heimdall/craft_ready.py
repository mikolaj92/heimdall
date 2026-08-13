"""Create a GitHub issue that satisfies ISSUE_CRAFT.md.

Fail closed if required fields are missing or empty. Files work:ready on the
target repo. Mill catalog (lokay repos.mikolaj92.yaml, never heimdall) also
gets ai:ready at create. Heimdall: work:ready only. Does not wake the mill,
SSH, merge, open probe issues, or send mail.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

from heimdall.dual_label_ready import in_catalog, is_heimdall
from heimdall.observe_queue import HEIMDALL, GhError, GhFn, fetch_catalog, gh

ATOM = "craft-ready"
WORK_READY = "work:ready"
AI_READY = "ai:ready"
BIFROST_IN = "bifrost:in"
DEFAULT_VERDICT = "verdict:pass"

REQUIRED = (
    "title",
    "problem",
    "scope",
    "repo",
    "acceptance",
    "constraints",
    "artifact_qa",
    "pri",
)
PRI_LABELS = frozenset({"pri:p0", "pri:p1", "pri:p2", "pri:p3"})
VERDICT_LABELS = frozenset(
    {
        "verdict:pass",
        "verdict:hold",
        "verdict:reject",
        "verdict:needs-scout",
    }
)
BLOCKING_VERDICT = frozenset(
    {"verdict:hold", "verdict:reject", "verdict:needs-scout"}
)
STUB_EXACT = frozenset({"tbd", "todo", "stub"})
STUB_PHRASE = re.compile(r"lokay will figure it out", re.IGNORECASE)
REPO_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
ISSUE_URL_RE = re.compile(
    r"https://github\.com/[^/\s]+/[^/\s]+/issues/(\d+)",
    re.IGNORECASE,
)

HEADINGS = (
    ("problem", "Problem"),
    ("scope", "Scope"),
    ("repo", "Repo"),
    ("acceptance", "Acceptance"),
    ("constraints", "Constraints"),
    ("artifact_qa", "Artifact / QA"),
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


def field(spec: dict[str, Any], key: str) -> str:
    value = spec.get(key)
    if not isinstance(value, str):
        return ""
    return value.strip()


def is_stub(text: str) -> bool:
    if text.casefold() in STUB_EXACT:
        return True
    return STUB_PHRASE.search(text) is not None


def validate(spec: dict[str, Any]) -> str | None:
    missing = [key for key in REQUIRED if not field(spec, key)]
    if missing:
        return f"missing or empty: {', '.join(missing)}"
    for key in REQUIRED:
        if is_stub(field(spec, key)):
            return f"stub in {key}"
    pri = field(spec, "pri")
    if pri not in PRI_LABELS:
        return f"invalid pri: {pri}"
    repo = field(spec, "repo")
    if not REPO_RE.fullmatch(repo):
        return f"invalid repo: {repo}"
    if "verdict" in spec:
        verdict = field(spec, "verdict")
        if not verdict:
            return "missing or empty: verdict"
        if verdict not in VERDICT_LABELS:
            return f"invalid verdict: {verdict}"
        if verdict in BLOCKING_VERDICT:
            return f"cannot craft work:ready with {verdict}"
    return None


def verdict_label(spec: dict[str, Any]) -> str:
    if "verdict" not in spec:
        return DEFAULT_VERDICT
    return field(spec, "verdict")


def issue_body(spec: dict[str, Any]) -> str:
    chunks = [
        f"### {heading}\n\n{field(spec, key)}" for key, heading in HEADINGS
    ]
    return "\n\n".join(chunks) + "\n"


def parse_issue_url(raw: str) -> tuple[int, str]:
    text = (raw or "").strip()
    if not text:
        raise GhError("empty gh issue create output")
    for line in reversed(text.splitlines()):
        match = ISSUE_URL_RE.search(line.strip())
        if match:
            url = match.group(0)
            return int(match.group(1)), url
    raise GhError(f"could not parse issue url from gh: {text}")


def create_issue(
    repo: str,
    title: str,
    body: str,
    labels: list[str],
    *,
    run: GhFn,
) -> tuple[int, str]:
    args = [
        "issue",
        "create",
        "-R",
        repo,
        "--title",
        title,
        "--body",
        body,
    ]
    for lab in labels:
        args.extend(["--label", lab])
    return parse_issue_url(run(args))


def craft_labels(spec: dict[str, Any], *, mill: bool) -> list[str]:
    labels = [
        WORK_READY,
        field(spec, "pri"),
        BIFROST_IN,
        verdict_label(spec),
    ]
    if mill:
        labels.append(AI_READY)
    return labels


def parse_spec(text: str) -> dict[str, Any]:
    try:
        spec = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid json: {exc}") from exc
    if not isinstance(spec, dict):
        raise ValueError("spec must be a JSON object")
    return spec


def craft_ready(
    spec: dict[str, Any],
    *,
    heimdall: str = HEIMDALL,
    run: GhFn | None = None,
) -> dict[str, Any]:
    """File a work:ready issue. Fail closed on missing fields or gh errors."""
    run = run or gh
    message = validate(spec)
    if message:
        return err(message)

    repo = field(spec, "repo")
    mill = False
    if not is_heimdall(repo, heimdall):
        try:
            catalog = fetch_catalog(run=run, exclude=heimdall)
        except GhError as exc:
            return err(f"catalog: {exc}", repo=repo)
        mill = in_catalog(repo, catalog)

    labels = craft_labels(spec, mill=mill)
    try:
        issue, url = create_issue(
            repo,
            field(spec, "title"),
            issue_body(spec),
            labels,
            run=run,
        )
    except GhError as exc:
        return err(str(exc), repo=repo)
    return ok(repo=repo, issue=issue, url=url, labels=labels)


def craft_from_text(text: str, *, run: GhFn | None = None) -> dict[str, Any]:
    try:
        spec = parse_spec(text)
    except ValueError as exc:
        return err(str(exc))
    return craft_ready(spec, run=run)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="craft-ready",
        description=(
            "Create a GitHub issue that satisfies ISSUE_CRAFT.md. "
            "Fail closed on missing fields. Does not wake the mill."
        ),
    )
    parser.add_argument(
        "--file",
        help="JSON spec path. Stdin if omitted.",
    )
    args = parser.parse_args(argv)
    try:
        if args.file:
            text = Path(args.file).read_text(encoding="utf-8")
        else:
            text = sys.stdin.read()
    except OSError as exc:
        return emit_exit(err(str(exc)))
    import heimdall.observe_queue as observe_queue

    observe_queue._catalog_cache = None
    return emit_exit(craft_from_text(text))


if __name__ == "__main__":
    raise SystemExit(main())
