# Issue craft contract

Heimdall crafts issues. There is no chat or email path to Lokay.

Two Lokay surfaces. Do not conflate. See [`CHANNEL.md`](CHANNEL.md) and [`MILL.md`](MILL.md).

| Surface | Execute signal | Sees heimdall? |
| --- | --- | --- |
| Grok Bot teammate “Lokay” | `work:ready` (+ `pri:*`) | Yes. [Heimdall #4](https://github.com/mikolaj92/heimdall/issues/4) ran here. |
| Unix mill (mini-m4-0) | `ai:ready` on a **catalog** repo (`repos.mikolaj92.yaml` in mikolaj92/lokay) | No. heimdall is not in the catalog. Do not add it from here. |

Incomplete work stays `verdict:hold`. Do not apply `work:ready` (or mill `ai:ready`) until every required field below is filled. See [`LABELS.md`](LABELS.md).

## Required body

A Lokay-ready issue MUST contain all of the following. If any item is missing or vague, keep `verdict:hold` and do not label `work:ready` or `ai:ready`.

| Field | What to write |
| --- | --- |
| **Problem** | What is wrong or missing, in one concrete claim. Not a vibe. |
| **Scope** | In scope vs out of scope. What Lokay must not do. |
| **Repo** | Target `owner/name` (and branch if not default). File the issue on that repo when possible. Check whether it is in the mill catalog before labeling. |
| **Acceptance** | Observable checks that mean done. Lokay should not need a follow-up question. |
| **Constraints** | Time, deps, files to touch or avoid, compatibility. Write `None` if there are none. |
| **Artifact / QA** | What Heimdall will inspect after Lokay (PR, logs, screenshot, command). If a later ship will be claimed, say what artifact link is required. |

## Required labels

Heimdall applies labels. Do not invent Heimdall names — [`labels.yml`](labels.yml) only.

| Label | When |
| --- | --- |
| `work:ready` | All required fields are filled. Execute signal for the Grok Bot teammate (and Heimdall’s own `work:*` queue). |
| `pri:*` | Always, with `work:ready`. Default inbound that passed the gate: `pri:p2`. |
| `bifrost:in` or `bifrost:out` | Anything Heimdall touches. Engineering handoff is almost always `bifrost:in`. |
| `verdict:*` | As needed. Accepted work may be `verdict:pass`. Unclear work is `verdict:hold`, never `work:ready`. |
| `ai:ready` | **Additionally**, when the target is a mill **catalog** repo. The mill surveys this, not `work:ready`. Mill-owned — do not add `ai:*` to [`labels.yml`](labels.yml). Mapping lives in this file. |

One primary `work:*` and one `pri:*`. Do not combine `work:ready` with `verdict:hold`, `verdict:reject`, or `verdict:needs-scout`.

`signal:noise` ⇒ `verdict:reject`, no `work:*`, no `ai:ready`.

Catalog check: [mikolaj92/lokay `repos.mikolaj92.yaml`](https://github.com/mikolaj92/lokay/blob/main/repos.mikolaj92.yaml). If the repo is listed there, apply `work:*` **and** `ai:ready` so the mill can see it. If it is not (heimdall, or anything else missing from that file), apply Heimdall `work:*` only.

## Incomplete

Use `verdict:hold` (and the inbound template) when proof, fit, or any required field is missing. Ping scout with `verdict:needs-scout` when only the human can choose. Reject with `verdict:reject` when out of scope.

Do not start either Lokay informally while the issue sits on hold.

## After Lokay

Grok Bot teammate / heimdall workflows move `work:ready` → `work:doing` → `work:done` (or `work:blocked`). A merged PR that `Closes #N` auto-applies `work:done` when that issue is `work:ready` or `work:doing`; opening such a PR moves `work:ready` → `work:doing` ([`.github/workflows/advance-work-labels.yml`](.github/workflows/advance-work-labels.yml)).

The Unix mill moves its own ledger (`ai:ready` → `ai:in-progress` / PR labels) on catalog repos. Heimdall still QAs the result against the acceptance and artifact notes before Influenzer may claim a ship (`verdict:pass` on `bifrost:out` requires a real artifact link).

## Templates

- Signal triage: [`.github/ISSUE_TEMPLATE/inbound.yml`](.github/ISSUE_TEMPLATE/inbound.yml)
- Lokay handoff: [`.github/ISSUE_TEMPLATE/work-ready.yml`](.github/ISSUE_TEMPLATE/work-ready.yml)

Dropdown values on those forms are auto-applied as taxonomy labels by [`.github/workflows/auto-label-issues.yml`](.github/workflows/auto-label-issues.yml) (`scripts/auto-label-issue.py`) on issue opened or edited. Humans do not need a second click for `source:*` / `signal:*` / chosen `pri:*`, or to replace `verdict:hold` when the inbound dropdown is not hold.

Auto-label is not craft. `work:ready` still requires every required field above. Inbound stays `verdict:hold` until Heimdall decides; inbound auto-label never applies `work:ready` or `ai:ready`. Catalog `ai:ready` is applied by Heimdall at craft time, not by auto-label.

## Do not

- Chat or email Lokay to execute
- Label `work:ready` or `ai:ready` on a stub, “TBD”, or “Lokay will figure it out”
- Invent Heimdall labels outside [`LABELS.md`](LABELS.md)
- Add mill `ai:*` to [`labels.yml`](labels.yml)
- Use email as the bot bus ([`CHANNEL.md`](CHANNEL.md))
- Open synthetic or probe issues to test auto-label, the gate, or the mill
- Expect the mill to pick up heimdall `work:ready`
