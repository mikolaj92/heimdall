"""Read-only JSON of the GitHub coordination bus.

Heimdall: open work:ready / work:doing / work:blocked issues, and open PRs.
Mill catalog (lokay repos.mikolaj92.yaml, never heimdall): open ai:ready /
ai:in-progress / work:ready / work:doing issues, plus mill-looking open PRs
(ai:pr-opened or similar). Does not apply labels, wake the mill, or mutate.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable

ATOM = "observe-queue"
FALA_REACTION = "github.observe"
HEIMDALL = "mikolaj92/heimdall"
CATALOG_REPO = "mikolaj92/lokay"
CATALOG_PATH = "repos.mikolaj92.yaml"
CATALOG_REF = "main"
LIST_LIMIT = "100"

HEIMDALL_ISSUE_LABELS = frozenset({"work:ready", "work:doing", "work:blocked"})
MILL_ISSUE_LABELS = frozenset(
    {"ai:ready", "ai:in-progress", "work:ready", "work:doing"}
)
MILL_PR_LABELS = frozenset(
    {
        "ai:pr-opened",
        "ai:pr-open",
        "ai:needs-review",
        "ai:request-changes",
        "ai:generated",
        "ai:ci-waiting",
        "ai:repairing",
    }
)

_REPO_NAME_RE = re.compile(
    r"^- name:\s*[\"']?([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)[\"']?\s*$"
)

GhFn = Callable[[list[str]], str]

_catalog_cache: list[str] | None = None


class GhError(RuntimeError):
    """gh failed; caller must not pretend the queue is idle."""


def ok(**fields: Any) -> dict[str, Any]:
    return {"ok": True, "atom": ATOM, **fields}


def err(message: str, **fields: Any) -> dict[str, Any]:
    return {"ok": False, "atom": ATOM, "error": message, **fields}


def write_fala_result(payload: dict[str, Any], *, kind: str) -> None:
    """If Fala set FALA_EFFECTOR_OUTPUT_DIR, write result.json. No Fala import."""
    output_dir = os.environ.get("FALA_EFFECTOR_OUTPUT_DIR")
    if not output_dir:
        return
    path = Path(output_dir) / "result.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "values": payload,
                "associations": [],
                "reactions": [
                    {
                        "kind": kind,
                        "media_type": "application/json",
                        "value": payload,
                    }
                ],
                "metadata": {},
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )


def emit(payload: dict[str, Any], *, fala_kind: str = FALA_REACTION) -> None:
    sys.stdout.write(json.dumps(payload, ensure_ascii=False) + "\n")
    write_fala_result(payload, kind=fala_kind)


def emit_exit(payload: dict[str, Any]) -> int:
    emit(payload)
    return 0 if payload.get("ok") else 1


def gh(args: list[str]) -> str:
    try:
        proc = subprocess.run(
            ["gh", *args],
            check=False,
            text=True,
            capture_output=True,
            timeout=60,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise GhError(str(exc)) from exc
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or f"gh exit {proc.returncode}").strip()
        raise GhError(detail)
    return proc.stdout


def gh_json(args: list[str], *, run: GhFn) -> Any:
    raw = run(args)
    if not raw.strip():
        return []
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise GhError(f"invalid json from gh {' '.join(args)}: {exc}") from exc


def parse_catalog(yaml_text: str, *, exclude: str = HEIMDALL) -> list[str]:
    """Repo names from lokay catalog YAML. Never includes heimdall."""
    names: list[str] = []
    seen: set[str] = set()
    skip = exclude.lower()
    skip_suffix = "/" + skip.split("/", 1)[-1]
    for line in yaml_text.splitlines():
        match = _REPO_NAME_RE.match(line.strip())
        if not match:
            continue
        name = match.group(1)
        key = name.lower()
        if key == skip or key.endswith(skip_suffix):
            continue
        if key in seen:
            continue
        seen.add(key)
        names.append(name)
    if not names:
        raise GhError("no repos parsed from mill catalog")
    return names


def fetch_catalog(*, run: GhFn, exclude: str = HEIMDALL) -> list[str]:
    global _catalog_cache
    if _catalog_cache is not None:
        return list(_catalog_cache)
    text = run(
        [
            "api",
            "-H",
            "Accept: application/vnd.github.raw",
            f"repos/{CATALOG_REPO}/contents/{CATALOG_PATH}?ref={CATALOG_REF}",
        ]
    )
    names = parse_catalog(text, exclude=exclude)
    _catalog_cache = list(names)
    return names


def label_names(raw: object) -> list[str]:
    names: list[str] = []
    if not raw:
        return names
    for item in raw:
        if isinstance(item, str):
            names.append(item)
        elif isinstance(item, dict) and item.get("name"):
            names.append(str(item["name"]))
    return names


def as_item(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "number": int(row["number"]),
        "title": str(row.get("title") or ""),
        "labels": label_names(row.get("labels")),
        "url": str(row.get("url") or ""),
    }


def keep_issue(labels: list[str], wanted: frozenset[str]) -> bool:
    return bool(wanted.intersection(labels))


def mill_pr(labels: list[str], head: str = "") -> bool:
    """Cheap mill/AI PR: ai:pr-opened or similar, or ai/ head ref."""
    for lab in labels:
        if lab in MILL_PR_LABELS or lab.startswith("ai:"):
            return True
    return head.startswith("ai/")


def list_issues(repo: str, *, run: GhFn) -> list[dict[str, Any]]:
    rows = gh_json(
        [
            "issue",
            "list",
            "-R",
            repo,
            "--state",
            "open",
            "--limit",
            LIST_LIMIT,
            "--json",
            "number,title,labels,url",
        ],
        run=run,
    )
    if not isinstance(rows, list):
        raise GhError(f"issue list for {repo} was not a list")
    return [as_item(row) for row in rows if isinstance(row, dict)]


def list_pulls(repo: str, *, run: GhFn) -> list[dict[str, Any]]:
    rows = gh_json(
        [
            "pr",
            "list",
            "-R",
            repo,
            "--state",
            "open",
            "--limit",
            LIST_LIMIT,
            "--json",
            "number,title,labels,url,headRefName",
        ],
        run=run,
    )
    if not isinstance(rows, list):
        raise GhError(f"pr list for {repo} was not a list")
    out: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        item = as_item(row)
        item["_head"] = str(row.get("headRefName") or "")
        out.append(item)
    return out


def survey_repo(
    repo: str,
    *,
    kind: str,
    run: GhFn,
) -> dict[str, Any]:
    issues = list_issues(repo, run=run)
    pulls = list_pulls(repo, run=run)
    if kind == "heimdall":
        issues = [i for i in issues if keep_issue(i["labels"], HEIMDALL_ISSUE_LABELS)]
        pulls = [{k: v for k, v in p.items() if k != "_head"} for p in pulls]
    else:
        issues = [i for i in issues if keep_issue(i["labels"], MILL_ISSUE_LABELS)]
        kept: list[dict[str, Any]] = []
        for pull in pulls:
            head = str(pull.pop("_head", "") or "")
            if mill_pr(pull["labels"], head):
                kept.append(pull)
        pulls = kept
    return {"repo": repo, "kind": kind, "issues": issues, "pulls": pulls}


def observe(*, heimdall: str = HEIMDALL, run: GhFn | None = None) -> dict[str, Any]:
    """Survey the bus. Fail closed on gh errors — never report idle on failure."""
    run = run or gh
    failed: list[dict[str, str]] = []
    repos: list[dict[str, Any]] = []

    try:
        catalog = fetch_catalog(run=run, exclude=heimdall)
    except GhError as exc:
        return err(f"catalog: {exc}")

    try:
        repos.append(survey_repo(heimdall, kind="heimdall", run=run))
    except GhError as exc:
        failed.append({"repo": heimdall, "error": str(exc)})

    for name in catalog:
        try:
            repos.append(survey_repo(name, kind="mill", run=run))
        except GhError as exc:
            failed.append({"repo": name, "error": str(exc)})

    counts = {
        "catalog": len(catalog),
        "surveyed": len(repos),
        "issues": sum(len(r["issues"]) for r in repos),
        "pulls": sum(len(r["pulls"]) for r in repos),
        "heimdall_issues": sum(
            len(r["issues"]) for r in repos if r["kind"] == "heimdall"
        ),
        "heimdall_pulls": sum(
            len(r["pulls"]) for r in repos if r["kind"] == "heimdall"
        ),
        "mill_issues": sum(len(r["issues"]) for r in repos if r["kind"] == "mill"),
        "mill_pulls": sum(len(r["pulls"]) for r in repos if r["kind"] == "mill"),
    }
    fields = {
        "heimdall": heimdall,
        "catalog": catalog,
        "counts": counts,
        "repos": repos,
    }
    if failed:
        return err(
            "gh failed; not idle",
            failed=failed,
            **fields,
        )
    return ok(**fields)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="observe-queue",
        description="Print a JSON envelope of the GitHub coordination bus. Read-only.",
    )
    parser.add_argument(
        "--heimdall",
        default=HEIMDALL,
        help="Heimdall OWNER/NAME (never added to the mill catalog)",
    )
    args = parser.parse_args(argv)
    global _catalog_cache
    _catalog_cache = None
    return emit_exit(observe(heimdall=args.heimdall))


if __name__ == "__main__":
    raise SystemExit(main())
