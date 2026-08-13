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

Heimdall applies labels. Lokay reads `work:*`. Do not invent Heimdall names — [`labels.yml`](labels.yml) only.

| Label | When |
| --- | --- |
| `work:ready` | All required fields are filled. This is the only Heimdall execute signal. |
| `pri:*` | Always, with `work:ready`. Default inbound that passed the gate: `pri:p2`. |
| `bifrost:in` or `bifrost:out` | Anything Heimdall touches. Engineering handoff is almost always `bifrost:in`. |
| `verdict:*` | As needed. Accepted work may be `verdict:pass`. Unclear work is `verdict:hold`, never `work:ready`. |

One primary `work:*` and one `pri:*`. Do not combine `work:ready` with `verdict:hold`, `verdict:reject`, or `verdict:needs-scout`.

`signal:noise` ⇒ `verdict:reject`, no `work:*`.

### Mill catalog (one rule)

On a mill-catalog repo ([mikolaj92/lokay `repos.mikolaj92.yaml`](https://github.com/mikolaj92/lokay/blob/main/repos.mikolaj92.yaml)), also apply `ai:ready`. The mill surveys that label, not `work:ready`. Dual-label is this rule, not a coordination brain. `uv run dual-label-ready --repo OWNER/NAME --issue N` applies that mill label when `work:ready` is already present (no-op on heimdall; idempotent if `ai:ready` is already there). `uv run craft-ready --file spec.json` (stdin if `--file` omitted) files a complete `work:ready` issue from JSON (fail closed on missing fields; catalog also `ai:ready`; heimdall `work:ready` only).

Do not add heimdall to that catalog. Do not add `ai:*` to [`labels.yml`](labels.yml) — mill-owned; mapping lives here. heimdall itself: `work:ready` only.

## Incomplete

Use `verdict:hold` (and the inbound template) when proof, fit, or any required field is missing. Ping scout with `verdict:needs-scout` when only the human can choose. Reject with `verdict:reject` when out of scope.

Do not start Lokay informally while the issue sits on hold.

## After Lokay

Lokay moves `work:ready` → `work:doing` → `work:done` (or `work:blocked`). A merged PR that `Closes #N` auto-applies `work:done` when that issue is `work:ready` or `work:doing`; opening such a PR moves `work:ready` → `work:doing` ([`.github/workflows/advance-work-labels.yml`](.github/workflows/advance-work-labels.yml)). Heimdall QAs the result against the acceptance and artifact notes before Influenzer may claim a ship (`verdict:pass` on `bifrost:out` requires a real artifact link). `uv run verdict-apply --repo OWNER/NAME --issue N --verdict verdict:pass` applies one `verdict:*` from [`labels.yml`](labels.yml) (also `--pr`; optional `--comment`). `uv run out-apply --repo OWNER/NAME --issue N --artifact URL` applies `bifrost:out` and `verdict:pass` together (fail closed without an http(s) artifact URL; also `--pr`; optional `--comment`). `uv run influenzer-handoff --repo OWNER/NAME --issue N --artifact URL --story story:ship` files a `bifrost:in` Influenzer triage issue from a source that already has `bifrost:out` + `verdict:pass` (reuse craft-inbound; never `work:ready`; also `--pr`; optional `--comment` / `--to-repo`). After that inbound exists, `uv run cleared-close --repo OWNER/NAME --issue N --handoff M` closes the cleared source (does not call Influenzer).

## Templates

- Signal triage: [`.github/ISSUE_TEMPLATE/inbound.yml`](.github/ISSUE_TEMPLATE/inbound.yml). `uv run craft-inbound --file spec.json` (stdin if `--file` omitted) files that inbound form (`bifrost:in`, never `work:ready`).
- Lokay handoff: [`.github/ISSUE_TEMPLATE/work-ready.yml`](.github/ISSUE_TEMPLATE/work-ready.yml)

Dropdown values on those forms are auto-applied as taxonomy labels by [`.github/workflows/auto-label-issues.yml`](.github/workflows/auto-label-issues.yml) (`uv run auto-label-issue`) on issue opened or edited. Humans do not need a second click for `source:*` / `signal:*` / chosen `pri:*`, or to replace `verdict:hold` when the inbound dropdown is not hold.

Auto-label is not craft. `work:ready` still requires every required field above. Inbound stays `verdict:hold` until Heimdall decides; inbound auto-label never applies `work:ready`. Promoting an existing complete issue is `uv run ready-apply --repo OWNER/NAME --issue N`, not auto-label. `uv run observe-inbound` lists open `bifrost:in` that is not yet `work:ready` and not outbound. Catalog `ai:ready` is applied by Heimdall at craft time, not by auto-label.

## Do not

- Chat or email Lokay to execute
- Label `work:ready` on a stub, “TBD”, or “Lokay will figure it out”
- Invent labels outside [`LABELS.md`](LABELS.md) (mill `ai:ready` on catalog repos is the exception above)
- Use email as the bot bus ([`CHANNEL.md`](CHANNEL.md))
- Open synthetic or probe issues to test auto-label, the gate, or the mill
