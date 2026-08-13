# Channels

Two planes. Do not mix them.

## A. CEO mail plane

CEO ↔ Heimdall only. Apple Mail.

Heimdall writes composed reports: a short summary plus the original attached or quoted. The CEO replies with short orders (“check this”).

Bifrost mailbox: AgentMail (IMAP into Apple Mail + MCP send/reply). Dedicated Gmail is a fallback. Never the CEO’s personal inbox.

Hermes Agent (Nous) email is chat-over-mail for that world, behind Bifrost. It is not the org front door and not the CEO UI.

## B. Internal routing plane

Bots talk to Heimdall, not to the CEO. Heimdall triages and routes.

Two Lokay surfaces. Do not conflate. Host and health: [`MILL.md`](MILL.md).

| Partner | How |
| --- | --- |
| Grok Bot teammates | Agent messages (`SendToAgent`). Do not email-steer them. |
| Lokay (Grok Bot teammate) | A repo-compatible GitHub issue labeled `work:ready` (+ `pri:*`), including on heimdall. [Heimdall #4](https://github.com/mikolaj92/heimdall/issues/4) ran here, not on the mill. Hands-off: execute from the issue only. Craft: [`ISSUE_CRAFT.md`](ISSUE_CRAFT.md). |
| Lokay (Unix mill) | Catalog repos in mikolaj92/lokay `repos.mikolaj92.yaml` + `ai:ready`. Host mini-m4-0. Does not see `work:ready`. heimdall is not in that catalog. [`MILL.md`](MILL.md). |
| Influenzer | Feedback in to Heimdall. Outbound only after `verdict:pass`. Tick also on mini-m4-0 — dry-run default; leaves the mill LaunchAgent alone. |
| Labels | [`LABELS.md`](LABELS.md) / [`labels.yml`](labels.yml) — namespaces `bifrost`, `verdict`, `signal`, `source`, `story`, `work`, `pri`. Do not invent Heimdall names. Mill `ai:*` is mill-owned; catalog mapping is in [`ISSUE_CRAFT.md`](ISSUE_CRAFT.md), not `labels.yml`. |

Email is not the internal bot bus.

Until Heimdall can hop to mini-m4-0: observe the mill via GitHub (`ai:ready` / `ai:in-progress` / PRs on catalog repos) and Grok Bots via `SendToAgent`. GitHub cannot see `~/.lokay/last-pass.json`. Health is `lokay status` on that box.

## Do not

- Use email as the bot bus
- Email-steer internal Grok Bots
- Chat or email Lokay to “just do a thing”
- Conflate Grok Bot Lokay with the Unix mill
- Open probe issues to test the mill
- Dump raw bot chat to the CEO
- Use the CEO’s personal inbox as Bifrost
- Treat Hermes Agent email as the org front door
