# SPEC.md - Palmeiras Dashboard v5

## Priority Fixes

### 1. Data Loading Issues
- Add skeleton loaders while data loads
- Show "Erro ao carregar" with retry button on API failure
- Display "Última atualização: X minutos atrás"

### 2. TV Channels Fix
- Change "HBO" → "SporTV"
- Add: "Paramount+", "Amazon Prime", "CazéTV"

### 3. UI Improvements
- Add team logos from API (crest field)
- Better spacing between cards
- Improve mobile responsiveness

### 4. Calendar Button
- Add prominent "📅 Assinar Calendário" button
- Link to: `https://palmeiras-web.vercel.app/api/calendar.ics`

### 5. Duplicate Calendar Button - FIX NOW
- Remove the duplicate "Adicionar ao Google Calendar" button from the hero section
- Keep only ONE button (in footer)

### 6. Team Logos - FIX NOW  
- Use m.homeTeam.crest and m.awayTeam.crest from API
- Add fallback to Palmeiras shield if no crest available

---

## Color Scheme (keep)
- Background: Dark (#121212)
- Primary: Palmeiras Green (#0D7A3D)
- Accent: Gold (#FFD700)

---

*Created by Athena - 2026-03-15*
