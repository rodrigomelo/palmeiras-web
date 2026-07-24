# Mobile parity contract

The responsive Web product is the authoritative interface for Palmeiras Agenda.
iOS and Android are intentionally thin platform shells around that interface so
features, copy, data rendering, original team markers, theme behavior, and design tokens
cannot drift between releases.

## Product parity matrix

| Surface or behavior | Web/PWA | iOS | Android | Source of truth |
|---|---:|---:|---:|---|
| PA application identity and launcher icon | Yes | Yes | Yes | `scripts/export-brand-assets.py` |
| Header, next-match hero, countdown, recent H2H, and team markers | Yes | Same UI | Same UI | `apps/web` |
| Monthly calendar directly below the hero, with year/month navigation and competition filters | Yes | Same UI | Same UI | `apps/web` |
| Upcoming games and recent results | Yes | Same UI | Same UI | `apps/web` |
| Competition summaries and campaign records | Yes | Same UI | Same UI | `apps/web` |
| Tables and competition filtering | Yes | Same UI | Same UI | `apps/web` |
| Palmeiras statistics and charts | Yes | Same UI | Same UI | `apps/web` |
| Copa 2026 and Brazil filters | Yes | Same UI | Same UI | `apps/web` |
| News and external article navigation | Yes | Safari for external hosts | Default browser for external hosts | Web UI + native shell |
| Light/dark theme | Yes | Same UI | Same UI | `apps/web` |
| Data refresh | Button | Button + pull-to-refresh | Button | Web UI + native shell |
| Calendar download and copied feed URL | Yes | Safari handoff + clipboard | browser/download handoff + clipboard | Web UI + native shell |
| Loading and connection recovery | Web states | Native overlay + Web states | Native overlay + Web states | Native shell + Web UI |
| Back navigation | Browser | WebKit gestures/history | Android back button/history | Native shell |
| Compact Masculino/Feminino scope, score visibility, and alert controls | Yes | Native preference + same UI | Native preference + same UI | API + Web UI + native shell |
| Shared next-match banner with countdown, recent H2H, and Share/Calendar icons | Yes | Same UI | Same UI | `apps/web` + `/api/v1/match` |
| Historical archive | Yes | Same UI | Same UI | `apps/web` + `/api/v1/history` |
| Match alerts | Web Push | Local schedule + background refresh | Local alarms + periodic job | API collector + native shell |
| Home-screen widget | PWA install surface | WidgetKit | AppWidget | Native shell + shared API |
| Live match system surface | Browser notification | Live Activity/Dynamic Island | Live widget/notification | Native shell + shared API |

## Native-shell constraints

- Only HTTPS content from `palmeiras.rodrigolanna.com.br` stays inside the app.
- External hosts, non-Web URL schemes, and calendar downloads leave the embedded
  surface through the platform's safe URL handler.
- Android disables cleartext traffic, file access, content access, and mixed
  content. JavaScript and DOM storage remain enabled because the product needs
  them.
- iOS uses the persistent default Web data store, native pull-to-refresh, safe
  area insets, and back/forward navigation gestures.
- Android explicitly applies status/navigation-bar insets for edge-to-edge OS
  releases and preserves WebView history across configuration recreation.

## Release gates

Every shared release must pass:

1. Web mobile-width rendered smoke test with meaningful content, clean console,
   theme toggle, calendar navigation, and every primary section tab.
2. iOS simulator build/run plus screenshot at the first meaningful screen.
3. Android emulator build/install/run plus screenshot and fatal-log check.
4. Physical iPhone build/sign/install when the configured device is connected.
5. API tests, JavaScript syntax validation, JSON validation, OpenAPI lint, and
   `git diff --check`.
6. Production health/version check and cache-busted Web asset verification.
