# Google Play release — Palmeiras Agenda

## Release identity

- App name: `Palmeiras Agenda`
- Application ID: `com.palmeiras.agenda`
- Version code: `55`
- Version name: `1.2.0`
- Minimum Android: 8.0 / API 26
- Target Android: 16 / API 36
- Distribution artifact: signed Android App Bundle (`.aab`)
- Play App Signing: required; the local key is the replaceable upload key

The application ID cannot be changed after the first Play release. Confirm it
before creating the Play Console app.

## Club intellectual-property publication path

The owner selected the club-flag path. The product renders club flags in match
content while keeping the separate Campo marcado application identity.

The following safeguards must remain in place:

1. Keep club flags limited to factual match content; do not use them as the
   application icon or application mark.
2. Keep the independent/non-official disclosure visible in the product and
   listing.
3. Treat club names and artwork as a trademark/rights review item and review the final app
   name/listing for trademark and affiliation risk before submission.

Club flags can increase trademark/rights review risk. This is not a legal
opinion or a guarantee of approval.

Official policies:

- <https://support.google.com/googleplay/android-developer/answer/9888072>
- <https://support.google.com/googleplay/android-developer/answer/9888374>

## Signing and build

Never commit the upload keystore or its passwords. Back up the upload key in a
separate secure location.

```bash
cd apps/android
cp keystore.properties.example keystore.properties
# Create or restore keystore/palmeiras-agenda-upload.jks, then replace all
# placeholder values in keystore.properties.

JAVA_HOME=/opt/homebrew/opt/openjdk@17 \
ANDROID_HOME=/opt/homebrew/share/android-commandlinetools \
ANDROID_SDK_ROOT=/opt/homebrew/share/android-commandlinetools \
./gradlew :app:lintRelease :app:testReleaseUnitTest :app:bundleRelease
```

Upload artifact:

```text
apps/android/app/build/outputs/bundle/release/app-release.aab
```

`bundleRelease` fails deliberately when the upload key is missing, so an
unsigned bundle is not mistaken for a publishable release.

## Store listing draft (pt-BR)

Name (30-character limit):

```text
Palmeiras Agenda
```

Short description (80-character limit):

```text
Jogos, resultados, tabelas e calendário do Palmeiras em um só lugar.
```

Full description:

```text
Acompanhe a agenda do Palmeiras em uma experiência rápida e organizada.

• Próximos jogos e contagem regressiva
• Resultados de partidas encerradas
• Calendário mensal por competição
• Classificações e tabelas
• Notícias e links para fontes externas
• Atalhos para adicionar jogos ao calendário
• Tema claro, escuro ou conforme o sistema

O Palmeiras Agenda é um aplicativo independente. Salvo autorização formal
documentada, não é o aplicativo oficial da Sociedade Esportiva Palmeiras e
não representa afiliação, patrocínio ou endosso do clube.
```

Suggested category: `Sports`  
Contains ads: `No`  
App access: no login or restricted area  
Privacy policy: <https://palmeiras.rodrigolanna.com.br/privacy.html>  
Support page: <https://palmeiras.rodrigolanna.com.br/support.html>

The Play listing also requires a public support email supplied by the account
owner.

## Required graphics

- 512 × 512 PNG app icon: the current independent Palmeiras Agenda field mark
- 1024 × 500 feature graphic: still required
- At least two phone screenshots: Agenda plus one meaningful secondary screen
- Optional 7-inch and 10-inch tablet screenshots

Do not place unlicensed club crests in store graphics.

## Play Console declarations

Complete and verify all declarations against the production behavior:

- Data safety: no account, ads, analytics SDK, location, contacts, camera, or
  microphone; HTTPS hosting infrastructure can process IP address, timestamp,
  user agent, route, and error logs for security and operations.
- Privacy policy: public URL above and in-app link are both present.
- Content rating questionnaire.
- Target audience and content.
- Ads declaration (`No`).
- News declaration if Play classifies the external news section as a news app.
- App access (`All functionality is available without special access`).

If the developer account is a personal account created after November 13,
2023, production access requires a closed test with at least 12 opted-in
testers for 14 continuous days.

## Recommended rollout

1. Create the Play Console app and enable Play App Signing.
2. Upload the signed `.aab` to Internal testing.
3. Resolve Play pre-review checks and test on physical phones.
4. Complete the required closed test when the account is subject to it.
5. Submit production with managed publishing enabled.
6. After approval, roll out production and monitor Android vitals.
