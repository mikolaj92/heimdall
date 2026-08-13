"""Apply labels.yml onto a GitHub repo (idempotent).

Creates or updates only names from labels.yml. Never creates GitHub's
default labels (bug, enhancement, documentation, duplicate, good first
issue, help wanted, invalid, question, wontfix).

From the repo root, with gh authenticated to the target repo:

  uv run sync-labels            # upsert taxonomy
  uv run sync-labels --prune    # also delete labels not in labels.yml
  uv run sync-labels --dry-run  # print actions only

Repo: --repo OWNER/NAME, else GH_REPO / GITHUB_REPOSITORY, else `gh repo view`.
On push of labels.yml to main, .github/workflows/sync-labels.yml runs --prune.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

DEFAULT_GITHUB_LABELS = frozenset(
    {
        "bug",
        "documentation",
        "duplicate",
        "enhancement",
        "good first issue",
        "help wanted",
        "invalid",
        "question",
        "wontfix",
    }
)


def default_labels_yml() -> Path:
    here = Path.cwd() / "labels.yml"
    if here.is_file():
        return here
    return Path(__file__).resolve().parents[2] / "labels.yml"


def parse_value(raw: str) -> str:
    raw = raw.strip()
    if len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in {'"', "'"}:
        return raw[1:-1]
    return raw


def parse_labels_yml(path: Path) -> list[dict[str, str]]:
    """Parse Heimdall labels.yml. Namespace color is default; label color overrides."""
    ns_color = ""
    current: dict[str, str] | None = None
    out: list[dict[str, str]] = []

    def flush() -> None:
        nonlocal current
        if not current or not current.get("name"):
            current = None
            return
        color = (current.get("color") or ns_color).removeprefix("#")
        if not color:
            raise SystemExit(f"missing color for label {current['name']}")
        out.append(
            {
                "name": current["name"],
                "description": current.get("description", ""),
                "color": color,
            }
        )
        current = None

    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        indent = len(line) - len(line.lstrip(" "))
        stripped = line.strip()
        body = stripped[2:] if stripped.startswith("- ") else stripped
        if ":" not in body:
            raise SystemExit(f"{path}:{lineno}: cannot parse {stripped!r}")
        key, _, raw_val = body.partition(":")
        key, val = key.strip(), parse_value(raw_val)

        if stripped.startswith("- name:"):
            if indent <= 2:
                flush()
                ns_color = ""
            else:
                flush()
                current = {"name": val}
            continue
        if key == "color":
            if current is not None:
                current["color"] = val
            else:
                ns_color = val
        elif key == "description" and current is not None:
            current["description"] = val

    flush()
    if not out:
        raise SystemExit(f"no labels parsed from {path}")
    return out


def taxonomy_names(path: Path) -> frozenset[str]:
    """Label names from labels.yml (`ns:name` only; skip namespace titles)."""
    return frozenset(lab["name"] for lab in parse_labels_yml(path))


def gh(args: list[str], *, repo: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["gh", *args, "-R", repo],
        check=True,
        text=True,
        capture_output=True,
    )


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


def list_label_names(repo: str) -> set[str]:
    proc = gh(["label", "list", "--json", "name", "--limit", "1000"], repo=repo)
    return {item["name"] for item in json.loads(proc.stdout)}


def refuse_github_defaults(wanted: list[dict[str, str]]) -> None:
    for lab in wanted:
        if lab["name"].lower() in DEFAULT_GITHUB_LABELS:
            raise SystemExit(
                f"refusing to create deleted GitHub default label: {lab['name']}"
            )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", help="OWNER/NAME (default: current gh repo)")
    parser.add_argument(
        "--prune",
        action="store_true",
        help="delete labels that are not in labels.yml (including GitHub defaults)",
    )
    parser.add_argument("--dry-run", action="store_true", help="print actions only")
    args = parser.parse_args(argv)

    wanted = parse_labels_yml(default_labels_yml())
    refuse_github_defaults(wanted)

    repo = args.repo or detect_repo()
    wanted_names = {lab["name"] for lab in wanted}

    for lab in wanted:
        cmd = (
            f"gh label create {lab['name']!r} --description {lab['description']!r} "
            f"--color {lab['color']} --force -R {repo}"
        )
        print(f"upsert {lab['name']}")
        if args.dry_run:
            print(f"  {cmd}")
            continue
        gh(
            [
                "label",
                "create",
                lab["name"],
                "--description",
                lab["description"],
                "--color",
                lab["color"],
                "--force",
            ],
            repo=repo,
        )

    pruned = 0
    if args.prune:
        existing = list_label_names(repo)
        extra = sorted(existing - wanted_names)
        for name in extra:
            print(f"delete {name}")
            pruned += 1
            if args.dry_run:
                continue
            gh(["label", "delete", name, "--yes"], repo=repo)

    print(
        f"{'dry-run ' if args.dry_run else ''}ok: {len(wanted)} taxonomy labels "
        f"on {repo}; pruned {pruned}"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except subprocess.CalledProcessError as exc:
        sys.stderr.write(exc.stderr or str(exc))
        raise SystemExit(exc.returncode)
