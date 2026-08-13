# Channels

Two planes. Do not mix them.

## A. CEO mail plane

CEO ↔ Heimdall only. Apple Mail.

Heimdall writes composed reports: a short summary plus the original attached or quoted. The CEO replies with short orders (“check this”).

Bifrost mailbox: AgentMail (IMAP into Apple Mail + MCP send/reply). Dedicated Gmail is a fallback. Never the CEO’s personal inbox.

Hermes Agent (Nous) email is chat-over-mail for that world, behind Bifrost. It is not the org front door and not the CEO UI.

## B. Internal routing plane

Bots talk to Heimdall, not to the CEO. Heimdall triages and routes.

| Partner | How |
| --- | --- |
| Grok Bot teammates | Agent messages (`SendToAgent`). Do not email-steer them. |
| Lokay | A repo-compatible GitHub issue labeled `work:ready` (+ `pri:*`). Lokay is hands-off: it only executes code from ready issues. Craft contract: [`ISSUE_CRAFT.md`](ISSUE_CRAFT.md). |
| Influenzer | Feedback in to Heimdall. Outbound only after `verdict:pass`. |
| Labels | [`LABELS.md`](LABELS.md) / [`labels.yml`](labels.yml) — namespaces `bifrost`, `verdict`, `signal`, `source`, `story`, `work`, `pri`. Do not invent names. |

Email is not the internal bot bus.

## Do not

- Use email as the bot bus
- Email-steer internal Grok Bots
- Chat or email Lokay to “just do a thing”
- Dump raw bot chat to the CEO
- Use the CEO’s personal inbox as Bifrost
- Treat Hermes Agent email as the org front door
