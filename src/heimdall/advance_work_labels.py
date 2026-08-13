"""Advance work:* on issues linked from a pull request.

Merged PRs that close an issue (GitHub closing keywords in title/body,
plus GraphQL closingIssuesReferences) move work:ready / work:doing →
work:done. Opening such a PR moves work:ready → work:doing.

Only names from labels.yml. Issues with no work:* are ignored.
work:blocked is left alone. Idempotent if already on the target.

From the repo root:

  uv run advance-work-labels              # Actions: PR opened/closed
  uv run advance-work-labels --pr 5       # re-run on a PR (merge path)
  uv run advance-work-labels --self-test
  uv run advance-work-labels --dry-run --event event.json

Repo: --repo OWNER/NAME, else GH_REPO / GITHUB_REPOSITORY, else `gh repo view`.
On pull_request opened/closed, .github/workflows/advance-work-labels.yml runs this.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from heimdall.sync_labels import default_labels_yml, taxonomy_names

WORK_NS = "work:"
WORK_READY = "work:ready"
WORK_DOING = "work:doing"
WORK_DONE = "work:done"
FROM_DONE = frozenset({WORK_READY, WORK_DOING})
FROM_DOING = frozenset({WORK_READY})

# GitHub closing keywords: close(s|d), fix(es|ed), resolve(s|d) + an issue ref.
CLOSING_RE = re.compile(
    r"(?:^|[^A-Za-z])(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?)\s+"
    r"(?:"
    r"https?://github\.com/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)/(?:issues|pull)/(\d+)"
    r"|([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)#(\d+)"
    r"|#(\d+)"
    r")",
    re.IGNORECASE | re.MULTILINE,
)


@dataclass(frozen=True)
class Plan:
    add: frozenset[str]
    remove: frozenset[str]


def detect_repo() -> str:
    env = os.environ.get("GH_REPO") or os.environ.get("GITHUB_REPOSITORY")
    if env:
        return env
    proc = subprocess.run(
        ["gh", "repo", "view", "--json", "nameWithOwner", "-q", ".nameWithOwner"],
        check=True,
        text=True,
        capture_output=True,
    )
    return proc.stdout.strip()


def split_repo(repo: str) -> tuple[str, str]:
    owner, _, name = repo.partition("/")
    if not owner or not name or "/" in name:
        raise SystemExit(f"expected OWNER/NAME, got {repo!r}")
    return owner, name


def same_repo(owner: str, name: str, other_owner: str, other_name: str) -> bool:
    return owner.lower() == other_owner.lower() and name.lower() == other_name.lower()


def gh(args: list[str], *, repo: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["gh", *args, "-R", repo],
        check=True,
        text=True,
        capture_output=True,
    )


def label_names(raw: object) -> set[str]:
    names: set[str] = set()
    if not raw:
        return names
    for item in raw:
        if isinstance(item, str):
            names.add(item)
        elif isinstance(item, dict) and item.get("name"):
            names.add(str(item["name"]))
    return names


def closing_issue_numbers(text: str, repo: str) -> set[int]:
    """Issue numbers referenced by GitHub closing keywords (same repo only)."""
    owner, name = split_repo(repo)
    found: set[int] = set()
    for match in CLOSING_RE.finditer(text or ""):
        url_owner, url_repo, url_n, own, rep, own_n, bare = match.groups()
        if url_n:
            if same_repo(owner, name, url_owner, url_repo):
                found.add(int(url_n))
        elif own_n:
            if same_repo(owner, name, own, rep):
                found.add(int(own_n))
        elif bare:
            found.add(int(bare))
    return found


def graphql_closing_numbers(raw: object, repo: str) -> set[int]:
    owner, name = split_repo(repo)
    found: set[int] = set()
    if not raw:
        return found
    for item in raw:
        if not isinstance(item, dict) or item.get("number") is None:
            continue
        ref = item.get("repository") or {}
        ref_owner = (ref.get("owner") or {}).get("login") if isinstance(ref, dict) else ""
        ref_name = ref.get("name") if isinstance(ref, dict) else ""
        if ref_owner and ref_name and not same_repo(owner, name, str(ref_owner), str(ref_name)):
            continue
        found.add(int(item["number"]))
    return found


def plan_work(
    current: set[str],
    allowed: frozenset[str],
    target: str,
    from_labels: frozenset[str],
) -> Plan | None:
    """Return a label plan, empty Plan if already on target, None to skip."""
    if target not in allowed:
        raise SystemExit(f"refusing to invent label {target}")
    work = {lab for lab in current if lab.startswith(WORK_NS) and lab in allowed}
    if not work:
        return None
    movable = work & from_labels
    if target in work and not movable:
        return Plan(frozenset(), frozenset())
    if not movable:
        return None
    add: set[str] = set()
    remove: set[str] = set()
    if target not in current:
        add.add(target)
    for lab in work:
        if lab != target:
            remove.add(lab)
    return Plan(frozenset(add), frozenset(remove))


def apply_plan(repo: str, number: int, plan: Plan, *, dry_run: bool) -> None:
    if not plan.add and not plan.remove:
        print(f"ok: no-op on {repo}#{number}")
        return
    args = ["issue", "edit", str(number)]
    if plan.add:
        args += ["--add-label", ",".join(sorted(plan.add))]
    if plan.remove:
        args += ["--remove-label", ",".join(sorted(plan.remove))]
    print(f"add {sorted(plan.add) or '-'} ; remove {sorted(plan.remove) or '-'} on {repo}#{number}")
    if dry_run:
        print(f"  gh {' '.join(args)} -R {repo}")
        return
    gh(args, repo=repo)
    print(f"ok: labeled {repo}#{number}")


def load_event(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data.get("pull_request"), dict):
        raise SystemExit("event has no pull_request")
    return data


def fetch_pr(repo: str, number: int) -> tuple[str, str, set[int], bool]:
    proc = gh(
        ["pr", "view", str(number), "--json", "title,body,closingIssuesReferences,mergedAt,state"],
        repo=repo,
    )
    data = json.loads(proc.stdout)
    merged = bool(data.get("mergedAt")) or str(data.get("state") or "").upper() == "MERGED"
    return (
        data.get("title") or "",
        data.get("body") or "",
        graphql_closing_numbers(data.get("closingIssuesReferences"), repo),
        merged,
    )


def fetch_closing_via_graphql(repo: str, number: int) -> set[int]:
    try:
        proc = gh(
            ["pr", "view", str(number), "--json", "closingIssuesReferences"],
            repo=repo,
        )
    except subprocess.CalledProcessError as exc:
        sys.stderr.write(f"warn: closingIssuesReferences: {exc.stderr or exc}\n")
        return set()
    data = json.loads(proc.stdout)
    return graphql_closing_numbers(data.get("closingIssuesReferences"), repo)


def fetch_issue_labels(repo: str, number: int) -> set[str] | None:
    proc = gh(["issue", "view", str(number), "--json", "labels,url"], repo=repo)
    data = json.loads(proc.stdout)
    if "/pull/" in str(data.get("url") or ""):
        return None
    return label_names(data.get("labels"))


def pr_currently_merged(repo: str, number: int) -> bool:
    proc = gh(["pr", "view", str(number), "--json", "mergedAt,state"], repo=repo)
    data = json.loads(proc.stdout)
    return bool(data.get("mergedAt")) or str(data.get("state") or "").upper() == "MERGED"


def linked_issues(repo: str, title: str, body: str, graphql: set[int]) -> set[int]:
    return closing_issue_numbers(f"{title}\n\n{body}", repo) | graphql


def mode_from_event(action: str, merged: bool) -> str | None:
    if action == "closed" and merged:
        return "done"
    if action == "opened":
        return "doing"
    return None


def target_for(mode: str) -> tuple[str, frozenset[str]]:
    if mode == "done":
        return WORK_DONE, FROM_DONE
    if mode == "doing":
        return WORK_DOING, FROM_DOING
    raise SystemExit(f"unknown mode {mode!r}")


def self_test() -> None:
    allowed = taxonomy_names(default_labels_yml())
    assert WORK_READY in allowed and WORK_DOING in allowed and WORK_DONE in allowed
    assert "work:blocked" in allowed
    assert "bug" not in allowed and "enhancement" not in allowed

    repo = "mikolaj92/heimdall"
    assert closing_issue_numbers("Closes #4", repo) == {4}
    assert closing_issue_numbers("this PR closes #4.", repo) == {4}
    assert closing_issue_numbers("Fixes #1, closes #2", repo) == {1, 2}
    assert closing_issue_numbers("Resolved mikolaj92/heimdall#4", repo) == {4}
    assert closing_issue_numbers(
        "Close https://github.com/mikolaj92/heimdall/issues/4", repo
    ) == {4}
    assert closing_issue_numbers("Closes #", repo) == set()
    assert closing_issue_numbers("see #4", repo) == set()
    assert closing_issue_numbers("autoclose #4", repo) == set()
    assert closing_issue_numbers("Closes octo/other#9", repo) == set()
    assert closing_issue_numbers(
        "Fixes https://github.com/octo/other/issues/9", repo
    ) == set()

    template = (
        "Heimdall QA surface\n\n## Issue\n\nCloses #4\n\n"
        "## work:* claim\n\nClaimed: `work:done`\n"
    )
    assert closing_issue_numbers(template, repo) == {4}

    gql = graphql_closing_numbers(
        [
            {
                "number": 4,
                "repository": {
                    "name": "heimdall",
                    "owner": {"login": "mikolaj92"},
                },
            }
        ],
        repo,
    )
    assert gql == {4}
    assert graphql_closing_numbers(
        [{"number": 9, "repository": {"name": "other", "owner": {"login": "octo"}}}],
        repo,
    ) == set()

    ready = {WORK_READY, "pri:p2", "bifrost:in"}
    doing = {WORK_DOING, "pri:p2", "bifrost:in"}
    done = {WORK_DONE, "pri:p2", "bifrost:in"}
    blocked = {"work:blocked", "pri:p2"}
    none = {"bifrost:in", "verdict:hold"}

    to_done = plan_work(ready, allowed, WORK_DONE, FROM_DONE)
    assert to_done == Plan(frozenset({WORK_DONE}), frozenset({WORK_READY}))
    to_done2 = plan_work(doing, allowed, WORK_DONE, FROM_DONE)
    assert to_done2 == Plan(frozenset({WORK_DONE}), frozenset({WORK_DOING}))
    already = plan_work(done, allowed, WORK_DONE, FROM_DONE)
    assert already == Plan(frozenset(), frozenset())
    assert plan_work(blocked, allowed, WORK_DONE, FROM_DONE) is None
    assert plan_work(none, allowed, WORK_DONE, FROM_DONE) is None

    to_doing = plan_work(ready, allowed, WORK_DOING, FROM_DOING)
    assert to_doing == Plan(frozenset({WORK_DOING}), frozenset({WORK_READY}))
    assert plan_work(doing, allowed, WORK_DOING, FROM_DOING) == Plan(frozenset(), frozenset())
    assert plan_work(done, allowed, WORK_DOING, FROM_DOING) is None
    assert plan_work(blocked, allowed, WORK_DOING, FROM_DOING) is None

    messy = plan_work({WORK_READY, WORK_DONE, "pri:p2"}, allowed, WORK_DONE, FROM_DONE)
    assert messy == Plan(frozenset(), frozenset({WORK_READY}))

    assert mode_from_event("closed", True) == "done"
    assert mode_from_event("closed", False) is None
    assert mode_from_event("opened", False) == "doing"
    assert mode_from_event("edited", False) is None

    print("ok: self-test")


def advance(
    repo: str,
    issues: set[int],
    mode: str,
    allowed: frozenset[str],
    *,
    dry_run: bool,
) -> None:
    target, from_labels = target_for(mode)
    if not issues:
        print(f"ok: no closing issues ({mode})")
        return
    for number in sorted(issues):
        try:
            current = fetch_issue_labels(repo, number)
        except subprocess.CalledProcessError as exc:
            sys.stderr.write(f"warn: skip {repo}#{number}: {exc.stderr or exc}\n")
            continue
        if current is None:
            print(f"ok: skip {repo}#{number} (pull request, not an issue)")
            continue
        plan = plan_work(current, allowed, target, from_labels)
        if plan is None:
            print(f"ok: skip {repo}#{number} (no movable work:*)")
            continue
        apply_plan(repo, number, plan, dry_run=dry_run)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", help="OWNER/NAME (default: current gh repo)")
    parser.add_argument("--pr", type=int, help="pull request number (else GITHUB_EVENT_PATH)")
    parser.add_argument("--event", type=Path, help="GitHub event JSON (default: GITHUB_EVENT_PATH)")
    parser.add_argument(
        "--mode",
        choices=("done", "doing"),
        help="override: done on merge, doing on open",
    )
    parser.add_argument("--dry-run", action="store_true", help="print actions only")
    parser.add_argument("--self-test", action="store_true", help="run parser fixtures")
    args = parser.parse_args(argv)

    if args.self_test:
        self_test()
        return 0

    allowed = taxonomy_names(default_labels_yml())
    repo = args.repo or detect_repo()

    graphql: set[int] = set()
    live_merged: bool | None = None
    if args.pr is not None:
        number = args.pr
        title, body, graphql, live_merged = fetch_pr(repo, number)
        if args.mode == "doing":
            action, merged = "opened", False
        elif args.mode == "done" or live_merged:
            action, merged = "closed", True
        else:
            action, merged = "opened", False
    else:
        event_path = args.event or Path(os.environ.get("GITHUB_EVENT_PATH") or "")
        if not event_path or not event_path.is_file():
            raise SystemExit("need --pr, --event, or GITHUB_EVENT_PATH")
        event = load_event(event_path)
        pr = event["pull_request"]
        number = int(pr["number"])
        title = pr.get("title") or ""
        body = pr.get("body") or ""
        action = str(event.get("action") or "")
        merged = bool(pr.get("merged"))
        graphql = fetch_closing_via_graphql(repo, number)

    mode = args.mode or mode_from_event(action, merged)
    if mode is None:
        print(f"ok: no-op on pull_request {action} merged={merged}")
        return 0

    if mode == "doing" and not args.mode:
        try:
            if live_merged is None:
                live_merged = pr_currently_merged(repo, number)
            if live_merged:
                print(f"ok: skip doing; {repo} PR {number} already merged")
                return 0
        except subprocess.CalledProcessError as exc:
            sys.stderr.write(f"warn: merge check: {exc.stderr or exc}\n")

    issues = linked_issues(repo, title, body, graphql)
    advance(repo, issues, mode, allowed, dry_run=args.dry_run)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except subprocess.CalledProcessError as exc:
        sys.stderr.write(exc.stderr or str(exc))
        raise SystemExit(exc.returncode)
