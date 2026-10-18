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

Taxonomy: [`LABELS.md`](LABELS.md) · managed labels: [`labels.yml`](labels.yml), not a guarantee of GitHub’s current state.

Namespaces: `bifrost` · `verdict` · `signal` · `source` · `story` · `work` · `pri`

Templates: `.github/ISSUE_TEMPLATE/` (`inbound`, `work-ready`); dropdowns are auto-labeled by [`.github/workflows/auto-label-issues.yml`](.github/workflows/auto-label-issues.yml). Auto-label is not craft — see [`ISSUE_CRAFT.md`](ISSUE_CRAFT.md). Lokay PRs: [`.github/pull_request_template.md`](.github/pull_request_template.md). Merged PRs that `Closes #N` move `work:ready`/`work:doing` → `work:done` ([`.github/workflows/advance-work-labels.yml`](.github/workflows/advance-work-labels.yml)).

From the repo root, `uv run sync-labels` creates or updates managed labels; `--prune` also deletes other labels during that run. Requires authenticated `gh`. `.github/workflows/sync-labels.yml` runs with `--prune` on `workflow_dispatch` or pushes to `main` changing `labels.yml`, `src/heimdall/sync_labels.py`, or the workflow itself. There is no continuous reconciliation.

## Monitor

[`fala-package.toml`](fala-package.toml) declares `correlation_paths.id = "monitor"`. That file is the order. Fala (`mikolaj92/Fala`) does not tick it from this repo: no LaunchAgent, no mill hook, no host command. Dual-label on the mill catalog closes only when you run it.

From the repo root, run each effector by hand with the `uv run …` command in that TOML (`uv run observe-queue`, `uv run dual-label-pass`, …). Do not use bare `python3`.

Self-check after one atom: JSON on stdout. `FALA_EFFECTOR_OUTPUT_DIR` is written only if a Fala host sets it (this repo does not). Mill autonomy stays mill.

## Status

Role + taxonomy v1: issue craft, templates, label sync, and atoms described in [`CHANNEL.md`](CHANNEL.md). GitHub lists request at most 100 open issues or PRs per repo. Reaching that limit before label filtering returns `ok: false`: completeness cannot be confirmed, even at exactly 100. `dual-label-pass` skips mutations in that repo. Tests run on GitHub (push/PR) via [`.github/workflows/test.yml`](.github/workflows/test.yml) and locally with `uv run pytest` or Lokay (`[tool.lokay] test`). Mail Bifrost is not wired yet.
