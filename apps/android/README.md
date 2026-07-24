# Palmeiras Agenda Android

Kotlin/WebView mobile shell for the responsive Palmeiras Agenda product.

The app loads the same production interface used by Web, PWA, and iOS:

```text
https://palmeiras.rodrigolanna.com.br/
```

The shell owns Android integration only: a persistent native bottom menu,
notification and appearance settings, manual refresh, secure navigation,
downloads, loading and error recovery, WebView history, and native launcher
assets.

Current shared app/API version: `1.2.0`. Keep Gradle `versionName`,
`ApiConfig.APP_VERSION`, `APP_VERSION`, and `packages/contracts/openapi.yaml`
aligned.

Current contents:

- `app/src/main/java/com/palmeiras/agenda/ApiConfig.kt` - shared Web product URL
- `app/src/main/java/com/palmeiras/agenda/MainActivity.kt` - secure WebView shell
- `app/src/main/java/com/palmeiras/agenda/NativeNavigation.kt` - bottom navigation
- `app/src/main/java/com/palmeiras/agenda/NativeSettingsView.kt` - native settings
- `app/src/main/res/mipmap-*` - generated Campo marcado launcher icons

Build the debug application with the checked-in Gradle wrapper:

```bash
./gradlew :app:assembleDebug
```

## Google Play release

The Play release targets Android 16 (API 36) and is distributed as an Android
App Bundle. Google Play App Signing should manage the production signing key;
the local keystore is the replaceable upload key.

1. Copy `keystore.properties.example` to `keystore.properties`.
2. Create or restore the upload keystore referenced by `storeFile`.
3. Keep the keystore and passwords outside version control and back them up.
4. Build and validate the signed bundle:

```bash
./gradlew :app:lintRelease :app:testReleaseUnitTest :app:bundleRelease
```

The upload artifact is written to
`app/build/outputs/bundle/release/app-release.aab`.

Refresh launcher icons from the shared brand source with:

```bash
scripts/export-brand-assets.py
```
