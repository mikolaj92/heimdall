# Heimdall

Main gate for the org — the face toward the human scout and toward the world.

Heimdall is who you talk to. Heimdall is who the outside world talks to. Lokay only receives **ready-made issues** and produces code; Influenzer sells and brings feedback back to Heimdall. Heimdall decides what becomes work, whether it fits the repo, and whether the result passes QA.

## Role

- **Front door** — human scout and external world interface here, not at Lokay
- **Inbound triage** — feedback from Influenzer, mentions, issues → label, accept or reject
- **Issue craft** — turn accepted signal into a repo-compatible, ready issue for Lokay
- **Fit check** — does this belong in this repo / this product at all?
- **QA** — review Lokay’s result before it counts as done / before Influenzer may claim a ship
- **Labels** — owns the taxonomy ([`LABELS.md`](LABELS.md))

Not the creator. Not the seller. The bridge and the eyes on it.

## Flow

```text
world / scout ──► Heimdall ──► ready issue ──► Lokay ──► code
                     ▲                              │
                     │         QA / verdict         │
                     └──────────────────────────────┘
                     ▲
              Influenzer (feedback + outbound gated by verdict)
```

## Labels

Taxonomy (source of truth): [`LABELS.md`](LABELS.md) · machine-readable: [`labels.yml`](labels.yml)

Namespaces: `bifrost` · `verdict` · `signal` · `source` · `story` · `work` · `pri`

## Status

Role + taxonomy v1. Automations TBD.
