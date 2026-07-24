# Palmeiras Agenda Visual Identity

Palmeiras Agenda has its own application identity: **Campo marcado**, a minimalist calendar-page outline integrated with a football midfield line and center circle. Match content uses each club's own flag; this does not replace the application's identity.

## Sources of Truth

- Application mark: `apps/web/static/brand/palmeiras-agenda-mark.svg`
- Compact application mark: `apps/web/static/brand/palmeiras-agenda-mark-small.svg`
- Team flags: API/local crest assets rendered by the shared WebView

Do not replace the application identity with a club crest, and do not use Campo marcado as a team crest.

Current identity release: `v12` across Web, PWA, iOS, Android, and social previews.

## Platform Matrix

| Surface | Asset |
|---|---|
| Web header | Campo marcado SVG |
| Web team and match content | Club flag |
| Web favicon and PWA icons | Campo marcado `v12` exports on the Web header surface |
| Social preview | Campo marcado `palmeiras-agenda-social-card-v12.png` |
| iOS launcher icon | Campo marcado in `AppIcon.appiconset` |
| iOS header | `PalmeirasAgendaLogo.imageset` |
| Android launcher icon | Campo marcado legacy and adaptive resources |
| Android header | `drawable-nodpi/palmeiras_agenda_logo.png` |

## Icon Background and Safe Area

Installable application icons use the Web header surface—not a separate flat-green tile—as their full-canvas background. The exact Campo marcado artwork is enlarged within platform-safe margins and centered from its solid artwork bounds. Adaptive and maskable variants may use a smaller mark to remain safe under system masks, but Web/PWA, iOS, and Android must retain the same geometry, ivory linework, gold binding strokes, gradient, gold wash, and grid treatment.

## Mark Construction

The canonical mark uses a `128 × 128` grid: one open monoline calendar-page outline, two short gold binding strokes, one midfield line, one center circle, and one center point. It contains no letters, shield, penalty boxes, goals, effects, or shadows. Use the deep-green version on light surfaces and the ivory-and-gold reversed version on green or dark surfaces. The product thought is: “O jogo já está marcado.”

## Color Palette

| Token | Hex | Use |
|---|---|---|
| Green 950 | `#043522` | Deep backgrounds |
| Green 900 | `#06412B` | Header depth |
| Green 800 | `#075C3B` | Primary brand and app-icon background |
| Green 700 | `#0A7A4A` | Active states |
| Green 100 | `#E7F1E9` | Soft tint |
| Gold 500 | `#C99A3D` | Accent |
| Ivory | `#FFFDF3` | Warm light surface |
| Mist | `#F3F5EF` | Page background |
| Ink | `#10231A` | Primary text |

UI color tokens live in `apps/web/static/brand/tokens.json` and are mirrored by the native themes.

## Shared Green Surfaces

The Web header and match hero are the visual source of truth for native green containers. Web, iOS, and Android must share the gradient stops, gold wash, grid spacing, grid opacity, corner radius, and border opacity recorded under `surfaces` in `tokens.json`. Do not approximate these surfaces from only the primary green token.

## Product Design System v3.0

The product UI implements the Lovable “Campo marcado” system through `apps/web/static/css/design-system.css` and the native-owned navigation, settings, loading, error, and launch surfaces. The component rules are:

- Use a 4px spacing base with the `4, 8, 12, 16, 24, 32, 48` scale.
- Use 6px control, 8px card, and 12px modal radii. Pills are reserved for semantic status only.
- Use Ivory for warm cards, Mist for page backgrounds, Ink for primary text, deep green for authority, and Gold only as a restrained accent.
- Use DM Sans on Web/PWA with weights 400, 500, 700, and 900. Native chrome follows platform typography with the same hierarchy.
- Use 900 tabular figures for scores and performance data; use uppercase medium-weight captions for metadata.
- Use restrained elevation. Hierarchy comes primarily from typography, borders, spacing, and contrast.
- Use 1.5px monoline utility icons with square corners and straight terminals.
- Keep all interactive targets at least 44×44px, preserve a visible gold focus ring, and honor reduced-motion preferences.
- Treat a full-width match card as the atomic sports component across Home, tables, competitions, calendar details, and Copa 2026.

## Typography and Voice

Primary typeface: `DM Sans`, with system sans-serif fallbacks. Copy should remain short, tactical, and useful. Palmeiras Agenda is an independent product; do not imply it is an official club publication.

## Exporting and Verification

Run:

```bash
scripts/export-brand-assets.py
```

The exporter rasterizes the exact application SVG for Web/PWA, iOS, and Android application assets. It composes every launcher icon over the exact Web header surface and validates opaque launcher backgrounds plus the transparent Android adaptive foreground.

Matching-resolution Web, iOS, and Android app icons should have identical SHA-256 hashes. The Web application-mark raster and native header-logo files should also match exactly.

When icon filenames change, bump the Web manifest URL and service-worker cache version so installed PWAs discover the new identity.
