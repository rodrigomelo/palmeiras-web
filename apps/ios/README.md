# Palmeiras Agenda iOS

SwiftUI/WKWebView mobile shell for the responsive Palmeiras Agenda product.

The app loads the same production interface used by Web, PWA, and Android:

```text
https://palmeiras.rodrigolanna.com.br/
```

The shell owns platform integration only: a persistent native bottom menu,
notification and appearance settings, manual refresh, safe external navigation,
calendar downloads, loading/error recovery, and native launcher assets. All
product screens and backend calls remain in the shared responsive Web app.

Current contents:

- `PalmeirasAgendaApp.swift` - application entry point
- `AppRootView.swift` - native bottom navigation and Settings screen
- `WebAppView.swift` - secure WKWebView and navigation integration
- `AppConfiguration.swift` - shared Web product URL
- `Assets.xcassets/AppIcon.appiconset` - generated Campo marcado app icons

Current shared app/API version: `1.2.0`. Keep the Xcode target marketing
version and `AppConfiguration.appVersion` aligned with `APP_VERSION` and
`packages/contracts/openapi.yaml`.

The generated project uses automatic signing with development team
`HFP4P6VBWV`. If another developer builds the app on a physical device, replace
that value in `project.yml` with their Apple Developer team and regenerate the
project.

Generate the checked-in Xcode project after changing `project.yml`:

```bash
cd apps/ios
xcodegen generate
xcodebuild -project PalmeirasAgenda.xcodeproj -scheme PalmeirasAgenda \
  -sdk iphonesimulator -destination 'generic/platform=iOS Simulator' \
  CODE_SIGNING_ALLOWED=NO build
```

Refresh the app icon catalog from the shared brand source with:

```bash
scripts/export-brand-assets.py
```
