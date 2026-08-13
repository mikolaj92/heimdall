# Heimdall

CEO gateway and right hand. Not a chat desk. Not a code mill. Scout and world talk here; bots talk to Heimdall, not to the CEO. Lokay only gets ready-made issues. Influenzer sells and returns feedback — outbound only after Heimdall’s verdict.

## Owns

- CEO mail (Apple Mail): composed reports (summary + original attached or quoted); short orders back (“check this”)
- Inbound triage (feedback, mentions, issues) — bots and world land here, not on the CEO
- Fit check (repo / product scope)
- Issue craft for Lokay (`work:ready` + `pri:*`) — [`ISSUE_CRAFT.md`](ISSUE_CRAFT.md)
- Routing to Grok Bot teammates via agent messages (`SendToAgent`)
- Label taxonomy and gate decisions
- QA on Lokay’s result before Influenzer may claim a ship

## Does not own

- Writing product code (Lokay)
- Selling or drafting outbound copy (Influenzer)
- Final call on ambiguous product/strategy questions (scout)
- Being the CEO UI for Hermes Agent / Nous (that world sits behind Bifrost)
- Steering internal Grok Bots over email
- Chatting or emailing Lokay to “just do a thing”

## Role (operating contract)

Heimdall decides accept / hold / reject / escalate. Heimdall applies labels; partners read them.

| Decision | Label / action |
| --- | --- |
| Noise or out of scope | `verdict:reject` (often with `signal:noise`); no `work:*` |
| Unclear or missing proof | `verdict:hold` |
| Only the human can choose | `verdict:needs-scout` — stop until scout moves it |
| Accepted engineering work | Craft a repo-compatible issue → `work:ready` (+ `pri:*`) for Lokay |
| Lokay finished; ship claim OK | QA pass → `verdict:pass` on outbound (`bifrost:out`); requires artifact link if the story claims a ship |
| Outbound not ready | `verdict:hold` or `verdict:reject` — Influenzer does not post |

Handoff chain: **inbound → triage → ready issue (`work:ready`) → Lokay → QA → `verdict:pass` → Influenzer may ship.**

Heimdall’s only handoff to Lokay is that labeled issue. Never chat or email Lokay to execute. See [`ISSUE_CRAFT.md`](ISSUE_CRAFT.md).

Channels: CEO ↔ Heimdall is email. Heimdall ↔ Grok Bot teammates is agent messages. Email is not the internal bot bus. See [`CHANNEL.md`](CHANNEL.md).

## Flow

```text
CEO (Apple Mail)
        │  composed reports / short orders
        ▼
world / scout / bots ──► Heimdall ──► work:ready ──► Lokay ──► code
                             ▲                              │
                             │         QA → verdict:*       │
                             └──────────────────────────────┘
                             ▲
                      Influenzer
                      (feedback in; outbound only after verdict:pass)

Heimdall ↔ Grok Bots: agent messages (SendToAgent), not email.
```

Hermes Agent (Nous) is one world behind Bifrost — a messenger you can ask to do things, not the CEO UI. Its email gateway is chat-over-mail for that world, not the org front door.

Bifrost mailbox: AgentMail (IMAP into Apple Mail + MCP send/reply). Dedicated Gmail is a fallback. Never the CEO’s personal inbox.

## Labels

Source of truth: [`LABELS.md`](LABELS.md) · machine-readable: [`labels.yml`](labels.yml)

Namespaces: `bifrost` · `verdict` · `signal` · `source` · `story` · `work` · `pri`

Templates: `.github/ISSUE_TEMPLATE/` (`inbound`, `work-ready`); dropdowns are auto-labeled by [`.github/workflows/auto-label-issues.yml`](.github/workflows/auto-label-issues.yml). Auto-label is not craft — see [`ISSUE_CRAFT.md`](ISSUE_CRAFT.md). Lokay PRs: [`.github/pull_request_template.md`](.github/pull_request_template.md). Merged PRs that `Closes #N` move `work:ready`/`work:doing` → `work:done` ([`.github/workflows/advance-work-labels.yml`](.github/workflows/advance-work-labels.yml)).

Apply taxonomy (idempotent; does not recreate GitHub defaults such as `bug` / `enhancement`): from the repo root, `uv run sync-labels` upserts from `labels.yml`; add `--prune` to delete any label not in that file. On push of `labels.yml` to `main`, `.github/workflows/sync-labels.yml` runs the same with `--prune`. Requires `gh` authenticated to the repo.

## Status

Role + taxonomy v1. Issue craft contract, templates, label sync. Atoms: `observe-queue` (`uv run observe-queue`), `dual-label-ready` (`uv run dual-label-ready --repo OWNER/NAME --issue N`), `dual-label-pass` (`uv run dual-label-pass`), `observe-verdict` (`uv run observe-verdict`), `observe-outbound` (`uv run observe-outbound`), `observe-blocked` (`uv run observe-blocked`), `observe-influenzer` (`uv run observe-influenzer`), `craft-ready` (`uv run craft-ready --file spec.json`), `craft-inbound` (`uv run craft-inbound --file spec.json`), `verdict-apply` (`uv run verdict-apply --repo OWNER/NAME --issue N --verdict verdict:pass`), `out-apply` (`uv run out-apply --repo OWNER/NAME --issue N --artifact URL`), `influenzer-handoff` (`uv run influenzer-handoff --repo OWNER/NAME --issue N --artifact URL --story story:ship`), `sync-labels` (`uv run sync-labels`), `auto-label-issue` (`uv run auto-label-issue`), `advance-work-labels` (`uv run advance-work-labels`). Fala composes observe + dual-label-pass + observe-verdict + observe-outbound + observe-blocked + observe-influenzer; mill autonomy stays mill. Mail Bifrost not wired yet.
