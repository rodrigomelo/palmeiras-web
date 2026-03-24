# Palmeiras Dashboard

Dashboard web para acompanhar o Palmeiras — jogos, classificação, notícias e calendário.

## Architecture

```
index.html          → Frontend (static)
static/css/styles.css
static/js/app.js
api/                → Vercel serverless functions (production)
  ├── matches.py
  ├── standings.py
  ├── news.py
  └── calendar.py
server.py           → Local dev server (same API, direct Supabase)
collectors/         → Data collection scripts
```

**Local and Vercel share the same Supabase database.** The API contracts are identical.

## Quick Start

### Local Development

```bash
# Ensure .env has credentials
cp .env.example .env
# Edit .env with SUPABASE_URL and SUPABASE_KEY

# Start local server
python3 server.py
open http://localhost:5001
```

### Vercel (Production)

```bash
# Deploy
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

Supabase tables: `matches`, `standings`, `news`, `team_stats`.
Schema in `supabase-schema.sql`.

## Stack

- **Frontend:** Vanilla HTML/CSS/JS
- **API:** Python (Vercel serverless / local HTTP server)
- **Database:** Supabase (PostgreSQL)
- **Deploy:** Vercel
