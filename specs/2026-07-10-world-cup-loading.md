# Bug Fix: World Cup 2026 Loading Failure

## Bug Report
- **ID**: BUG-2026-07-10-WC-LOAD
- **Severity**: High
- **Reproduction Steps**: Open the Palmeiras Agenda web app, select the Copa 2026 tab, and wait for the World Cup match list to load.
- **Expected Behavior**: The Copa 2026 tab loads FIFA World Cup 2026 matches from June 11, 2026 through July 19, 2026.
- **Actual Behavior**: The tab shows "Erro ao carregar a Copa 2026".

## Root Cause
The VPS backend rejects `competition=WC` because its competition allowlist does not include World Cup aliases. The same backend also defaults `/api/matches` to Palmeiras-only filtering, which would exclude all World Cup tournament rows even after accepting `WC`.

## Fix Plan
- Files to modify: `/var/www/palmeiras-web/api/_shared.py`, `/var/www/palmeiras-web/api/matches.py`
- Approach: Add World Cup competition aliases and only apply the Palmeiras `team_id` filter when the request explicitly provides `team_id`.
- Verification: Confirm the World Cup API endpoint returns rows, confirm the Copa 2026 tab renders match content, and confirm Palmeiras-specific queries still return Palmeiras matches when `team_id=1769` is provided.

## Acceptance Criteria
- **AC-001**: `GET /api/matches?competition=WC&from_date=2026-06-11&to_date=2026-07-19&limit=200` returns HTTP 200 with World Cup matches.
- **AC-002**: The Copa 2026 tab no longer renders "Erro ao carregar a Copa 2026".
- **AC-003**: Palmeiras-only match queries with `team_id=1769` still return Palmeiras matches.
- **AC-004**: Python API files compile and the `palmeiras-web` service restarts successfully.
