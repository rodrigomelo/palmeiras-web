# Palmeiras Data Architecture

## Overview

Palmeiras Agenda now separates ingestion, backend, and clients:

- `services/collector/palmeiras_collector` writes to Supabase.
- `services/api/palmeiras_api` reads from Supabase and exposes `/api/v1`.
- `apps/web`, `apps/ios`, and `apps/android` consume the same API contract.
- `packages/contracts/openapi.yaml` documents the public contract.

Legacy root folders `api/` and `collectors/` are compatibility adapters only.

## Flow

```text
[football-data.org] ──┐
[FIFA World Cup API] ─┤
[ge.globo scraping]  ─┤
[lance scraping]     ─┘
          ↓
services/collector/palmeiras_collector
          ↓ service-role writes
Supabase PostgreSQL
          ↓ read-only backend access
services/api/palmeiras_api
          ↓ /api/v1 JSON + ICS
apps/web     apps/ios     apps/android
```

## Backend Boundary

All interfaces must call the API, not Supabase:

```text
https://palmeiras.rodrigolanna.com.br/api/v1
```

Allowed compatibility aliases:

```text
/api/* → same route implementation as /api/v1/*
```

The compatibility aliases exist so the deployed web app and old links keep
working. New client code should use `/api/v1`.

## API Ownership

The single backend implementation lives in:

```text
services/api/palmeiras_api
```

Important files:

| File | Responsibility |
|---|---|
| `shared.py` | Supabase REST access, validation, DTO transforms |
| `routes.py` | Public route behavior and `/api` + `/api/v1` dispatch |
| `ical.py` | iCalendar rendering |
| `adapters.py` | BaseHTTPRequestHandler response adapters |

Compatibility adapters in `api/*.py` and the local/VPS `server.py` both call
this same package.

## Public Contract

Source of truth:

```text
packages/contracts/openapi.yaml
```

Current route groups:

| Route | Client use |
|---|---|
| `/api/v1/health` | deployment health/version |
| `/api/v1/matches` | Palmeiras and World Cup match lists |
| `/api/v1/standings` | league table |
| `/api/v1/news` | recent news |
| `/api/v1/calendar_monthly` | month grid data |
| `/api/v1/calendar.ics` | calendar feed |

## Data Tables

| Table | Writer | Reader |
|---|---|---|
| `matches` | collector service role | API read-only key |
| `standings` | collector service role | API read-only key |
| `news` | collector service role | API read-only key |

Schema and RLS policies live in:

```text
infra/supabase/schema.sql
```

Reads are public through Supabase RLS; writes/update/delete policies are scoped
to `service_role`. Public clients should still read through the backend API so
contracts, caching, and transformations stay consistent.

## DB To API Transform

| DB | API |
|---|---|
| `external_id` | `id` |
| `utc_date` | `utcDate` |
| `home_team` JSON | `homeTeam` |
| `away_team` JSON | `awayTeam` |
| `competition` JSON | `competition` |
| `home_score` | `homeScore`, `score.fullTime.home` |
| `away_score` | `awayScore`, `score.fullTime.away` |
| `half_time_home` | `score.halfTime.home` |
| `half_time_away` | `score.halfTime.away` |
| `played_games` | `playedGames` |
| `goals_for` | `goalsFor` |
| `goals_against` | `goalsAgainst` |
| `goal_difference` | `goalDifference` |

## Client Configuration

| Client | API base configuration |
|---|---|
| Web | `CONFIG.API_BASE_URL` in `apps/web/static/js/config.js`; defaults to same-origin |
| iOS | `AppConfiguration.production.apiBaseURL` |
| Android | `ApiConfig.BASE_URL` |

All three point at `/api/v1`.

## Operational Notes

- Configure `SUPABASE_URL` and `SUPABASE_ANON_KEY` for the API.
- Configure `SUPABASE_KEY` and `FOOTBALL_API_KEY` for collector/internal jobs.
- Set `APP_VERSION` so `/api/v1/health` matches release metadata.
- Configure `/etc/palmeiras-web.env` on the VPS before production deploy;
  otherwise clients show backend loading errors because `/health` and data
  endpoints return `503`.
- Production deploy installs `palmeiras-collector.timer`, which runs the
  collector every 15 minutes, shortly after boot, and without overlapping runs.
- `/api/v1/health` reports `services.data_freshness` for matches, standings,
  and news so stale ingestion is visible to deploy checks and monitoring.
