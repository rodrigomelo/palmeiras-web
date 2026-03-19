# Palmeiras Dashboard

A football dashboard for Sociedade Esportiva Palmeiras, showing upcoming matches, results, standings, stats, news, and calendar integration.

## Architecture

```
External APIs              Supabase               Vercel
┌─────────────────┐       ┌──────────┐      ┌──────────────────┐
│ football-data.org│──┐    │ matches  │      │ palmeiras-data   │
│ (matches, tables)│  ├───▶│ standings│◀─────│ (FastAPI API)    │
│                  │  │    │ news     │      └────────┬─────────┘
│ ge.globo         │──┘    └──────────┘               │
│ (news)           │                                   │ reads
└─────────────────┘                                   ▼
                                              ┌──────────────────┐
                                              │ palmeiras-web    │
                                              │ (static + proxy) │
                                              └────────┬─────────┘
                                                       │
                                                       ▼
                                              ┌──────────────────┐
                                              │ Browser/Dashboard│
                                              └──────────────────┘
```

## Projects

| Folder | Description | Vercel URL | Local Port |
|--------|-------------|------------|------------|
| [`data/`](data/) | API + Collectors (FastAPI + Supabase) | [palmeiras-data.vercel.app](https://palmeiras-data.vercel.app) | 5002 |
| [`web/`](web/) | Dashboard UI (static + Flask proxy) | [palmeiras-web.vercel.app](https://palmeiras-web.vercel.app) | 5001 |

## Local vs Vercel

| Aspect | Local | Vercel |
|--------|-------|--------|
| **Web** | Flask serves HTML + proxies /api/* | Static files + vercel.json routes API to data |
| **Data** | Flask/FastAPI on port 5002 | FastAPI serverless function |
| **API calls** | Web → localhost:5002 → Supabase | Web → vercel proxy → data.vercel.app → Supabase |

This difference is **intentional**: Vercel doesn't support persistent Flask servers, so the web app becomes static files with API proxying via `vercel.json`.

## Quick Start

```bash
# Data API
cd data
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # configure Supabase credentials
python api/main.py     # http://localhost:5002

# Web Dashboard (in another terminal)
cd web
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python server.py       # http://localhost:5001
```

## Data Collection

```bash
cd data
source .venv/bin/activate
python -c "from collectors import run_all; run_all()"
```

## Key Principles

- **Zero external calls from frontend** — all data via Supabase → Data API
- **Supabase as single source of truth** — collectors populate, API reads
- **Local-first development** — test locally before deploying to Vercel
- **Never deploy without local testing**

## Endpoints

| Endpoint | Description |
|----------|-------------|
| `GET /api/matches?status=FINISHED` | Past results (newest first) |
| `GET /api/matches?status=SCHEDULED,TIMED` | Upcoming matches |
| `GET /api/standings?competition=BSA` | League table |
| `GET /api/news` | Latest news |
| `GET /api/calendar.ics` | iCal feed |

---
*Palmeiras Dashboard v2.0 — Refactored 2026-03-19*
