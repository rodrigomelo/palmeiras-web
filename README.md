# Palmeiras Agenda

Shared backend plus Web, iOS, and Android clients for Palmeiras Agenda.

## Architecture

```text
palmeiras-web/
├── apps/
│   ├── web/                  # PWA/web client
│   ├── ios/                  # native iOS scaffold
│   └── android/              # native Android scaffold
├── services/
│   ├── api/                  # single public backend implementation
│   └── collector/            # internal ingestion jobs
├── packages/
│   └── contracts/            # OpenAPI contract shared by all clients
├── infra/
│   └── supabase/             # database schema and RLS policies
├── api/                      # compatibility HTTP adapters
├── collectors/               # compatibility wrappers for old imports
└── server.py                 # local/VPS static/API adapter
```

## Shared Backend Rule

All clients must use the same public API:

```text
https://palmeiras.rodrigolanna.com.br/api/v1
```

Current legacy `/api/*` paths remain available for compatibility, but new client
code should use `/api/v1/*`.

The API implementation lives in `services/api/palmeiras_api`. The root `api/*.py`
files are thin compatibility adapters. `server.py` uses the same package locally
and on the VPS, so local and production API behavior cannot drift.

## Brand Identity

The app logo and PWA icon are the original PA calendar mark, not the Palmeiras
crest. Brand rules, logo variants, color tokens, and export instructions live in
`docs/BRAND_IDENTITY.md`.

Run `scripts/export-brand-assets.py` after any logo SVG change. It refreshes the
web/PWA icons, favicon, social card, Android launcher icons, and iOS AppIcon
asset catalog from the same PA mark source.

## Data Flow

```text
football-data.org / FIFA / scrapers
        ↓
services/collector → Supabase PostgreSQL
        ↓
services/api/palmeiras_api
        ↓
apps/web, apps/ios, apps/android
```

Collectors are internal jobs and may use `SUPABASE_KEY` / service role. Web, iOS,
and Android never connect directly to Supabase.

## Local Development

```bash
cp .env.example .env
# Fill SUPABASE_URL and SUPABASE_ANON_KEY for read-only API access.

python3 server.py
open http://localhost:5001
```

Without Supabase env vars, the web app still serves locally and API routes return
`503` with a `not_configured`/degraded health response.

## API Contract

The public contract is in:

```text
packages/contracts/openapi.yaml
```

Main endpoints:

| Endpoint | Description |
|---|---|
| `GET /api/v1/health` | Backend health |
| `GET /api/v1/matches?status=FINISHED&limit=50` | Match results |
| `GET /api/v1/matches?status=SCHEDULED,TIMED&team_id=1769&limit=10` | Palmeiras upcoming matches |
| `GET /api/v1/matches?competition=WC&from_date=2026-06-11&to_date=2026-07-19&limit=200` | FIFA World Cup 2026 matches |
| `GET /api/v1/standings?competition=BSA` | League standings |
| `GET /api/v1/news?limit=10` | Recent news |
| `GET /api/v1/calendar_monthly?year=2026&month=7` | Calendar grid data |
| `GET /api/v1/calendar.ics` | iCalendar feed |

## Web

Source: `apps/web`

The web client defaults to same-origin `/api/v1`. To point it at another backend,
set `window.PALMEIRAS_API_BASE_URL` before `apps/web/static/js/config.js` loads or
set the `api-base-url` meta tag in `apps/web/index.html`.

## iOS

Source: `apps/ios`

The iOS scaffold contains SwiftUI app files, DTOs, and `PalmeirasAPIClient`.
Create an Xcode SwiftUI app target named `PalmeirasAgenda`, add the Swift files
from `apps/ios/PalmeirasAgenda`, and keep future DTOs generated from
`packages/contracts/openapi.yaml`.

## Android

Source: `apps/android`

The Android scaffold contains a Gradle project, Kotlin DTOs, and
`PalmeirasApiClient`. It calls the same `/api/v1` backend as Web and iOS.

## Collector

Source: `services/collector/palmeiras_collector`

Compatibility imports from `collectors` still work. New code should import from
`services.collector.palmeiras_collector`.

```bash
python3 -m services.collector.palmeiras_collector.runner
```

The runner refreshes Palmeiras matches, Copa do Brasil, Copa 2026, standings,
past-match scores, broadcasts, and news in one idempotent pipeline. It uses a
file lock so two collector runs cannot overlap. After Copa 2026 finishes, run it
with `--skip-world-cup` or remove the World Cup step from the deployed timer.

Production runs are automatic through `deploy/palmeiras-collector.timer`:

```bash
systemctl list-timers palmeiras-collector.timer
systemctl status palmeiras-collector.timer
journalctl -u palmeiras-collector.service -n 120 --no-pager
```

## Deploy

### VPS

```bash
scripts/deploy-vps.sh
```

The VPS systemd service runs `server.py`, while Nginx serves `apps/web` static
files and proxies `/api/` to the same local backend adapter.
Deploy also installs and enables `palmeiras-collector.timer`, which runs the
collector every 15 minutes and shortly after boot. `/api/v1/health` includes
`services.data_freshness` so deployments and monitoring can see when matches,
standings, or news are stale.

## Environment Variables

| Variable | Required | Owner | Description |
|---|---:|---|---|
| `SUPABASE_URL` | yes | API/collector | Supabase project URL |
| `SUPABASE_ANON_KEY` | yes | API | Read-only public key |
| `SUPABASE_KEY` | collector only | Collector | Service-role key for ingestion writes |
| `APP_VERSION` | recommended | API | Version returned by `/health` |
| `FOOTBALL_API_KEY` | collector only | Collector | football-data.org key |
| `HOST` / `PORT` | local/VPS | API adapter | Local server bind config |
| `ALLOWED_ORIGINS` | optional | API adapter | CORS allowlist for local/VPS |

## Database

Schema and RLS policies live in `infra/supabase/schema.sql`.

Public clients should read through the API. Write/update/delete policies are
service-role only so native and web clients cannot mutate Supabase directly.
