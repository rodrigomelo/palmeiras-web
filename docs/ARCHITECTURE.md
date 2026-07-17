# Architecture

## Decision

Use a single public backend for all interfaces:

```text
apps/web
apps/ios       → services/api/palmeiras_api → Supabase
apps/android
```

Collectors are internal writers:

```text
services/collector/palmeiras_collector → Supabase
```

Production scheduling is handled by `palmeiras-collector.timer`, installed by
`scripts/deploy-vps.sh`. The timer runs the collector every 15 minutes and the
runner uses a lock to prevent overlapping refreshes.

## Boundaries

| Boundary | Owns | Does not own |
|---|---|---|
| `apps/web` | PWA UI, web-only caching, browser interactions | Supabase access, API transforms |
| `apps/ios` | SwiftUI native UI, iOS API client | Supabase access |
| `apps/android` | Android native UI, Kotlin API client | Supabase access |
| `services/api` | HTTP contract, validation, DTO transforms, read-only data access | Scraping, native UI |
| `services/collector` | External data ingestion and service-role writes | Public API serving |
| `packages/contracts` | OpenAPI schema and generated-client source | Runtime behavior |
| `infra/supabase` | Tables, indexes, RLS policies | App UI or API code |

## Public API

Use `/api/v1` for new clients. Legacy `/api/*` routes remain aliases.

```text
GET /api/v1/health
GET /api/v1/matches
GET /api/v1/standings
GET /api/v1/news
GET /api/v1/calendar_monthly
GET /api/v1/calendar.ics
```

## Compatibility Adapters

- `api/*.py` keeps legacy compatibility adapters thin.
- `server.py` adapts local/VPS HTTP requests into `services/api`.
- `collectors/*` adapts old imports into `services/collector`.

These adapters should stay thin. Business behavior belongs in the service
packages.
