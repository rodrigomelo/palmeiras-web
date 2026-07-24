# Architecture

## Decision

Use the responsive Web product as the single user-interface implementation and
ship it through the PWA plus thin, secure iOS and Android shells:

```text
apps/web ──────────────────────────────┐
apps/ios (WKWebView shell) ────────────┼→ services/api/palmeiras_api → Supabase
apps/android (WebView shell) ──────────┘
```

This keeps every feature, interaction, original team marker, design token, and copy change
identical across Web, PWA, iOS, and Android. The native shells own platform
integration only: launcher identity, safe navigation, loading/error recovery,
external links, notifications, background refresh, widgets, iOS Live Activities,
and Android back navigation.

Collectors are internal writers:

```text
services/collector/palmeiras_collector → Supabase
```

Production scheduling is handled by `palmeiras-collector.timer`, installed by
`scripts/deploy-vps.sh`. The timer runs the collector every five minutes and the
runner uses a lock to prevent overlapping refreshes. The five-minute cadence also
drives Web Push delivery and live-event reconciliation.

## Boundaries

| Boundary | Owns | Does not own |
|---|---|---|
| `apps/web` | PWA UI, web-only caching, browser interactions | Supabase access, API transforms |
| `apps/ios` | SwiftUI/WKWebView shell and iOS navigation integration | Product UI duplication, Supabase access |
| `apps/android` | Android WebView shell and Android navigation integration | Product UI duplication, Supabase access |
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
GET /api/v1/match
GET /api/v1/history
GET /api/v1/h2h
GET /api/v1/push/public-key
POST /api/v1/push/subscriptions
```

## Compatibility Adapters

- `api/*.py` keeps legacy compatibility adapters thin.
- `server.py` adapts local/VPS HTTP requests into `services/api`.
- `collectors/*` adapts old imports into `services/collector`.

These adapters should stay thin. Business behavior belongs in the service
packages.
