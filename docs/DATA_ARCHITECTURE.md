# Palmeiras Data Architecture

## Overview

Palmeiras Agenda uses a single Supabase database shared across:
- **Collector** — writes data (Palmeiras matches, World Cup matches, standings, news)
- **Local server** (`server.py`) — reads data for development
- **Vercel API** (`api/*.py`) — reads data for production

All three connect to the same Supabase instance. API contracts are identical.

## Pipeline Flow

```
[football-data.org API] ──┐
[FIFA World Cup WC API] ──┤
[ge.globo scraping]     ──┤
[lance.com.br scraping] ──┤
                           ↓
              [Collector: collectors/__init__.py]
              Python — fetch, transform, cache crests
                           ↓
              [Supabase: matches, standings, news]
              • matches: upsert on external_id
              • standings: build first, then replace
              • news: keep existing if scraper fails
                           ↓
              [API: api/*.py (Vercel) | server.py (local)]
              Python — camelCase transform, same contracts
                           ↓
              [Frontend: static/js/app.js]
              Vanilla JS — render, no framework
```

## Data Sources

| Source | Data | Method |
|--------|------|--------|
| football-data.org | Palmeiras matches, World Cup 2026 matches, standings | REST API |
| ge.globo | News | HTML scraping (BeautifulSoup) |
| lance.com.br | News | HTML scraping (BeautifulSoup) |

## Competition Codes

| Code | Competition |
|------|-------------|
| `BSA` | Campeonato Brasileiro Série A |
| `COPA` | Copa do Brasil |
| `CLI` | Copa Libertadores |
| `WC` | FIFA World Cup 2026 |

## Crest Management

Team logos are cached in `static/crests/{team_id}.png`.

```
[football-data.org/crests] → [crest_manager.py] → [static/crests/*.png]
                                                         ↓
                                              [Supabase: local paths]
                                                         ↓
                                              [API returns /static/crests/ID.png]
```

- Downloads on first collector run, skips if already cached
- Known broken URLs (gstatic) replaced with `crests.football-data.org`
- Teams without logos get placeholder SVG on frontend

## API Contract

### `/api/matches`

Supported filters:
- `status=SCHEDULED,TIMED,FINISHED`
- `competition=BSA|CLI|COPA|WC`
- `team_id=1769`
- `from_date=YYYY-MM-DD`
- `to_date=YYYY-MM-DD`

```json
{
  "matches": [
    {
      "id": 554817,
      "utcDate": "2026-03-22T00:00:00+00:00",
      "status": "FINISHED",
      "matchday": 8,
      "stage": "REGULAR_SEASON",
      "venue": "Allianz Parque",
      "broadcast": "Premiere / Globo",
      "homeTeam": { "id": 1769, "name": "SE Palmeiras", "shortName": "Palmeiras", "crest": "/static/crests/1769.png" },
      "awayTeam": { "id": 1776, "name": "São Paulo FC", "shortName": "São Paulo", "crest": "/static/crests/1776.png" },
      "competition": { "code": "BSA", "name": "Campeonato Brasileiro Série A" },
      "score": {
        "fullTime": { "home": 3, "away": 1 },
        "halfTime": { "home": 1, "away": 0 }
      }
    }
  ]
}
```

### `/api/standings`

```json
{
  "standings": [
    {
      "position": 1,
      "teamName": "SE Palmeiras",
      "teamShort": "Palmeiras",
      "crest": "/static/crests/1769.png",
      "playedGames": 8,
      "won": 6, "draw": 1, "lost": 1,
      "goalsFor": 17, "goalsAgainst": 8,
      "goalDifference": 9,
      "points": 19,
      "teamId": 1769
    }
  ]
}
```

### `/api/news`

```json
[
  {
    "id": "uuid",
    "title": "News headline",
    "url": "https://ge.globo.com/...",
    "image": "https://...",
    "source": "ge.globo",
    "collected_at": "2026-03-24T21:03:09+00:00"
  }
]
```

## DB → API Transform

| DB (snake_case) | API (camelCase) |
|-----------------|-----------------|
| `external_id` | `id` |
| `utc_date` | `utcDate` |
| `home_team` (JSON) | `homeTeam` (object) |
| `away_team` (JSON) | `awayTeam` (object) |
| `competition` (JSON) | `competition` (object) |
| `home_score` | `homeScore` + `score.fullTime.home` |
| `half_time_home` | `score.halfTime.home` |
| `played_games` | `playedGames` |
| `drawn` | `draw` |
| `goals_for` | `goalsFor` |
| `goals_against` | `goalsAgainst` |
| `goal_difference` | `goalDifference` |

## Known Limitations

| Issue | Severity | Notes |
|-------|----------|-------|
| News scraper uses CSS selectors | Medium | Will break on site redesign; current collector keeps existing data if no articles are collected |
| Standings/news history is not versioned | Medium | Upserts preserve current rows, but there is no historical snapshot table |
| Copa do Brasil free-source scraper is best-effort | Medium | Manual fallback exists; raw scraper records now use schema-safe integer IDs |
| football-data.org free tier limits | Medium | World Cup collector uses one bulk endpoint and a small retry/backoff |
| World Cup venues missing from football-data match payloads | Low | ICS and UI use "A definir" unless upstream starts providing venue data |
| Public write RLS policies are permissive in schema example | High | Production should use service-role writes from collectors only; anon clients should remain read-only |

## 2026 World Cup Collection

The collector now calls:

```text
GET https://api.football-data.org/v4/competitions/WC/matches?season=2026
```

Expected contract on 2026-06-03:
- `resultSet.count = 104`
- `resultSet.first = 2026-06-11`
- `resultSet.last = 2026-07-19`
- `competition.code = WC`

Records are written to the same `matches` table as Palmeiras fixtures. The frontend keeps Palmeiras-specific widgets scoped with `team_id=1769`, while the calendar and `.ics` feed intentionally include both Palmeiras and World Cup matches.

## Robustness Review

Completed improvements:
- Added `collect_world_cup()` with schema-safe transformation and idempotent `upsert`.
- Increased monthly calendar limit from 80 to 250 and ICS limit from 150 to 500.
- Added `/api/matches` filters for `competition`, `team_id`, `from_date`, and `to_date`.
- Fixed latest-results ordering so finished-match views fetch newest rows first.
- Fixed Copa do Brasil raw scraper IDs to be integers, matching `matches.external_id INTEGER`.
- Stripped collector-only fields such as `source` before Supabase writes.
- Extended score resolver competition tokens for `WC`.

Recommended next hardening:
- Run the Supabase schema with read-only anon policies and service-role-only writes.
- Add a collector run log table with source, row counts, duration, and error message.
- Add alerting when World Cup count differs from 104 or the collector returns zero rows.
- Add a scheduled database backup/restore drill before the tournament begins.
- Consider a venue enrichment source if stadium-level ICS locations become important.

## Stack

| Component | Technology |
|-----------|------------|
| Frontend | Vanilla HTML/CSS/JS |
| API | Python (Vercel serverless / http.server) |
| Database | Supabase (PostgreSQL) |
| Data sources | football-data.org, web scraping |
| Deploy | Vercel |
| Crest cache | Local PNG files in `static/crests/` |

---

*Last updated: 2026-06-03*
*Maintained by: Hefesto*
