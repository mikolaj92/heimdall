# Unix mill vs Grok Bot Lokay

Two Lokay surfaces. Do not conflate them.

## A. Grok Bot teammate “Lokay”

Agent messages (`SendToAgent`) plus Heimdall `work:ready` / `work:doing` / `work:done` ([`LABELS.md`](LABELS.md)). Runs on heimdall itself. [Heimdall #4](https://github.com/mikolaj92/heimdall/issues/4) was this surface, not the mill.

## B. Unix mill

[mikolaj92/lokay](https://github.com/mikolaj92/lokay) on **mini-m4-0**.

| Fact | Where |
| --- | --- |
| Catalog | `repos.mikolaj92.yaml` — scope of what the mill surveys. Missing from the file means not milled. |
| Ready label | `ai:ready` (`src/lokay/gh_issues.py` `_LABEL_META`; config `github.ready_label`) |
| Host | mini-m4-0 · LaunchAgent `ai.mikolaj.lokay-mill` · `scripts/lokay-mill-daemon.sh` |
| Logs / receipt | `~/.lokay/` · `~/.lokay/last-pass.json` |
| Health | `lokay status` on that box — not visible from GitHub |
| Event wake | `.github/workflows/lokay-wake-issue.yml` needs a self-hosted runner labeled `lokay-mill` |

**heimdall is not in the catalog.** That is on purpose. Do not add it from this repo unless we later decide otherwise.

The mill does not survey `work:ready`. A catalog issue with only Heimdall labels is invisible to it.

## Craft mapping

When Heimdall files work on a **catalog** repo: apply Heimdall `work:*` **and** mill `ai:ready`. Mapping lives in [`ISSUE_CRAFT.md`](ISSUE_CRAFT.md). Do not add `ai:*` to [`labels.yml`](labels.yml) — mill-owned.

Work on heimdall itself: `work:ready` only. The Grok Bot teammate picks it up. The mill will not.

## Observation until a hop exists

GitHub cannot see `last-pass.json`. Heimdall has no hop to mini-m4-0 yet.

Until it does:

- Mill — watch catalog GitHub: `ai:ready` / `ai:in-progress` / mill PRs (`ai/fix/*`, `ai:generated`).
- Grok Bot — `SendToAgent`.

Do not treat wake workflow cancellations or a missing `lokay-mill` runner as mill health. Health is `lokay status` on the box.

## Influenzer tick

Also belongs on mini-m4-0 ([influenzer `docs/mini-m4-0.md`](https://github.com/mikolaj92/influenzer/blob/main/docs/mini-m4-0.md)). Dry-run is default. It leaves the mill LaunchAgent alone.

Same hop problem: GitHub cannot see whether that tick is up.

## Do not

- Open probe issues to test the mill
- Add heimdall to `repos.mikolaj92.yaml` from this repo
- Add `ai:*` to Heimdall [`labels.yml`](labels.yml)
- Chat or email either Lokay to execute ([`CHANNEL.md`](CHANNEL.md))
