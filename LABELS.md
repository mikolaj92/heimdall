# Heimdall label taxonomy

Source of truth for labels Heimdall may apply across org repos.
Namespaces are prefixes. One label per dimension unless noted.

Heimdall owns applying and changing these. Grok Bot Lokay consumes `work:*`. The Unix mill consumes `ai:ready` on catalog repos — mill-owned, not this taxonomy; mapping in [`ISSUE_CRAFT.md`](ISSUE_CRAFT.md). Influenzer consumes `story:*` and respects `verdict:*` on outbound. The scout (human) is pinged via `verdict:needs-scout`.

## bifrost:* — direction

| Label | Meaning |
| --- | --- |
| `bifrost:in` | Inbound signal (reply, mention, issue, feedback) |
| `bifrost:out` | Outbound artifact (draft post, release note, announcement) |

Exactly one required on anything Heimdall touches.

## verdict:* — gate decision (Heimdall)

| Label | Meaning |
| --- | --- |
| `verdict:pass` | May proceed (post / accept into backlog) |
| `verdict:hold` | Not yet — missing proof, unclear, wait |
| `verdict:reject` | Noise, spam, false claim, out of scope |
| `verdict:needs-scout` | Only the human scout decides |

Exactly one on gated items. `pass` on outbound requires a real artifact link (PR, release, issue, or commit) when the story claims a ship.

## signal:* — what inbound is (bifrost:in)

| Label | Meaning |
| --- | --- |
| `signal:feedback` | Product opinion / experience report |
| `signal:bug` | Something broken |
| `signal:feature` | Ask for new capability |
| `signal:question` | Needs an answer, not necessarily code |
| `signal:praise` | Positive signal worth amplifying |
| `signal:noise` | No action (spam, off-topic, empty) |

One primary. Heimdall may add `signal:noise` + `verdict:reject` together.

## source:* — where it came from (bifrost:in)

| Label |
| --- |
| `source:github` |
| `source:x` |
| `source:bluesky` |
| `source:mastodon` |
| `source:linkedin` |
| `source:other` |

One primary.

## story:* — what outbound is about (bifrost:out)

| Label | Meaning |
| --- | --- |
| `story:major` | Major version / milestone |
| `story:ship` | Concrete ship with artifact |
| `story:explore` | What we are investigating |
| `story:issue` | A hard problem we opened or hit |
| `story:decision` | Choice we made and why |
| `story:failure` | What broke / what we learned |

One primary. Prefer `story:major` / `story:ship` / `story:failure` over vibes.

## work:* — queue for Grok Bot Lokay (producer)

| Label | Meaning |
| --- | --- |
| `work:ready` | Triaged, ready to implement |
| `work:doing` | Lokay is on it |
| `work:blocked` | Stuck on decision or dependency |
| `work:done` | Shipped / closed |

One primary when the item is (or became) engineering work.

## pri:* — urgency

| Label | Meaning |
| --- | --- |
| `pri:p0` | Drop everything |
| `pri:p1` | This week |
| `pri:p2` | Normal |
| `pri:p3` | Backlog / whenever |

Default inbound that passes the gate: `pri:p2`.

## Rules (short)

1. Heimdall labels; others read.
2. No `verdict:pass` on `bifrost:out` without an artifact link if the text implies a ship.
3. `signal:noise` ⇒ `verdict:reject`, no `work:*`, no mill `ai:ready`.
4. `verdict:needs-scout` stops automation until the human moves it.
5. Do not invent Heimdall labels outside this file — extend the taxonomy here first.
6. Do not add mill `ai:*` here. On mill catalog repos, apply `ai:ready` per [`ISSUE_CRAFT.md`](ISSUE_CRAFT.md).

Machine-readable copy: [`labels.yml`](labels.yml). Apply with `python3 scripts/sync-labels.py` (see script header).
