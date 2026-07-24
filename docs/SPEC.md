# Futebol Agenda — Specification Document

> **Status:** Draft · **Date:** 2025-07-24 · **Author:** Vulcan (with Rodrigo)

## Project Overview

### Purpose

Transform the single-club "Palmeiras Agenda" into a **multi-club football agenda platform** —
"Futebol Agenda". Users authenticate, select the club they support from a growing list of Brazilian
clubs, and get the full match-day experience themed in their club's colors.

### Scope

**IN scope (Phase 1 — MVP multi-club):**
- Rebrand to "Futebol Agenda" (web + mobile apps)
- Authentication (user accounts — login/register)
- Club selector (choose from available clubs)
- Dynamic theming system (CSS custom properties per club)
- Corinthians as the second club (black theme)
- Data layer: filter matches/standings by selected club
- Per-user notification preferences (stored server-side, not just localStorage)

**OUT of scope (Phase 1):**
- Social features (comments, reactions, friends)
- Paid tiers / subscriptions
- Club-specific news collectors (each club uses the same football-data.org feed)
- Admin panel for club management

### Constraints
- **Performance**: Same or faster than current load times (<2s first contentful paint)
- **Backward compatibility**: Existing Palmeiras users must transition seamlessly (their club defaults to Palmeiras)
- **Mobile**: WebView apps must adapt to any club theme without a new binary build
- **Data source**: football-data.org API + CBF scraper — no per-club API needed
- **Cost**: Supabase free/low tier for auth + user prefs

---

## Architecture: Current State

### What exists today (Palmeiras Agenda)

| Layer | Current State | What Changes |
|-------|---------------|--------------|
| **Frontend** | Vanilla JS SPA, hardcoded Palmeiras green theme, hardcoded TEAM_ID=1769 | Dynamic theme + club-scoped data + auth UI |
| **config.js** | `TEAM_ID: 1769`, `COMP_NAMES`, `STADIUMS`, `getCrest()` — all Palmeiras-specific | Generalize: multi-club config registry |
| **CSS** | `:root { --brand: #075c3b; ... }` — hardcoded green | Dynamic `--brand` per club via data attribute or runtime CSS var injection |
| **API** | `TEAM_ID = 1769` hardcoded in `shared.py`, filters by Palmeiras | Accept `club_id` param, filter dynamically |
| **Supabase** | 3 tables (matches, standings, news) — no user data | Add: `users`, `user_preferences`, `clubs` tables |
| **Collector** | Scrapes Palmeiras matches only | Extend to scrape per-club (Corinthians = team 1779) |
| **Auth** | None (anonymous access) | Supabase Auth (email/password or OAuth) |
| **PWA** | Palmeiras branding (icons, colors, manifest) | Dynamic manifest + themed icons per club |
| **Mobile** | WebView loading production URL, native notification bridge | Same WebView + club theme flows through automatically |

### S.U.P.E.R Health Assessment (Current Architecture)

| Principle | Score | Issue |
|-----------|-------|-------|
| **S**ingle Purpose | 🟢 | Each module is well-scoped (collector, API, web) |
| **U**nidirectional | 🟢 | Data flows sources → collector → DB → API → frontend |
| **P**orts | 🟡 | API has no formal contract for `club_id` filtering yet |
| **E**nvironment-Agnostic | 🟡 | TEAM_ID hardcoded in 4+ places (config.js, shared.py, features.js) |
| **R**eplaceable | 🔴 | Palmeiras identity is deeply coupled — changing club requires 10+ file edits |

**Critical violation (R):** The club identity (Palmeiras) is hardcoded across:
1. `config.js` — TEAM_ID, stadium map, crest URLs
2. `styles.css` — `:root` brand colors
3. `features.js` — TEAM_IDS map, Palmeiras text strings
4. `shared.py` — TEAM_ID constant
5. `routes.py` — implicit Palmeiras filtering in every route
6. `index.html` — title, meta tags, SVG logo
7. `sw.js` — app shell + branding
8. `manifest.webmanifest` — name, icons, colors
9. iOS `AppConfiguration.swift` — app name, URL
10. Android `strings.xml` — app name

---

## Architecture: Target State

### Multi-Club Registry Pattern

```
┌─────────────────────────────────────────────┐
│              CLUB REGISTRY                   │
│  Source of truth for all club definitions    │
│  (JS + Python + DB all read from same spec)  │
└──────────────────┬──────────────────────────┘
                   │
         ┌─────────┼─────────┐
         ▼         ▼         ▼
   ┌──────────┐ ┌──────────┐ ┌──────────┐
   │ FRONTEND │ │   API    │ │ COLLECTOR│
   │ config + │ │ shared + │ │ per-club │
   │ theme    │ │ routes   │ │ scrapers │
   └──────────┘ └──────────┘ └──────────┘
```

### Club Definition Schema

```typescript
interface ClubDefinition {
  id: string;                    // "palmeiras", "corinthians"
  name: string;                  // "Palmeiras"
  fullName: string;              // "Sociedade Esportiva Palmeiras"
  footballDataId: number;        // 1769 (men)
  womenFootballDataId: number;   // 20002 (women, or null)
  cbfId: number;                 // CBF scraper ID
  shortCode: string;             // "PAL" / "COR"
  theme: {
    brand: string;               // "#075c3b" (Palmeiras green)
    brandStrong: string;         // "#043522"
    brandBright: string;         // "#0a7a4a"
    brandSoft: string;           // "#e7f1e9"
    gold: string;                 // "#c99a3d"
  };
  darkTheme: {
    brand: string;               // "#48b57a"
    brandStrong: string;         // "#06140f"
    brandBright: string;         // "#65d996"
    brandSoft: string;           // "#10251a"
    gold: string;                 // "#d8b560"
  };
  stadium: string;               // "Allianz Parque"
  crest: {                       // URL or local path
    svg: string;
    png192: string;
    png512: string;
  };
}
```

### Registered Clubs (Phase 1)

| Club | ID | football-data ID | Theme | Stadium |
|------|----|-----------------|-------|---------|
| Palmeiras | `palmeiras` | 1769 | Green `#075c3b` | Allianz Parque |
| Corinthians | `corinthians` | 1779 | Black `#1a1a1a` | Neo Química Arena |

### Database Changes (Supabase)

```sql
-- Clubs registry (mirrors the JS/Python registry)
CREATE TABLE clubs (
    id TEXT PRIMARY KEY,           -- "palmeiras", "corinthians"
    name TEXT NOT NULL,
    football_data_id INTEGER NOT NULL,
    women_football_data_id INTEGER,
    theme JSONB NOT NULL,          -- { brand, brandStrong, ... }
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- User accounts (Supabase Auth handles email/password)
-- auth.users is managed by Supabase

-- User preferences (per user × per club context)
CREATE TABLE user_preferences (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE,
    selected_club TEXT NOT NULL DEFAULT 'palmeiras',
    team_scope TEXT NOT NULL DEFAULT 'men', -- 'men' or 'women'
    spoiler_free BOOLEAN DEFAULT FALSE,
    theme_mode TEXT DEFAULT 'system', -- 'light' | 'dark' | 'system'
    -- Notification preferences
    notify_one_hour BOOLEAN DEFAULT FALSE,
    notify_kickoff BOOLEAN DEFAULT FALSE,
    notify_results BOOLEAN DEFAULT FALSE,
    notify_schedule_changes BOOLEAN DEFAULT TRUE,
    notify_live_events BOOLEAN DEFAULT FALSE,
    notify_news BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(user_id)
);
```

### Authentication Flow

```
User opens app
  ├─ Has session token? ──► Load preferences ──► Apply club theme ──► Show agenda
  └─ No session
       ├─ First time ──► Club selection screen ──► Register/Login ──► Save club
       └─ Returning ──► Login screen ──► Load saved club ──► Show agenda
```

### Theming Flow

```
1. User selects club (or loads saved preference)
2. JS reads club definition from registry
3. CSS custom properties injected at runtime:
   document.documentElement.style.setProperty('--brand', club.theme.brand)
4. All CSS using var(--brand) updates instantly
5. Logo, icons, manifest update dynamically
6. Theme persists in user_preferences (server-side) + localStorage (offline)
```

---

## Implementation Plan

### Phase 1: Club Registry + Theming (no auth yet)

**Goal:** App works for Palmeiras and Corinthians, club is selectable, theme changes.

#### Task 1.1: Create club registry (JS)
- Create `apps/web/static/js/clubs.js` — single source of truth for club definitions
- Palmeiras (existing values extracted from CSS) + Corinthians (black theme)
- Export `CLUBS` map, `getClub(id)`, `DEFAULT_CLUB_ID`

#### Task 1.2: Create club registry (Python)
- Create `services/api/palmeiras_api/clubs.py` — mirrors JS registry
- Same data structure, used by API routes and collector

#### Task 1.3: Dynamic CSS theming
- Replace hardcoded `:root` brand vars with runtime injection
- Keep `:root` as the "Palmeiras default" (backward compat)
- Add `applyClubTheme(clubId)` function in features.js
- Apply theme from `localStorage` on page load (before paint to avoid FOUC)

#### Task 1.4: Club selector UI
- New onboarding screen: pick your club (full-screen overlay on first visit)
- Header club badge: tappable to switch clubs
- Persist selection in `localStorage` + URL param `?club=corinthians`

#### Task 1.5: Generalize config.js
- Remove hardcoded TEAM_ID=1769
- Read from club registry: `CONFIG.TEAM_ID = CLUBS[selectedClubId].footballDataId`
- Stadium map becomes per-club
- Crest URLs become per-club

#### Task 1.6: Generalize API
- `shared.py`: replace `TEAM_ID = 1769` with `get_club_team_id(club_id)`
- All routes accept `club_id` param (default: "palmeiras" for backward compat)
- Filter matches/standings by club's football-data ID

#### Task 1.7: Rebrand web assets
- `index.html`: title, meta, app name → "Futebol Agenda"
- `manifest.webmanifest`: name, short_name → "Futebol Agenda"
- Logo: neutral "Futebol Agenda" lockup (no club badge)

### Phase 2: Authentication + User Preferences

#### Task 2.1: Supabase Auth integration
- Add Supabase JS client to frontend
- Login/Register screen (email/password)
- Session management (token in localStorage, refresh on load)
- Protected routes: preferences, notification settings

#### Task 2.2: Database migrations
- Create `clubs` table + seed data
- Create `user_preferences` table
- RLS policies: users read/write only their own preferences

#### Task 2.3: Preferences sync
- Replace `localStorage`-only prefs with server-synced prefs
- On login: load from Supabase → apply theme + prefs
- On change: save to localStorage immediately, sync to Supabase async
- Notification subscriptions stored server-side per user

#### Task 2.4: Auth UI
- Club selection screen (first visit or not logged in)
- Login/register modal
- Account section in Ajustes tab
- Logout button

### Phase 3: Collector Expansion

#### Task 3.1: Per-club collector
- Collector accepts `--club corinthians` flag
- Uses club registry to get football-data ID
- Scrapes/store matches for the specified club
- systemd timer runs for each active club

### Phase 4: Mobile App Updates

#### Task 4.1: Rebrand mobile apps
- App name: "Futebol Agenda" (iOS project.yml, Android strings.xml)
- Logo: neutral brand lockup
- WebView loads same URL, club theme flows through

#### Task 4.2: Native club selector (optional)
- Native onboarding: pick club → pass to WebView via URL param
- Persist club choice in native UserDefaults/SharedPreferences

---

## S.U.P.E.R Compliance Matrix (Target)

| Component | S | U | P | E | R |
|-----------|---|---|---|---|---|
| Club Registry (JS) | 🟢 | 🟢 | 🟢 | 🟢 | 🟢 |
| Club Registry (Python) | 🟢 | 🟢 | 🟢 | 🟢 | 🟢 |
| Dynamic Theming | 🟢 | 🟢 | 🟢 | 🟢 | 🟢 |
| Auth Module | 🟢 | 🟢 | 🟢 | 🟢 | 🟢 |
| Preferences Sync | 🟢 | 🟢 | 🟢 | 🟢 | 🟡 |
| Per-club Collector | 🟢 | 🟢 | 🟢 | 🟢 | 🟢 |

**Key improvement:** Club identity is no longer hardcoded — it's a registry-driven config.
Swapping/adding clubs becomes a single registry entry, zero code changes.

---

## Acceptance Criteria

| ID | Criterion | Verification |
|----|-----------|--------------|
| AC-001 | User can select Palmeiras or Corinthians on first visit | Manual: clear localStorage, open app, see club selector |
| AC-002 | Selecting Corinthians changes theme to black | Visual: all --brand elements become black/white |
| AC-003 | Theme persists across page reloads | Manual: select club, reload, theme maintained |
| AC-004 | Existing Palmeiras users transition seamlessly | Test: existing localStorage → defaults to Palmeiras, no regression |
| AC-005 | User can register and log in | Manual: register with email, receive session, reload maintains session |
| AC-006 | Preferences sync to server | Manual: change notification prefs, check Supabase user_preferences table |
| AC-007 | Data filters by selected club | API test: `?club=corinthians` returns Corinthians matches only |
| AC-008 | App name is "Futebol Agenda" | Visual: title, manifest, mobile app name |
| AC-009 | Mobile apps show correct theme | Manual: open iOS/Android app, club theme applies in WebView |
| AC-010 | Corinthians data populates correctly | Manual: select Corinthians, see fixtures, standings, calendar |

---

## Roadmap (Future Clubs)

| Club | ID | football-data ID | Theme Color | Priority |
|------|----|-----------------|-------------|----------|
| Palmeiras | palmeiras | 1769 | Green #075c3b | ✅ Done |
| Corinthians | corinthians | 1779 | Black #1a1a1a | Phase 1 |
| São Paulo | sao-paulo | 1765 | Red #c41e1e | Phase 2 |
| Santos | santos | 6685 | White/Black | Phase 2 |
| Flamengo | flamengo | 1783 | Red/Black | Phase 3 |
| Fluminense | fluminense | 1765 | Bordeaux #7a0026 | Phase 3 |
| Atlético-MG | atletico-mg | 1766 | Black/White | Phase 3 |
| Cruzeiro | cruzeiro | 1771 | Blue #1e3a8a | Phase 3 |

---

## Change Log

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 0.1 | 2025-07-24 | Vulcan | Initial draft — multi-club transformation spec |
