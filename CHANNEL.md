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

Two Lokay surfaces. Do not conflate. Grok Bot teammate: `work:ready` (including heimdall). Unix mill: mill-catalog repos + `ai:ready`. Dual-label is one craft rule in [`ISSUE_CRAFT.md`](ISSUE_CRAFT.md), not a coordination brain. Do not add heimdall to the mill catalog. Do not add `ai:*` to [`labels.yml`](labels.yml).

`observe-queue` (`uv run observe-queue`) prints a JSON envelope of that bus. Heimdall: open `work:ready` / `work:doing` / `work:blocked` and open PRs. Mill catalog (lokay `repos.mikolaj92.yaml` via `gh api`, never heimdall): open `ai:ready` / `ai:in-progress` / `work:ready` / `work:doing`, plus mill-looking open PRs (`ai:pr-opened` or similar). Read-only. Does not apply labels, wake the mill, or steer.

`dual-label-ready` (`uv run dual-label-ready --repo OWNER/NAME --issue N`) applies mill `ai:ready` on a catalog issue that already has `work:ready`. No-op on heimdall. Does not wake the mill.

`craft-ready` (`uv run craft-ready --file spec.json`) creates a complete `work:ready` issue; it is not on the Fala monitor path.

`ready-apply` (`uv run ready-apply --repo OWNER/NAME --issue N`) promotes an existing issue that already satisfies ISSUE_CRAFT to `work:ready` (catalog also `ai:ready`). Fail closed on stubs, missing fields, blocking verdicts, or anything other than exactly one taxonomy-owned `bifrost:in` / `bifrost:out` direction. `bifrost:in` is not automatically `work:ready`. Does not create a second issue or wake the mill. Not on the Fala monitor path.

`craft-inbound` (`uv run craft-inbound --file spec.json`) files a `bifrost:in` triage issue (inbound template; never `work:ready`); it is not on the Fala monitor path.

`verdict-apply` (`uv run verdict-apply --repo OWNER/NAME --issue N --verdict verdict:pass`) applies one `verdict:*` from [`labels.yml`](labels.yml) (also `--pr N`; optional `--comment`); not on the Fala monitor path.

`out-apply` (`uv run out-apply --repo OWNER/NAME --issue N --artifact URL`) marks outbound that may ship (`bifrost:out` + `verdict:pass`; fail closed without an http(s) artifact URL; also `--pr N`; optional `--comment`); not on the Fala monitor path.

`influenzer-handoff` (`uv run influenzer-handoff --repo OWNER/NAME --issue N --artifact URL --story story:ship`) files a `bifrost:in` triage issue on Influenzer after source `bifrost:out` + `verdict:pass` (reuse craft-inbound; never `work:ready`; also `--pr N`; optional `--comment` / `--to-repo`); not on the Fala monitor path.

`observe-verdict` (`uv run observe-verdict`) prints a JSON envelope of open PRs Heimdall should look at for QA/verdict: all open PRs on heimdall, plus mill-looking open PRs on catalog repos (`ai:` labels or `ai/` heads). Read-only. Does not merge, comment, label, or wake the mill.

`observe-outbound` (`uv run observe-outbound`) prints a JSON envelope of open GitHub items that claim outbound (`bifrost:out`) but must not ship yet (missing `verdict:pass`), surveying heimdall issues+PRs and the mill catalog (never heimdall twice); read-only — does not merge, comment, label, wake the mill, or call Influenzer.

`observe-blocked` (`uv run observe-blocked`) prints a JSON envelope of open issues that are stuck (`work:blocked` on heimdall; `work:blocked` or mill `ai:blocked` on catalog repos, never heimdall twice); read-only — does not merge, comment, label, wake the mill, or mail.

`observe-influenzer` (`uv run observe-influenzer`) prints a JSON envelope of open items on Influenzer's GitHub (default `mikolaj92/influenzer`): inbound (`bifrost:in`), outbound that must not ship (`bifrost:out` missing `verdict:pass`), `work:blocked`, `verdict:hold`, and all open PRs. One repo only; does not fetch the mill catalog. Read-only — does not merge, comment, label, wake Influenzer tick, SSH, mail, or mill.

`observe-inbound` (`uv run observe-inbound`) prints a JSON envelope of open Heimdall issues in the inbound triage queue (`bifrost:in` that is not yet `work:ready` and not `bifrost:out`). Default `mikolaj92/heimdall`; `--heimdall OWNER/NAME`. One repo only; does not fetch the mill catalog. `bifrost:in` is not `work:ready`. Read-only — does not apply `work:ready`, wake the mill, SSH, or mail.

`observe-cleared` (`uv run observe-cleared`) prints a JSON envelope of open GitHub items that may ship (`bifrost:out` and `verdict:pass`), surveying heimdall issues+PRs and the mill catalog (never heimdall twice). Pair of `observe-outbound` (must not ship). Read-only — does not merge, comment, label, wake the mill, or call Influenzer. `influenzer-handoff` / `out-apply` stay mutators.

[`fala-package.toml`](fala-package.toml) declares `correlation_paths.id = "monitor"` (observe-queue → dual-label-pass → observe-verdict → observe-outbound → observe-blocked → observe-influenzer → observe-inbound → observe-cleared). That file is the order. Fala does not tick it from this repo: no LaunchAgent, no mill hook, no host command. From the repo root, run each effector by hand (`uv run observe-queue`, `uv run dual-label-pass`, …). Dual-label on the mill catalog closes only then. Self-check: JSON on stdout; `FALA_EFFECTOR_OUTPUT_DIR` only if a Fala host sets it (this repo does not). Parent monitors; it does not wake, SSH, or steer the mill. Mill autonomy stays mill.

Email is not the internal bot bus.

## Do not

- Use email as the bot bus
- Email-steer internal Grok Bots
- Chat or email Lokay to “just do a thing”
- Dump raw bot chat to the CEO
- Use the CEO’s personal inbox as Bifrost
- Treat Hermes Agent email as the org front door
