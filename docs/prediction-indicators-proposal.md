# Palmeiras Web — Prediction Indicators Proposal

**Date:** 2026-04-05  
**Author:** Olympian Team (Atlas orchestrating: Artemis, Poseidon, Athena)  
**Status:** Research Complete — Awaiting Rodrigo's Decision

---

## Executive Summary

Rodrigo requested improvements to the Palmeiras Web data layer with a focus on **prediction indicators**. This document consolidates research from the Olympian team and proposes a phased implementation roadmap.

**Key Finding:** The cron job feeding data is currently broken. This needs to be fixed first before any new indicators can be properly displayed.

---

## Current State

### What's Working
- ✅ API endpoint (`/api/standings`) serves fresh data on request
- ✅ football-data.org integration (matches, standings, odds)
- ✅ News scraping (ge.globo, lance.com.br)
- ✅ Supabase storage (matches, standings, news tables)

### What's Broken
- ❌ **Cron job** (`palmeiras-data-collector`) — broken, status: error
  - Error: "Discord recipient is required" — misconfigured delivery channel
  - Last successful data fetch: **2026-03-24** (10+ days ago)
  - This means the data in the DB is stale

### What's Missing (Data Gaps)
1. **No xG data** — football-data.org free tier doesn't provide it
2. **No H2H precomputed** — head-to-head records require per-query scanning
3. **No rolling team metrics** — win rate home/away, avg goals, clean sheet %
4. **No historical standings** — standings table is delete+insert, no history
5. **No match-level stats enrichment** — corners, shots, fouls not stored

---

## Indicator Roadmap

### Phase 0 — Fix the Cron (PREREQUISITE)
| Task | Effort | Owner |
|------|--------|-------|
| Fix `palmeiras-data-collector` cron delivery channel | 30 min | Hefesto |

### Phase 1 — Zero Effort (Data Already Available)
Uses existing API data — no new sources or schema changes needed.

| Indicator | Source | Display Idea | Priority |
|-----------|--------|--------------|----------|
| Win probability | Odds implícitas (já na API) | Barra visual 3-segmentos | ⭐⭐⭐⭐⭐ |
| Form guide | `form` field ("WWDLW") | Badge com cores + arrow | ⭐⭐⭐⭐⭐ |
| Head-to-head | matches table (scan) | "Palmeiras 4-1-2 nos últimos 7" | ⭐⭐⭐⭐ |
| Home/Away performance | extend collector | Stat card "Casa: 80% vitórias" | ⭐⭐⭐ |

### Phase 2 — Low Effort (1-3 days work)
| Indicator | Source | Effort | Owner |
|-----------|--------|--------|--------|
| xG (Expected Goals) | Understat scraper (free tier first) | 2-3 days | Artemis |

**xG Source Priority:**
| Source | Reliability | Cost | Notes |
|--------|-------------|------|-------|
| Understat freemium | 🟡 Medium | Free | Test first — if breaks, switch |
| API-Football paid | ✅ High | ~$20/month | Fallback if Understat unstable |
| football-data.org | 🟡 Medium | Free tier limited | Already using — limited for xG |
| fbref.com | 🟡 Medium | Free | Scraping required, may break |

**Pragmatic path:** Test Understat free tier → if reliable, expand → if unstable, switch to API-Football paid.
*Recommendation: Don't pay until we validate the data is valuable.*
| Home/Away split | Extend collector | 1 day | Hefesto |
| Corner predictions | football-data stats | 1 day | Hefesto |
| Momentum calculated | Compute from matches | 1 day | Poseidon |

### Phase 3 — Medium Effort (1+ weeks)
Requires schema changes and/or new data sources.

| Indicator | Source | Effort | Notes |
|-----------|--------|--------|-------|
| xG via paid API | API-Football ($15-30/mês) | 1 week | More reliable than scraper |
| Injuries/Suspensions | Scraping | Complex | Fragile, may break often |
| Team strength ratings | Computed | 1 week | For Poisson prediction model |
| Standings history | New table + trigger | 1 week | Track position changes over time |

---

## Proposed UI/UX (Athena's Recommendations)

### Top 5 Indicator Concepts (Priority Order)

**1. 🎯 Win Probability Bars** — PRIORITY 1
- Three-segment mini progress bar on match cards (Home / Draw / Away)
- Visual weight proportional to probability
- Green (Palmeiras win), Gray (draw), Red (opponent)
- Source: odds implícitas from football-data

**2. 📈 Form Trend + Momentum Arrow** — PRIORITY 1
- Extend existing `.form-badge` into "momentum widget"
- Last 5 results as colored badges + arrow (↗️ hot, → stable, ↘️ cold)
- On Hero card and standings rows
- Source: `form` field in standings table

**3. 🏆 Confidence Badge** — PRIORITY 2
- Single word label: 🔴 Arriscado / 🟡 Possível / 🟢 Provável
- Based on probability thresholds (>70% = Provável, etc.)
- Replaces raw numbers on Palpites tab

**4. 📊 xG Comparison Widget** — PRIORITY 2
- "xG: 1.8 vs 0.9" on Hero card back
- Average xG for/against displayed per team
- Source: Understat scraper

**5. ↗️↘️ Position Change Arrows** — PRIORITY 3
- Micro-arrows on classification rows showing trajectory
- Requires standings history (Phase 3)

### ⚠️ UX Safeguards
- **Progressive disclosure** — indicators hidden by default, shown on tap/expand
- **One new thing per section** — ship incrementally, measure impact
- **"Modo Avançado" toggle** — casual fans see clean view, engaged fans opt-in to details
- **Disclaimer** — small note: "Estimativas baseadas em dados — não são garantias"

---

## Data Architecture (Poseidon's Recommendations)

### New Tables Needed

```sql
-- match_stats: enriches each match with computed metrics
CREATE TABLE match_stats (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    match_id UUID REFERENCES matches(id),
    home_xg FLOAT, away_xg FLOAT,
    home_win_probability FLOAT, draw_probability FLOAT, away_win_probability FLOAT,
    computed_at TIMESTAMPTZ DEFAULT NOW()
);

-- team_stats: rolling window metrics per team
CREATE TABLE team_stats (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    team_id INTEGER,
    competition VARCHAR(50),
    stat_type VARCHAR(20), -- 'overall', 'home', 'away'
    matches_played INTEGER DEFAULT 0,
    win_rate FLOAT, avg_goals_scored FLOAT, avg_xg FLOAT,
    window_matches INTEGER DEFAULT 10,
    computed_at TIMESTAMPTZ DEFAULT NOW()
);

-- h2h_records: precomputed head-to-head
CREATE TABLE h2h_records (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    team_a_id INTEGER, team_b_id INTEGER, competition VARCHAR(50),
    total_matches INTEGER DEFAULT 0,
    team_a_wins INTEGER DEFAULT 0, draws INTEGER DEFAULT 0, team_b_wins INTEGER DEFAULT 0,
    UNIQUE(team_a_id, team_b_id, competition)
);
```

### Prediction Model (MVP)
Simple Poisson model using:
- Home team avg goals (rolling 10-match window)
- Away team avg goals
- H2H historical goals
- Home advantage factor (~0.3 goals)

No ML framework needed — statistical model works fine for web display.

---

## Decision Required from Rodrigo

Please approve or adjust the following:

1. **Fix cron first?** Yes/No
2. **Start with Phase 1 indicators?** (odds + form + H2H — lowest effort, immediate value)
3. **Budget for xG?** Should we invest in paid API-Football tier or stick with Understat scraper?
4. **New tables?** Approve schema changes proposed by Poseidon?

---

## Team Assignments (When Approved)

| Agent | Role |
|-------|------|
| Hefesto | Implement indicators, fix cron, extend collectors |
| Poseidon | Schema changes, team_stats aggregation |
| Artemis | xG source validation, Understat scraper testing |
| Athena | UI implementation per phased roadmap |
| Apollo | QA and regression testing |

---

*Prepared by Atlas (Orchestrator) 🏔️*
*Olympian Team — Palmeiras Web Project*
