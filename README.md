# Palmeiras Agenda

Agenda web para acompanhar o Palmeiras — jogos, classificação, notícias e calendário.

## Architecture

```
palmeiras-web/
├── index.html                 → Frontend
├── server.py                  → Local dev server (direct Supabase)
├── vercel.json                → Vercel deployment config
├── .env                       → Local credentials (not tracked)
├── .env.example               → Template
├── static/
│   ├── css/styles.css         → Styles
│   ├── js/
│   │   ├── config.js          → Shared constants (TEAM_ID, stadiums, helpers)
│   │   └── app.js             → Application logic
│   ├── crests/*.png           → Cached team logos (22 teams)
│   └── favicon.png
├── api/                       → Vercel serverless functions
│   ├── matches.py
│   ├── standings.py
│   ├── news.py
│   └── calendar.py
├── collectors/                → Data collection scripts
│   ├── __init__.py            → Main collector (matches, standings, news, broadcast)
│   ├── crest_manager.py       → Logo download & cache
│   └── requirements.txt
├── data/                      → Raw data
├── docs/                      → Documentation
└── supabase-schema.sql        → Database schema
```

## Data Flow

```
[football-data.org API] ──→ [Collector] ──→ [Supabase] ──→ [API] ──→ [Frontend]
[ge.globo scraping]     ──→                                         
[lance.com.br scraping] ──→                                         
```

- **Collector** writes to Supabase
- **Local server** (`server.py`) reads from Supabase directly
- **Vercel API** reads from Supabase via env vars
- **Both APIs** return identical JSON contracts
- **Single Supabase instance** shared across all environments

## Quick Start

### Local Development

```bash
cd palmeiras-web

# Ensure .env has credentials
cp .env.example .env
# Edit .env with SUPABASE_URL and SUPABASE_KEY

# Start local server (use homebrew Python, not system Python)
/opt/homebrew/bin/python3 server.py
open http://localhost:5001
```

> **Note:** The system Python 3.9 (from Xcode) doesn't have `supabase` installed.
> Always use `/opt/homebrew/bin/python3` or install supabase for the system Python.

### Run the Collector

```bash
cd palmeiras-web
/opt/homebrew/bin/python3 -c "
from collectors import collect_matches, collect_standings, collect_news, apply_broadcast_info
collect_matches()
collect_standings()
collect_news()
apply_broadcast_info()
"
```

### Deploy to Vercel

```bash
npx vercel --prod

# Environment variables (set once)
npx vercel env add SUPABASE_URL production
npx vercel env add SUPABASE_KEY production
npx vercel env add SUPABASE_URL development
npx vercel env add SUPABASE_KEY development
```

## API Endpoints

| Endpoint | Description |
|---|---|
| `GET /api/matches?status=FINISHED&limit=50` | Match results |
| `GET /api/matches?status=SCHEDULED,TIMED&limit=10` | Upcoming matches |
| `GET /api/matches?status=IN_PLAY` | Live matches |
| `GET /api/standings?competition=BSA` | League standings |
| `GET /api/news?limit=10` | Recent news |
| `GET /api/calendar.ics` | iCal feed for calendar apps |

## Environment Variables

| Variable | Required | Description |
|---|---|---|
| `SUPABASE_URL` | ✅ | Supabase project URL |
| `SUPABASE_KEY` | ✅ | Supabase service role key |
| `FOOTBALL_API_KEY` | Collectors | football-data.org API key |

## Database

Supabase tables: `matches`, `standings`, `news`.
Schema in `supabase-schema.sql`.

## Crest Cache

Team logos are cached locally in `static/crests/{team_id}.png`.

- **`crest_manager.py`** downloads logos from football-data.org on first run
- Already cached logos are skipped (file exists check)
- Teams without logos show a placeholder SVG
- Known broken URLs (e.g., gstatic) are replaced with `crests.football-data.org`
- Run the collector to cache new team logos automatically

## Stack

- **Frontend:** Vanilla HTML/CSS/JS
- **API:** Python (Vercel serverless / local HTTP server)
- **Database:** Supabase (PostgreSQL)
- **Data:** football-data.org + web scraping (ge.globo, lance.com.br)
- **Deploy:** Vercel
