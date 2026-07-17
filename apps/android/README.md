# Palmeiras Agenda Android

Native Android client scaffold for the shared Palmeiras Agenda backend.

The app must call the same backend as Web and iOS:

```text
https://palmeiras.rodrigolanna.com.br/api/v1
```

The Android client retries the legacy `/api` route for compatibility with older
deployments, matching the iOS fallback behavior.

Current shared app/API version: `1.1.37`. Keep Gradle `versionName`,
`ApiConfig.APP_VERSION`, `APP_VERSION`, and `packages/contracts/openapi.yaml`
aligned.

Current contents:

- `app/src/main/java/com/palmeiras/agenda/ApiConfig.kt` - API base URL
- `app/src/main/java/com/palmeiras/agenda/PalmeirasApiClient.kt` - backend client
- `app/src/main/java/com/palmeiras/agenda/Models.kt` - DTOs matching `packages/contracts/openapi.yaml`
- `app/src/main/java/com/palmeiras/agenda/MainActivity.kt` - minimal native loading screen
- `app/src/main/res/mipmap-*` - generated PA calendar launcher icons

Keep all future models generated from `packages/contracts/openapi.yaml`.
Refresh launcher icons from the shared brand source with:

```bash
scripts/export-brand-assets.py
```
