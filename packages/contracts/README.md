# Palmeiras API Contracts

This package is the source of truth for client/backend contracts.

- `openapi.yaml` defines the public `/api/v1` API used by Web, iOS, and Android.
- Legacy `/api/*` routes remain available as compatibility aliases, but new clients should use `/api/v1/*`.
- Generated client models should be derived from this package rather than handwritten from a UI implementation.
- Keep `info.version` aligned with `APP_VERSION`, the web service worker cache version, Android `versionName`, and the iOS app version constant.

Recommended client base URL:

```text
https://palmeiras.rodrigolanna.com.br
```

Every API request should append `/api/v1`.
