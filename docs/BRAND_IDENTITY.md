# Palmeiras Agenda Visual Identity

Palmeiras Agenda uses an original PA calendar mark. The brand is about match rhythm, performance, fixtures, and planning. It should feel tactical, organized, green, and unmistakably connected to football without using club crests as the app logo.

## Source Of Truth

The official logo source is:

`apps/web/static/brand/palmeiras-agenda-mark.svg`

Never replace the app logo or PWA icon with the Palmeiras crest, a team badge, a generic calendar icon, or a third-party asset. Team crests may appear only as match/team content, not as the product brand.

Current logo release: `v5` for app/web/mobile icon exports and `v7` for the social preview card. This release keeps the green holder inside the gold outline, removes the old white matte behind `PA`, and does not use the old arrow/fold artifact.

## Logo System

| Asset | Purpose |
|---|---|
| `palmeiras-agenda-mark.svg` | Primary transparent PA calendar logo |
| `palmeiras-agenda-mark-small.svg` | Simplified small-size mark for 16px to 64px contexts |
| `palmeiras-agenda-lockup.svg` | Horizontal logo plus product name |
| `palmeiras-agenda-wordmark.svg` | Product-name wordmark and positioning line |
| `palmeiras-agenda-mark-flat-dark.svg` | Flat variant for light backgrounds |
| `palmeiras-agenda-mark-flat-light.svg` | Flat variant for dark backgrounds |
| `palmeiras-agenda-social-card.svg` | Source for social previews |
| `apps/ios/PalmeirasAgenda/Assets.xcassets/AppIcon.appiconset` | Native iOS app icons generated from the PA mark |
| `apps/android/app/src/main/res/mipmap-*` | Native Android launcher icons generated from the PA mark |

The logo background must remain transparent. The mark itself may contain green, gold, ivory, and internal pitch/calendar shapes, but there should be no full-canvas backing rectangle.
The PA monogram should not sit on a separate white matte block; it should sit directly on the calendar/pitch artwork.
The green holder inside the gold outline is part of the mark and may be used in header, banner, icon, and social-card contexts.

## Clear Space

Keep clear space around the logo equal to at least one calendar binder width. In compact UI, avoid placing the mark closer than 8px to text or controls. Do not crop the mark or put it inside another shape unless the app shell already provides a fixed logo slot.

## Minimum Sizes

| Use | Minimum |
|---|---:|
| Header mark | 40px |
| PWA icon | 192px source |
| Favicon | Use the dedicated 16px or 32px PNG |
| Social card logo | 180px |

Use `palmeiras-agenda-mark-small.svg` for tiny raster exports. It has fewer pitch lines and a heavier PA monogram for legibility.

## Color Palette

| Token | Hex | Use |
|---|---|---|
| Green 950 | `#043522` | Deep brand green, dark text on light surfaces |
| Green 900 | `#06412B` | Header/background depth |
| Green 800 | `#075C3B` | Primary brand surface |
| Green 700 | `#0A7A4A` | Active states and highlights |
| Green 100 | `#E7F1E9` | Soft brand tint |
| Gold 500 | `#C99A3D` | Calendar trim and focus accent |
| Gold 600 | `#A97822` | Darker gold details |
| Ivory | `#FFFDF3` | Calendar paper and warm light surfaces |
| Mist | `#F3F5EF` | Page background |
| Ink | `#10231A` | Primary readable text |
| Blue 600 | `#2468A8` | Copa do Brasil/supporting competition color |
| Red 600 | `#B93B36` | Loss/error/live warnings |
| Olive 600 | `#6B7F32` | Paulista/supporting competition color |
| Violet 600 | `#8B3F68` | World Cup/supporting competition color |

Use green and ivory as the main identity colors. Gold is an accent, not a dominant background. Avoid replacing the palette with Palmeiras crest colors from external sources; use the tokens in `apps/web/static/brand/tokens.json`.

## Typography

Primary typeface: `DM Sans`

Fallback stack: `-apple-system, BlinkMacSystemFont, Segoe UI, sans-serif`

Use heavy weights for product naming and compact UI headings. Body and data labels should stay practical and readable. Avoid decorative or football-poster fonts in the app UI.

## Voice

Short, tactical, and useful:

- Agenda tática de jogos, desempenho e calendário
- Jogos, desempenho, calendário
- Próximos jogos
- Sequência
- Classificação

Avoid hype-led copy, overly broad club slogans, or anything that makes Palmeiras Agenda sound like an official club property.

## Do

- Use the PA calendar mark as the product logo.
- Keep the transparent background.
- Use the small mark for favicons and compact icons.
- Keep the PA monogram legible.
- Use green, gold, ivory, and pitch-line details consistently.
- Keep team crests limited to match/team content.

## Do Not

- Do not replace the logo with the Palmeiras crest.
- Do not add the old gold arrow/fold artifact back to the top-right of the mark.
- Do not put a full dark square behind the transparent mark.
- Do not stretch, rotate, recolor randomly, or crop the mark.
- Do not use low-resolution raster files as the source of truth.
- Do not create alternate monograms such as `SEP`, `P`, or generic calendar icons.

## Exporting Assets

Run this from the project root after editing any brand SVG:

```bash
scripts/export-brand-assets.py
```

The script regenerates:

- `palmeiras-agenda-icon-192.png`
- `palmeiras-agenda-icon-192-v5.png`
- `palmeiras-agenda-icon-512.png`
- `palmeiras-agenda-icon-512-v5.png`
- `palmeiras-agenda-favicon-16.png`
- `palmeiras-agenda-favicon-16-v5.png`
- `palmeiras-agenda-favicon-32.png`
- `palmeiras-agenda-favicon-32-v5.png`
- `palmeiras-agenda-favicon-64.png`
- `palmeiras-agenda-favicon.png`
- `palmeiras-agenda-favicon-v5.png`
- `palmeiras-agenda-apple-touch-icon-v5.png`
- `palmeiras-agenda-maskable-512-v5.png`
- `palmeiras-agenda-app-icon-1024-v5.png`
- `palmeiras-agenda-social-card-v7.png`
- root `/favicon.ico`
- legacy `/static/icon-192.png`, `/static/icon-512.png`, `/static/favicon.png`, and `/static/favicon.ico`
- native Android launcher icons in `apps/android/app/src/main/res/mipmap-*`
- native iOS app icons in `apps/ios/PalmeirasAgenda/Assets.xcassets/AppIcon.appiconset`

The script also checks transparent square exports so accidental background fills are caught immediately.

## Web App Wiring

Current production references:

- Header logo: `/static/brand/palmeiras-agenda-mark.svg?v=5`
- Favicons: `/favicon.ico`, `/static/brand/palmeiras-agenda-favicon-16-v5.png`, `/static/brand/palmeiras-agenda-favicon-32-v5.png`, `/static/brand/palmeiras-agenda-favicon-v5.png`
- Apple touch icon: `/static/brand/palmeiras-agenda-apple-touch-icon-v5.png`
- Manifest icons: `/static/brand/palmeiras-agenda-icon-192-v5.png`, `/static/brand/palmeiras-agenda-icon-512-v5.png`, `/static/brand/palmeiras-agenda-maskable-512-v5.png`
- Social preview: `/static/brand/palmeiras-agenda-social-card-v7.png`

When changing immutable static asset names or SVG sources used by the shell, bump `CACHE_NAME` in `apps/web/sw.js`.
