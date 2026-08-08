# Data sources and provenance

This file summarizes the source registry already stored in the bundled SQLite database. It is a description of the project's recorded provenance, not a fresh verification of those external pages.

| Source | Recorded role in the project |
|---|---|
| Liquipedia — Esports World Cup 2026 | Tournament format, teams, placements / tournament metadata |
| Liquipedia — The International 2026 | Primary source recorded for TI 2026 participants |
| OpenDota heroes API | Hero ID → hero-name mapping |
| OpenDota match API | Fantasy fields that were absent from the local Dotabuff/Liquipedia cache |
| Dotabuff EWC 2026 pages | Match/league/player/team web snapshots and aggregate cross-checks |
| BattlePass Fantasy guide | Fantasy scoring coefficients recorded as the rules source |
| Dot Esports TI 2026 article | Secondary cross-check for TI 2026 participants |

The public database view `analytics_sources` exposes the source key, source name, URL, fetch/snapshot time, content type/status, hashes where available, and project notes.

## Source-first behavior

The query layer is designed to distinguish between facts already stored in SQLite and facts that would require an external source. Source-related requests can be routed to the source registry instead of silently inventing information.

## Snapshot caveat

External pages and tournament participant lists can change after a snapshot. The project stores provenance timestamps and source notes so the data can be audited against the original snapshot context.
