# Calendário Visual — SPEC

## Overview
Monthly visual calendar grid for Palmeiras matches. Replaces the iCal download link in the footer with an interactive full-page calendar tab.

## Competition Colors
| Competition | Color | CSS Variable |
|---|---|---|
| Brasileirão | 🟢 Green | `--comp-bsa: #006B3F` |
| Libertadores | 🟡 Gold | `--comp-cli: #DAA520` |
| Copa do Brasil | 🔵 Blue | `--comp-copa: #1E88E5` |
| Other | ⚪ White | `--comp-other: #9E9E9E` |

## Layout

### Grid (7 columns — Sun to Sat)
```
Sun  Mon  Tue  Wed  Thu  Fri  Sat
[day numbers with colored dots]
```

### Navigation Bar (top)
```
< [ Month Year ] >
```
- Left/right arrows navigate months
- Center shows "Month Year" (e.g., "Abril 2025")
- Portuguese locale

### Day Cell
- Day number (top-left)
- Up to 3 colored dots below (one per competition with matches)
- If >3 competitions, show "+N" badge
- "Today" highlighted with brand color ring
- Days outside current month shown muted (opacity 0.3)

### Expanded Day (tap interaction)
When a day with matches is tapped:
- A list expands BELOW the calendar grid (not inline)
- Shows all matches for that day with:
  - Time
  - Home/Away teams with crests
  - Competition badge (colored)
  - Status (SCHEDULED, FINISHED, IN_PLAY)
- Tap again to collapse

### Mobile
- Calendar grid fits screen width (no horizontal scroll)
- Expanded list scrolls vertically below grid
- Each day cell minimum 44px touch target

## API

### GET /api/v1/calendar_monthly?year=YYYY&month=MM

Response:
```json
{
  "year": 2025,
  "month": 4,
  "days": {
    "15": [
      {
        "utcDate": "2025-04-15T19:00:00Z",
        "status": "SCHEDULED",
        "competition": { "code": "BSA", "name": "Brasileirão" },
        "homeTeam": { "id": 1769, "name": "Palmeiras", "shortName": "Palmeiras", "crest": "..." },
        "awayTeam": { "id": 1776, "name": "São Paulo", "shortName": "São Paulo", "crest": "..." },
        "matchday": 5,
        "venue": "Allianz Parque",
        "broadcast": "Premiere"
      }
    ]
  }
}
```

## File Changes
- `services/api/palmeiras_api/routes.py` — shared endpoint implementation
- `api/calendar_monthly.py` — compatibility adapter
- `apps/web/index.html` — calendar UI
- `apps/web/static/css/styles.css` — calendar styles
- `apps/web/static/js/app.js` — calendar rendering logic

## Implementation Notes
- Uses existing Supabase matches table
- Reuses `CONFIG.BR_TZ` and `CONFIG.TEAM_ID`
- Competition dot colors defined in CSS vars for easy theming
- No external dependencies (vanilla JS)
