"""Apply taxonomy labels from inbound / work-ready issue-form dropdowns.

GitHub renders each dropdown as `### Heading` then the chosen option
(`source:github`). Only exact names from labels.yml are applied.

  inbound     — source:*, signal:*; replace verdict:hold if another
                verdict:* is chosen. Never applies work:ready.
  work-ready  — chosen pri:* only (exactly one). Does not strip work:ready.
  other       — no-op

Idempotent. From the repo root:

  uv run auto-label-issue              # Actions: issues opened/edited
  uv run auto-label-issue --issue 12   # re-run on an existing issue
  uv run auto-label-issue --self-test
  uv run auto-label-issue --dry-run --body-file body.md --current-labels bifrost:in,verdict:hold

Repo: --repo OWNER/NAME, else GH_REPO / GITHUB_REPOSITORY, else `gh repo view`.
On issue opened/edited, .github/workflows/auto-label-issues.yml runs this.
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

HEADING_RE = re.compile(r"^###\s+(.+?)\s*$", re.MULTILINE)

INBOUND_HEADINGS = ("Source", "Signal kind")
INBOUND_FIELDS = {
    "Source": "source",
    "Signal kind": "signal",
    "Proposed verdict": "verdict",
}
WORK_READY_HEADINGS = ("Priority", "Problem")
WORK_READY_FIELDS = {
    "Priority": "pri",
}


@dataclass(frozen=True)
class Plan:
    add: frozenset[str]
    remove: frozenset[str]


def parse_issue_form(body: str) -> dict[str, str]:
    """Map `### Heading` → first non-empty line of that section."""
    if not body:
        return {}
    text = body.replace("\r\n", "\n").replace("\r", "\n")
    matches = list(HEADING_RE.finditer(text))
    fields: dict[str, str] = {}
    for i, match in enumerate(matches):
        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        value = ""
        for line in text[start:end].splitlines():
            stripped = line.strip()
            if not stripped or stripped == "_No response_":
                continue
            if stripped.startswith("<!--") and stripped.endswith("-->"):
                continue
            value = stripped
            break
        fields[match.group(1).strip()] = value
    return fields


def detect_template(fields: dict[str, str]) -> str | None:
    if all(h in fields for h in INBOUND_HEADINGS):
        return "inbound"
    if all(h in fields for h in WORK_READY_HEADINGS):
        return "work-ready"
    return None


def _chosen(raw: str, prefix: str, allowed: frozenset[str]) -> str | None:
    if raw in allowed and raw.startswith(prefix + ":"):
        return raw
    return None


def plan_labels(
    body: str,
    current: set[str],
    allowed: frozenset[str],
) -> Plan:
    fields = parse_issue_form(body)
    template = detect_template(fields)
    add: set[str] = set()
    remove: set[str] = set()
    if template == "inbound":
        mapping = INBOUND_FIELDS
    elif template == "work-ready":
        mapping = WORK_READY_FIELDS
    else:
        return Plan(frozenset(), frozenset())

    for heading, prefix in mapping.items():
        chosen = _chosen(fields.get(heading, ""), prefix, allowed)
        if chosen is None:
            continue
        ns = prefix + ":"
        if chosen not in current:
            add.add(chosen)
        for lab in current:
            if lab != chosen and lab.startswith(ns) and lab in allowed:
                remove.add(lab)

    return Plan(frozenset(add), frozenset(remove))


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


def load_event(path: Path) -> tuple[int, str, set[str]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    issue = data.get("issue")
    if not isinstance(issue, dict) or "number" not in issue:
        raise SystemExit("event has no issue")
    return (
        int(issue["number"]),
        issue.get("body") or "",
        label_names(issue.get("labels")),
    )


def fetch_issue(repo: str, number: int) -> tuple[str, set[str]]:
    proc = gh(
        ["issue", "view", str(number), "--json", "body,labels"],
        repo=repo,
    )
    data = json.loads(proc.stdout)
    return data.get("body") or "", label_names(data.get("labels"))


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


def self_test() -> None:
    allowed = taxonomy_names(default_labels_yml())
    assert "source:github" in allowed and "signal:bug" in allowed
    assert "bug" not in allowed and "enhancement" not in allowed

    inbound = (
        "### Source\n\nsource:github\n\n"
        "### Signal kind\n\nsignal:bug\n\n"
        "### Signal\n\nA crash in login.\n\n"
        "### Fit check\n\nIn scope.\n\n"
        "### Proposed verdict\n\nverdict:hold\n\n"
        "### Gate\n\n- [x] Not handing to Lokay. No `work:ready` until complete.\n"
    )
    hold = plan_labels(inbound, {"bifrost:in", "verdict:hold"}, allowed)
    assert hold.add == frozenset({"source:github", "signal:bug"})
    assert hold.remove == frozenset()
    assert "work:ready" not in hold.add

    pass_body = inbound.replace("verdict:hold", "verdict:pass", 1)
    passed = plan_labels(pass_body, {"bifrost:in", "verdict:hold"}, allowed)
    assert passed.add == frozenset({"source:github", "signal:bug", "verdict:pass"})
    assert passed.remove == frozenset({"verdict:hold"})

    already = plan_labels(
        inbound, {"bifrost:in", "verdict:hold", "source:github", "signal:bug"}, allowed
    )
    assert already.add == frozenset() and already.remove == frozenset()

    swapped = plan_labels(
        inbound.replace("source:github", "source:x"),
        {"bifrost:in", "verdict:hold", "source:github", "signal:bug"},
        allowed,
    )
    assert swapped.add == frozenset({"source:x"})
    assert swapped.remove == frozenset({"source:github"})

    bogus = plan_labels(
        inbound.replace("source:github", "source:email").replace("signal:bug", "bug"),
        {"bifrost:in", "verdict:hold"},
        allowed,
    )
    assert bogus.add == frozenset() and bogus.remove == frozenset()

    work = (
        "### Problem\n\nMissing auto-label.\n\n"
        "### Scope\n\nThis repo.\n\n"
        "### Repo\n\nmikolaj92/heimdall\n\n"
        "### Acceptance\n\nLabels applied.\n\n"
        "### Constraints\n\nNone\n\n"
        "### Artifact / QA\n\nPR.\n\n"
        "### Priority\n\npri:p0\n\n"
        "### Craft\n\n- [x] Complete per ISSUE_CRAFT.md.\n"
    )
    p0 = plan_labels(work, {"work:ready", "pri:p2", "bifrost:in"}, allowed)
    assert p0.add == frozenset({"pri:p0"})
    assert p0.remove == frozenset({"pri:p2"})
    assert "work:ready" not in p0.remove

    p2 = plan_labels(
        work.replace("pri:p0", "pri:p2"),
        {"work:ready", "pri:p2", "bifrost:in"},
        allowed,
    )
    assert p2.add == frozenset() and p2.remove == frozenset()

    noise = plan_labels("Just a comment.\n\n### Notes\n\nhello\n", {"bug"}, allowed)
    assert noise.add == frozenset() and noise.remove == frozenset()

    print("ok: self-test")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", help="OWNER/NAME (default: current gh repo)")
    parser.add_argument("--issue", type=int, help="issue number (else GITHUB_EVENT_PATH)")
    parser.add_argument("--body-file", type=Path, help="issue body for dry-run / local")
    parser.add_argument(
        "--current-labels",
        default="",
        help="comma-separated current labels (with --body-file)",
    )
    parser.add_argument("--event", type=Path, help="GitHub event JSON (default: GITHUB_EVENT_PATH)")
    parser.add_argument("--dry-run", action="store_true", help="print actions only")
    parser.add_argument("--self-test", action="store_true", help="run parser fixtures")
    args = parser.parse_args(argv)

    if args.self_test:
        self_test()
        return 0

    allowed = taxonomy_names(default_labels_yml())
    repo = args.repo or detect_repo()

    if args.body_file is not None:
        number = args.issue or 0
        body = args.body_file.read_text(encoding="utf-8")
        current = {part.strip() for part in args.current_labels.split(",") if part.strip()}
    elif args.issue is not None:
        number = args.issue
        body, current = fetch_issue(repo, number)
    else:
        event_path = args.event or Path(os.environ.get("GITHUB_EVENT_PATH") or "")
        if not event_path or not event_path.is_file():
            raise SystemExit("need --issue, --body-file, or GITHUB_EVENT_PATH")
        number, body, current = load_event(event_path)

    plan = plan_labels(body, current, allowed)
    if args.body_file is not None and args.issue is None:
        print(f"add {sorted(plan.add) or '-'}")
        print(f"remove {sorted(plan.remove) or '-'}")
        return 0
    apply_plan(repo, number, plan, dry_run=args.dry_run)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except subprocess.CalledProcessError as exc:
        sys.stderr.write(exc.stderr or str(exc))
        raise SystemExit(exc.returncode)
