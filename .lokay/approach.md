# Approach plan

<!-- lokay-approach source=deterministic repo=mikolaj92/heimdall issue=35 -->

Repository: `mikolaj92/heimdall`  
Issue: #35 — Podłącz tick ścieżki monitor albo zdejmij twierdzenie z README

## Goal

`fala-package.toml` opisuje ścieżkę `monitor` (observe-queue → dual-label-pass → observe-verdict → outbound → blocked → influenzer → inbound → cleared). README i `CHANNEL.md` piszą, że Fala to składa. Na hoście nie ma LaunchAgenta, skryptu ani udokumentowanej komendy, która odpala ten pakiet. LaunchAgent `ai.mikolaj.lokay-mill` tyka tylko Lokaya. Pakiet leży martwy; `dual-label-pass` na katalogu nie ma rytmu.

## Files likely touched

- `fala-package.toml`
- `CHANNEL.md`
- `README.md`

Chose option B (manual run; Fala does not tick). Localize scope excluded `scripts/`; Fala has no standalone `run-until-idle` CLI, so a host script would invent a command this repo cannot honestly document.

## Test plan

- README / `CHANNEL.md` mówią jedną prawdę: jak odpalić `correlation_paths.id = "monitor"` (komenda z cwd repo, `uv run`, pakiet Fala) **albo** że monitor jest ręczny i Fala go nie tyka
- Jeśli tick: skrypt w repo (np. `scripts/heimdall-monitor.sh`) woła Fala na `fala-package.toml` path `monitor`; bez gołego `python3`; bez budzenia młyna / SSH / mail
- Skrypt nie jest GitHub Action i nie jest nowym fat composerem w Pythonie
- `fala-package.toml` zostaje źródłem kolejności; nie duplikować 1..8 w Pythonie
- Krótki self-check w README: co operator widzi po jednym ticku (JSON / `FALA_EFFECTOR_OUTPUT_DIR`)

## Non-goals

- Apple Mail / Bifrost MCP. Nowe observe-*. Zmiana katalogu młyna.

## Notes

- Trust intentional issue; this plan is evidence for later review, not a human gate.
- Coding agent may refine details but should stay on the stated goal and non-goals.
- Collector boundary: if implementation introduces unbounded collection, ship only a bounded collector patch that starts durably in the background after merge. The coding agent and mill must not populate data or wait for collection to finish.
