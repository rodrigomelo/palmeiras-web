# Palmeiras Dashboard - System Architecture (v6)

## ⚠️ STABLE VERSION - CAREFUL WITH CHANGES!

**This version is stable and working. Do not break this!**

### Current Stable URLs
| Service | URL | Status |
|---------|-----|--------|
| Palmeiras Web | https://palmeiras-web.vercel.app | ✅ Stable |
| Palmeiras Data API | https://palmeiras-data.vercel.app | ✅ Stable |
| Supabase | https://supabase.com | ✅ Active |

### Deployment Workflow (MANDATORY!)
1. **Local first** - Deploy to localhost (ports 5001, 5002)
2. **Test locally** - Human tests and approves
3. **Deploy to production** - Only after approval, deploy to Vercel

**Never deploy to Vercel without local testing!**

---

## Overview

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           PALMEIRAS DASHBOARD                          │
│                         Arquitetura v6                                 │
└─────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────┐
│                         DATA LAYER (Supabase)                          │
│  ┌─────────────────────────────────────────────────────────────────┐ │
│  │  CRON JOB (scheduler)                                            │ │
│  │  ┌──────────────────┐    ┌──────────────────┐                   │ │
│  │  │ Palmeiras Data   │───▶│ football-data.org│                   │ │
│  │  │ Collector        │    │     (API)        │                   │ │
│  │  └──────────────────┘    └──────────────────┘                   │ │
│  │           │                                                      │ │
│  │           ▼                                                      │ │
│  │  ┌──────────────────────────────────────────────────────────────┐│ │
│  │  │                    SUPABASE DATABASE                         ││ │
│  │  │  • matches (partidas passadas e futuras)                    ││ │
│  │  │  • standings (classificação)                                ││ │
│  │  │  • news (notícias)                                           ││ │
│  │  └──────────────────────────────────────────────────────────────┘│ │
│  └─────────────────────────────────────────────────────────────────┘ │
└──────────────────────────────────┬────────────────────────────────────┘
                                   │ (reads from Supabase)
                                   ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                    DATA API (palmeiras-data)                           │
│  ┌─────────────────────────────────────────────────────────────────┐ │
│  │  VERCEL (Serverless Python)                                     │ │
│  │  ┌──────────────────┐                                            │ │
│  │  │ FastAPI         │───▶ Lê do Supabase                        │ │
│  │  │ Endpoints:      │     • /api/matches                         │ │
│  │  │   /api/matches  │     • /api/standings                        │ │
│  │  │   /api/standings│     • /api/news                            │ │
│  │  │   /api/news     │                                            │ │
│  │  └──────────────────┘                                            │ │
│  └─────────────────────────────────────────────────────────────────┘ │
└──────────────────────────────────┬────────────────────────────────────┘
                                   │ (reads from Data API)
                                   ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                    WEB APP (palmeiras-web)                             │
│  ┌─────────────────────────────────────────────────────────────────┐ │
│  │  VERCEL (Serverless Python)                                     │ │
│  │  ┌──────────────────┐    ┌──────────────────┐                   │ │
│  │  │ Flask Server     │───▶│  Static Files   │                   │ │
│  │  │ (reads API)      │    │  (index.html)   │                   │ │
│  │  └──────────────────┘    └──────────────────┘                   │ │
│  │           │                                                      │ │
│  │           ▼                                                      │ │
│  │  ┌──────────────────────────────────────────────────────────────┐│ │
│  │  │              USER BROWSER                                  ││ │
│  │  │  🖥️ Palmeiras Dashboard                                     ││ │
│  │  │     • Próximo Jogo (hero card)                              ││ │
│  │  │     • Lista de Jogos                                        ││ │
│  │  │     • Classificação                                         ││ │
│  │  │     • Estatísticas                                           ││ │
│  │  │     • Notícias                                               ││ │
│  │  │     • Calendário ICS                                         ││ │
│  │  └──────────────────────────────────────────────────────────────┘│ │
│  └─────────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────┐
│                         EXTERNAL SERVICES                               │
│  ┌──────────────────┐    ┌──────────────────┐    ┌───────────────┐   │
│  │ football-data.org │    │   ge.globo       │    │ Google Calendar│  │
│  │   (matches,       │    │   (news)         │    │   (subs)       │  │
│  │    standings)     │    │                  │    │                │  │
│  └──────────────────┘    └──────────────────┘    └───────────────┘  │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Data Flow

### 1. Data Collection (Cron Job)
```
Scheduler (Vercel Cron / Local Cron)
        ↓
Palmeiras Collector → football-data.org API
        ↓
Supabase Database
```

### 2. Data Serving
```
User Request → Palmeiras Web (Flask)
        ↓
Palmeiras Data API (FastAPI) → Supabase
        ↓
JSON Response
```

### 3. Calendar Subscription
```
User subscribes to .ics → Palmeiras Web → reads Supabase → generates calendar
```

---

## Key Principles

| Principle | Description |
|-----------|-------------|
| **Zero Direct External Calls** | Frontend never calls external APIs |
| **Supabase as Single Source** | All data stored in our database |
| **Cron-based Sync** | External APIs called only by schedulers |
| **Offline Fallback** | Works if external APIs are down (data still in Supabase) |
| **Fast Loading** | Serves from cache/database, no wait for external API |

---

## API Endpoints

| Endpoint | Description | Data Source |
|----------|-------------|-------------|
| `/api/matches` | All matches | Supabase: matches table |
| `/api/standings` | League table | Supabase: standings table |
| `/api/news` | News articles | Supabase: news table |
| `/calendar.ics` | Calendar feed | Generated from matches |

---

## File Structure

```
palmeiras-data/                     # DATA LAYER
├── collectors/
│   └── __init__.py                 #   Data collection logic
├── api_flask.py                    #   FastAPI server
├── handler.py                      #   Vercel handler
├── vercel.json                     #   Vercel config
└── .venv/                          #   Python dependencies

palmeiras-web/                      # PRESENTATION LAYER
├── server.py                       #   Flask server
├── index.html                      #   Frontend dashboard
├── api/
│   ├── index.py                    #   API routes
│   └── cache.py                    #   Caching utilities
├── vercel.json                     #   Vercel config
└── requirements.txt                #   Python dependencies

shared:
└── supabase/                       #   Database schema & config
```

---

## Supabase Schema

### matches table
```sql
id              -- Match ID from football-data.org
utcDate         -- Match date/time (UTC)
status          -- FINISHED, SCHEDULED, TIMED, IN_PLAY
homeTeam        -- {id, name, crest}
awayTeam        -- {id, name, crest}
score           -- {fullTime: {home, away}}
competition     -- {id, name, code}
venue           -- Stadium name
matchday        -- Round number
```

### standings table
```sql
competition     -- Competition ID
position       -- Table position
team           -- {id, name, crest}
playedGames    -- Games played
won            -- Wins
drawn          -- Draws
lost           -- Losses
goalsFor       -- Goals for
goalsAgainst   -- Goals against
goalDifference -- Goal difference
points         -- Total points
```

### news table
```sql
id              -- Unique ID
title           -- Article title
url             -- Article URL
source          -- Source (ge.globo, lance, etc.)
publishedAt     -- Publication date
```

---

## Deployment URLs

| Service | URL | Status |
|---------|-----|--------|
| Palmeiras Data API | https://palmeiras-data.vercel.app | ✅ Active |
| Palmeiras Web | https://palmeiras-web.vercel.app | ✅ Active |
| Supabase | https://supabase.com | ✅ Active |

---

## ⚠️ IMPORTANT: Local vs Remote Ports

**NEVER confuse local ports with remote URLs!**

### Local Development
| Service | Port | URL |
|---------|------|-----|
| Palmeiras Web | 5001 | http://localhost:5001 |
| Palmeiras Data | 5002 | http://localhost:5002 |

### Remote (Vercel)
| Service | URL |
|---------|-----|
| Palmeiras Web | https://palmeiras-web.vercel.app |
| Palmeiras Data | https://palmeiras-data.vercel.app |

The frontend detects the environment automatically via `isLocal` variable in `index.html`.

---

## ⏰ Timezone

All dates and times are displayed in **Sao Paulo, Brazil (GMT-3)**.

This applies to:
- Frontend display (using `BR_TZ = 'America/Sao_Paulo'`)
- ICS calendar export (converted from UTC to GMT-3)

The calendar ICS includes:
- **Past games** with results (e.g., "🏆 SE Palmeiras 2 x 1 Fluminense")
- **Upcoming games** (e.g., "🏆 SE Palmeiras x Grêmio FBPA")

Both "Download" and "Copy Link" buttons generate the ICS file locally in the browser.

---

## Environment Variables

| Variable | Description | Where |
|----------|-------------|-------|
| `SUPABASE_URL` | Supabase project URL | Palmeiras Data API |
| `SUPABASE_KEY` | Supabase anon key | Palmeiras Data API |
| `FOOTBALL_API_KEY` | API key for football-data.org | Collector (local) |

---

## Benefits

✅ **No Rate Limiting Issues** - External API called only by schedulers  
✅ **High Reliability** - Works even if external APIs are down  
✅ **Fast Performance** - Serves from Supabase instantly  
✅ **Data Ownership** - All data stored in our database  
✅ **Easy Debugging** - Check Supabase tables directly  

---

*Documentation updated: 2026-03-16*
*Palmeiras Dashboard v6*
