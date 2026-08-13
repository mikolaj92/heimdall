# Issue craft contract

Heimdall crafts issues. Lokay only executes from a GitHub issue labeled `work:ready`. There is no chat or email path to Lokay.

Incomplete work stays `verdict:hold`. Do not apply `work:ready` until every required field below is filled. See [`CHANNEL.md`](CHANNEL.md) and [`LABELS.md`](LABELS.md).

## Required body

A Lokay-ready issue MUST contain all of the following. If any item is missing or vague, keep `verdict:hold` and do not label `work:ready`.

| Field | What to write |
| --- | --- |
| **Problem** | What is wrong or missing, in one concrete claim. Not a vibe. |
| **Scope** | In scope vs out of scope. What Lokay must not do. |
| **Repo** | Target `owner/name` (and branch if not default). File the issue on that repo when possible. |
| **Acceptance** | Observable checks that mean done. Lokay should not need a follow-up question. |
| **Constraints** | Time, deps, files to touch or avoid, compatibility. Write `None` if there are none. |
| **Artifact / QA** | What Heimdall will inspect after Lokay (PR, logs, screenshot, command). If a later ship will be claimed, say what artifact link is required. |

## Required labels

Heimdall applies labels. Lokay reads `work:*`. Do not invent names — [`labels.yml`](labels.yml) only.

| Label | When |
| --- | --- |
| `work:ready` | All required fields are filled. This is the only execute signal. |
| `pri:*` | Always, with `work:ready`. Default inbound that passed the gate: `pri:p2`. |
| `bifrost:in` or `bifrost:out` | Anything Heimdall touches. Engineering handoff is almost always `bifrost:in`. |
| `verdict:*` | As needed. Accepted work may be `verdict:pass`. Unclear work is `verdict:hold`, never `work:ready`. |

One primary `work:*` and one `pri:*`. Do not combine `work:ready` with `verdict:hold`, `verdict:reject`, or `verdict:needs-scout`.

`signal:noise` ⇒ `verdict:reject`, no `work:*`.

## Incomplete

Use `verdict:hold` (and the inbound template) when proof, fit, or any required field is missing. Ping scout with `verdict:needs-scout` when only the human can choose. Reject with `verdict:reject` when out of scope.

Do not start Lokay informally while the issue sits on hold.

## After Lokay

Lokay moves `work:ready` → `work:doing` → `work:done` (or `work:blocked`). Heimdall QAs the result against the acceptance and artifact notes before Influenzer may claim a ship (`verdict:pass` on `bifrost:out` requires a real artifact link).

## Templates

- Signal triage: [`.github/ISSUE_TEMPLATE/inbound.yml`](.github/ISSUE_TEMPLATE/inbound.yml)
- Lokay handoff: [`.github/ISSUE_TEMPLATE/work-ready.yml`](.github/ISSUE_TEMPLATE/work-ready.yml)

Dropdown values on those forms are auto-applied as taxonomy labels by [`.github/workflows/auto-label-issues.yml`](.github/workflows/auto-label-issues.yml) (`scripts/auto-label-issue.py`) on issue opened or edited. Humans do not need a second click for `source:*` / `signal:*` / chosen `pri:*`, or to replace `verdict:hold` when the inbound dropdown is not hold.

Auto-label is not craft. `work:ready` still requires every required field above. Inbound stays `verdict:hold` until Heimdall decides; inbound auto-label never applies `work:ready`.

## Do not

- Chat or email Lokay to execute
- Label `work:ready` on a stub, “TBD”, or “Lokay will figure it out”
- Invent labels outside [`LABELS.md`](LABELS.md)
- Use email as the bot bus ([`CHANNEL.md`](CHANNEL.md))
- Open synthetic or probe issues to test auto-label or the gate
