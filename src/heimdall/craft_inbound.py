"""Create a GitHub issue that matches the inbound triage template.

Files bifrost:in with source:*, signal:*, and a proposed verdict:* (hold
unless specified). Never work:ready or ai:ready — talk/triage, not mill
execute. Fail closed on missing fields, unknown labels, or gh errors.
Does not wake the mill, merge, or send mail. Not on the Fala monitor path.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

from heimdall.observe_queue import HEIMDALL, GhError, GhFn, gh

ATOM = "craft-inbound"
BIFROST_IN = "bifrost:in"
DEFAULT_VERDICT = "verdict:hold"
FORBIDDEN = frozenset({"work:ready", "ai:ready"})
REQUIRED = ("title", "signal", "source", "summary", "fit")
LABEL_KEYS = ("signal", "source", "proposed_verdict", "pri", "work", "verdict")
REPO_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
ISSUE_URL_RE = re.compile(
    r"https://github\.com/[^/\s]+/[^/\s]+/issues/(\d+)",
    re.IGNORECASE,
)
LABEL_NAME_RE = re.compile(
    r"^- name:\s*[\"']?((signal|source|verdict|pri):[A-Za-z0-9_-]+)[\"']?\s*$"
)

HEADINGS = (
    ("source", "Source"),
    ("signal", "Signal kind"),
    ("summary", "Signal"),
    ("fit", "Fit check"),
    ("proposed_verdict", "Proposed verdict"),
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


def default_labels_yml() -> Path:
    here = Path.cwd() / "labels.yml"
    if here.is_file():
        return here
    return Path(__file__).resolve().parents[2] / "labels.yml"


def parse_taxonomy(text: str) -> dict[str, frozenset[str]]:
    buckets: dict[str, list[str]] = {
        "signal": [],
        "source": [],
        "verdict": [],
        "pri": [],
    }
    for line in text.splitlines():
        match = LABEL_NAME_RE.match(line.strip())
        if not match:
            continue
        name, prefix = match.group(1), match.group(2)
        buckets[prefix].append(name)
    missing = [prefix for prefix, names in buckets.items() if not names]
    if missing:
        raise ValueError(f"no {'/'.join(missing)} labels in labels.yml")
    return {prefix: frozenset(names) for prefix, names in buckets.items()}


def load_taxonomy(path: Path | None = None) -> dict[str, frozenset[str]]:
    path = path or default_labels_yml()
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ValueError(f"labels.yml: {exc}") from exc
    return parse_taxonomy(text)


def forbidden_request(spec: dict[str, Any]) -> str | None:
    for key in LABEL_KEYS:
        value = field(spec, key)
        if value in FORBIDDEN:
            return value
    raw = spec.get("labels")
    if isinstance(raw, list):
        for item in raw:
            if isinstance(item, str) and item.strip() in FORBIDDEN:
                return item.strip()
    return None


def proposed_verdict(spec: dict[str, Any]) -> str:
    if "proposed_verdict" not in spec:
        return DEFAULT_VERDICT
    return field(spec, "proposed_verdict")


def target_repo(spec: dict[str, Any]) -> str:
    if "repo" not in spec:
        return HEIMDALL
    return field(spec, "repo")


def validate(spec: dict[str, Any], taxonomy: dict[str, frozenset[str]]) -> str | None:
    missing = [key for key in REQUIRED if not field(spec, key)]
    if missing:
        return f"missing or empty: {', '.join(missing)}"
    blocked = forbidden_request(spec)
    if blocked:
        return f"refuses {blocked}"
    signal = field(spec, "signal")
    if signal not in taxonomy["signal"]:
        return f"unknown signal: {signal}"
    source = field(spec, "source")
    if source not in taxonomy["source"]:
        return f"unknown source: {source}"
    if "proposed_verdict" in spec:
        verdict = field(spec, "proposed_verdict")
        if not verdict:
            return "missing or empty: proposed_verdict"
        if verdict not in taxonomy["verdict"]:
            return f"unknown proposed_verdict: {verdict}"
    if "pri" in spec:
        pri = field(spec, "pri")
        if not pri:
            return "missing or empty: pri"
        if pri not in taxonomy["pri"]:
            return f"unknown pri: {pri}"
    if "repo" in spec:
        repo = field(spec, "repo")
        if not repo:
            return "missing or empty: repo"
        if not REPO_RE.fullmatch(repo):
            return f"invalid repo: {repo}"
    return None


def issue_body(spec: dict[str, Any]) -> str:
    values = dict(spec)
    values["proposed_verdict"] = proposed_verdict(spec)
    chunks = [
        f"### {heading}\n\n{field(values, key)}" for key, heading in HEADINGS
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


def craft_labels(spec: dict[str, Any]) -> list[str]:
    labels = [
        BIFROST_IN,
        field(spec, "source"),
        field(spec, "signal"),
        proposed_verdict(spec),
    ]
    if "pri" in spec:
        labels.append(field(spec, "pri"))
    return labels


def parse_spec(text: str) -> dict[str, Any]:
    try:
        spec = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid json: {exc}") from exc
    if not isinstance(spec, dict):
        raise ValueError("spec must be a JSON object")
    return spec


def craft_inbound(
    spec: dict[str, Any],
    *,
    run: GhFn | None = None,
    labels_yml: Path | None = None,
    taxonomy: dict[str, frozenset[str]] | None = None,
) -> dict[str, Any]:
    """File a bifrost:in triage issue. Never work:ready. Fail closed."""
    run = run or gh
    try:
        taxonomy = taxonomy or load_taxonomy(labels_yml)
    except ValueError as exc:
        return err(str(exc))

    message = validate(spec, taxonomy)
    if message:
        return err(message)

    repo = target_repo(spec)
    labels = craft_labels(spec)
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
    return craft_inbound(spec, run=run)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="craft-inbound",
        description=(
            "Create a bifrost:in triage issue from the inbound template. "
            "Never work:ready. Fail closed on missing fields. Does not wake the mill."
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
    return emit_exit(craft_from_text(text))


if __name__ == "__main__":
    raise SystemExit(main())
