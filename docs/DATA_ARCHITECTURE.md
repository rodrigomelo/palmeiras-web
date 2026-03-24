# Palmeiras Data Architecture

## Overview

Palmeiras Agenda uses a single Supabase database shared across:
- **Collector** — writes data (matches, standings, news)
- **Local server** (`server.py`) — reads data for development
- **Vercel API** (`api/*.py`) — reads data for production

All three connect to the same Supabase instance. API contracts are identical.

## Pipeline Flow

```
[football-data.org API] ──┐
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
| football-data.org | Matches, standings | REST API |
| ge.globo | News | HTML scraping (BeautifulSoup) |
| lance.com.br | News | HTML scraping (BeautifulSoup) |

## Competition Codes

| Code | Competition |
|------|-------------|
| `BSA` | Campeonato Brasileiro Série A |
| `COPA` | Copa do Brasil |
| `CLI` | Copa Libertadores |

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
| News scraper uses CSS selectors | 🟡 | Will break on site redesign |
| No data history (standings/news) | 🟡 | Delete-then-insert pattern |
| Copa do Brasil has limited crest coverage | 🟢 | Small teams may lack logos |
| football-data.org free tier limits | 🟡 | Rate limited |

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

*Last updated: 2026-03-24*
*Maintained by: Hefesto*
