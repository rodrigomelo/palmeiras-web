# Palmeiras Data Architecture

## Overview

Palmeiras project consists of two repos:
- `palmeiras-web` — Frontend (JS), API (Python), Collectors (Python)
- `palmeiras-data` — Collector logic lives inside `palmeiras-web/collectors/`

---

## Pipeline Flow

```
[Football-Data API] ──────────────────────────────┐
[ge.globo scraping]  ────────────────────────────┤
[lance.com.br scraping] ──────────────────────────┤
                                                    ↓
                                     [Collector: collectors/__init__.py]
                                     Python — transform to snake_case
                                     ⚠️ NO validation layer (CURRENTLY)
                                                    ↓
                                        [Supabase: matches, standings, news]
                                        ⚠️ JSON strings in nested fields
                                        ⚠️ standings/news: delete + insert (no upsert)
                                                    ↓
                                     [API: api/standings.py, matches.py]
                                     Python — camelCase transform
                                                    ↓
                                          [Frontend JS — consume]
```

---

## Data Criticidade Table

| Criticidade | Data | Impact if Missing |
|-------------|------|-------------------|
| 🔴 Alta | Match score, status | App is useless |
| 🔴 Alta | Standings position, points | Core feature broken |
| 🟡 Média | Broadcast, referee | Degraded but functional |
| 🟢 Baixa | Team crest, form | Fallback acceptable |

---

## API Contract

### `/api/standings?competition=BSA`

**Response:**
```json
{
  "standings": [
    {
      "position": 1,
      "teamName": "Palmeiras",
      "teamShort": "PAL",
      "crest": "https://...png",
      "playedGames": 10,
      "won": 7,
      "draw": 2,
      "lost": 1,
      "goalsFor": 20,
      "goalsAgainst": 8,
      "goalDifference": 12,
      "points": 23,
      "teamId": 1769
    }
  ]
}
```

### `/api/matches?status=FINISHED&limit=10`

**Response:**
```json
{
  "matches": [
    {
      "id": "12345",
      "utcDate": "2026-03-15T19:00:00Z",
      "status": "FINISHED",
      "matchday": 12,
      "stage": "REGULAR_SEASON",
      "venue": "Allianz Parque",
      "broadcast": "Premiere / Globo",
      "homeTeam": { "id": 1769, "name": "Palmeiras", "shortName": "PAL", "crest": "..." },
      "awayTeam": { "id": 1775, "name": "Corinthians", "shortName": "COR", "crest": "..." },
      "competition": { "id": 71, "name": "Campeonato Brasileiro", "code": "BSA", "emblem": "..." },
      "score": {
        "fullTime": { "home": 2, "away": 1 },
        "halfTime": { "home": 1, "away": 0 }
      },
      "homeScore": 2,
      "awayScore": 1
    }
  ]
}
```

---

## DB → API Transform (Naming Conventions)

| DB (snake_case) | API (camelCase) |
|-----------------|-----------------|
| `played_games` | `playedGames` |
| `team` (JSON) | `teamName`, `teamShort`, `teamId`, `crest` |
| `drawn` ⚠️ | `draw` |

---

## Gaps Identified

| Gap | Severity | Impact |
|-----|----------|--------|
| Standings without history (delete + insert pattern) | 🔴 CRITICAL | RPO = 0, all history lost on each run |
| News without archival | 🔴 CRITICAL | RPO = 0, articles lost on each run |
| No schema validation | 🔴 CRITICAL | Silent failures, field mismatches |
| No retry logic in collector | 🟡 MEDIUM | Data gaps if API source fails |
| No persistent logging | 🟡 MEDIUM | Hard to audit failures |
| JSON strings in DB (nested data) | 🟡 MEDIUM | Query complexity, parsing needed |
| Python ↔ JS naming mismatch | 🟡 MEDIUM | Interface confusion, bugs |

---

## Proposed Validation Layers

```
[Source API] → [Collector + Pydantic] → [Supabase] → [API Transform + Zod] → [Frontend + Zod]
                 ✅                       ✅              ✅                       ✅
```

| Layer | Tool | Validates |
|-------|------|----------|
| Collector input | Pydantic | Raw data from external API |
| API output | Zod | Response before serving |
| Frontend input | Zod | API response before render |

---

## Tech Stack

| Component | Technology |
|-----------|------------|
| Collector | Python 3 |
| External API | api.football-data.org (free tier) |
| Database | Supabase (PostgreSQL) |
| API Server | Python (built-in http.server) |
| Frontend | Vanilla JS |

---

## Dependencies

### Python (collector)
- `requests`
- `python-dotenv`
- `supabase` (PostgreSQL client)

### Frontend
- Vanilla JS (no framework specified)

---

## Next Steps

1. **🔴 CRITICAL** — Change standings/news from delete+insert to upsert (preserve history)
2. **🔴 CRITICAL** — Add Pydantic validation in collector
3. **🟡 MEDIUM** — Add retry with exponential backoff
4. **🟡 MEDIUM** — Add structured logging
5. **🟡 MEDIUM** — Zod validation in API Transform (Apollo/Hefesto)
6. **🟢 LOW** — Document design system (Athena)
7. **🟢 LOW** — Create TEST_PLAN.md (Apollo)

---

*Last updated: 2026-03-21*
*Maintained by: Poseidon (Data Architect)*
