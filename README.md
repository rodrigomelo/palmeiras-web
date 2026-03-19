# Palmeiras Dashboard

Football dashboard for Sociedade Esportiva Palmeiras — upcoming matches, results, standings, stats, news, and calendar.

## Architecture

```
Supabase                    Vercel (single project)
┌──────────┐               ┌──────────────────────────────────┐
│ matches  │◀──────────────│ /api/matches.py                  │
│ standings│◀──────────────│ /api/standings.py                │
│ news     │◀──────────────│ /api/news.py                     │
└──────────┘               │ /api/calendar.py                 │
      ▲                    │                                  │
      │                    │ index.html  ← static             │
      │                    │ static/css/  ← static            │
┌──────────┐               │ static/js/   ← static            │
│Collector │               └──────────────────────────────────┘
│(cron)    │
└──────────┘
```

One Vercel project. Static files + Python serverless functions. Same domain, no proxy, no CORS.

## Local Development

```bash
# Install Vercel CLI
npm i -g vercel

# Link project
vercel link

# Run locally (matches production exactly)
vercel dev
```

Open http://localhost:3000

## Data Collection

```bash
cd collectors
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp ../.env .env  # or set SUPABASE_URL and SUPABASE_KEY
python __init__.py
```

## Environment Variables

| Variable | Description |
|----------|-------------|
| `SUPABASE_URL` | Supabase project URL |
| `SUPABASE_KEY` | Supabase service_role key |
| `FOOTBALL_API_KEY` | football-data.org API key (collectors only) |

## Endpoints

| Endpoint | Description |
|----------|-------------|
| `GET /api/matches?status=FINISHED` | Past results |
| `GET /api/matches?status=SCHEDULED,TIMED` | Upcoming matches |
| `GET /api/standings?competition=BSA` | League table |
| `GET /api/news` | Latest news |
| `GET /api/calendar.ics` | iCal subscription feed |

---
*v2.0 — Single Vercel project architecture*
