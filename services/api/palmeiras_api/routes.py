"""Route handlers for the Palmeiras Agenda backend API."""

import re
import sys
from datetime import datetime, timedelta, timezone
from urllib.error import HTTPError
from urllib.parse import parse_qs

from services.collector.palmeiras_collector.crest_manager import (
    CRESTS_DIR,
    get_or_download_crest,
)

from .ical import render_calendar
from .shared import (
    APP_VERSION,
    BR_TZ,
    TEAM_ID,
    TEAM_IDS,
    WOMEN_TEAM_ID,
    RequestValidationError,
    calendar_match,
    competition_param,
    get_first,
    int_param,
    is_configured,
    month_window,
    normalize_competition_code,
    optional_competition_param,
    parse_json,
    parse_statuses,
    supabase_get,
    team_scope_param,
    transform_match,
    transform_standing,
    upstream_status,
    validate_date,
    year_month_params,
)

JSON = "application/json; charset=utf-8"
TEXT = "text/plain; charset=utf-8"
ICS = "text/calendar; charset=utf-8"
PNG = "image/png"
Response = tuple[int, object, str, str]
CBF_WOMEN_TEAM_IDS = {
    20001, 20002, 20005, 20007, 20008, 20011, 20013, 20014, 20016,
    20018, 20027, 20038, 20064, 59849, 59897, 60175, 61377, 62194,
}
BLOCKED_NEWS_SOURCES = {
    "facebook.com",
    "instagram.com",
    "threads.net",
    "tiktok.com",
    "twitter.com",
    "x.com",
    "youtube.com",
}


def _json(status, body, cache_control="public, max-age=300") -> Response:
    return status, body, JSON, cache_control


def _text(status, body, content_type=TEXT, cache_control="public, max-age=300") -> Response:
    return status, body, content_type, cache_control


def _safe_error(collection="matches", code="upstream_error"):
    return {collection: [], "error": code}


def _calendar_error(code="upstream_error"):
    return {"error": code, "days": {}}


def _competitions_error(code="upstream_error"):
    return {"competitions": [], "error": code}


def _public_news_items(rows, limit):
    """Keep malformed and social-only collector rows out of public clients."""
    items = []
    for row in rows or []:
        title = str(row.get("title") or "").strip()
        source = str(row.get("source") or "").strip().lower()
        url = str(row.get("url") or "").strip()
        if not url or len(title) < 15 or len(title) > 180:
            continue
        if source in BLOCKED_NEWS_SOURCES:
            continue
        items.append(row)
        if len(items) >= limit:
            break
    return items


def _exclusive_end_date(value):
    if not value:
        return None
    return (datetime.strptime(value, "%Y-%m-%d").date() + timedelta(days=1)).isoformat()


def _year_window(year):
    start = datetime(year, 1, 1, 0, 0, 0, tzinfo=BR_TZ)
    end = datetime(year + 1, 1, 1, 0, 0, 0, tzinfo=BR_TZ)
    return (
        start.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S"),
        end.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S"),
    )


def _row_competition_code(row):
    comp = parse_json(row.get("competition", "{}"))
    return normalize_competition_code(comp.get("code"))


def _row_has_team(row, team_id):
    home = parse_json(row.get("home_team", "{}"))
    away = parse_json(row.get("away_team", "{}"))
    return home.get("id") == team_id or away.get("id") == team_id


def _row_team_scope(row):
    area = parse_json(row.get("area", "{}"))
    explicit = str(area.get("teamScope") or area.get("team_scope") or "").lower()
    if explicit in ("men", "women"):
        return explicit
    if _row_has_team(row, WOMEN_TEAM_ID):
        return "women"
    if _row_has_team(row, TEAM_ID):
        return "men"
    return "other"


def _row_matches_scope(row, scope):
    return scope == "all" and _row_team_scope(row) in ("men", "women") or _row_team_scope(row) == scope


def _row_is_world_cup(row):
    return _row_competition_code(row) == "WC"


def _row_belongs_to_calendar(row):
    return _row_has_team(row, TEAM_ID) or _row_is_world_cup(row)


def _parse_iso_datetime(value):
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _data_freshness():
    now = datetime.now(timezone.utc)
    max_age = timedelta(hours=2)
    tables = {
        "matches": {"table": "matches", "field": "updated_at"},
        "standings": {"table": "standings", "field": "updated_at"},
        "news": {"table": "news", "field": "collected_at"},
    }
    status = "fresh"
    body = {"status": status, "max_age_minutes": round(max_age.total_seconds() / 60), "tables": {}}

    for name, config in tables.items():
        field = config["field"]
        rows = supabase_get(config["table"], select=field, order=f"{field}.desc", limit="1")
        latest_raw = rows[0].get(field) if rows else None
        latest = _parse_iso_datetime(latest_raw)
        age_minutes = round((now - latest).total_seconds() / 60) if latest else None
        table_status = "fresh" if age_minutes is not None and age_minutes <= body["max_age_minutes"] else "stale"
        if table_status != "fresh":
            status = "stale"
        body["tables"][name] = {
            "status": table_status,
            "latest_at": latest_raw,
            "age_minutes": age_minutes,
        }

    body["status"] = status
    return body


def _team_result(match, team_id):
    home_id = match["homeTeam"].get("id")
    away_id = match["awayTeam"].get("id")
    if home_id != team_id and away_id != team_id:
        return None

    home_score = match.get("homeScore")
    away_score = match.get("awayScore")
    if home_score is None or away_score is None:
        return None

    team_home = home_id == team_id
    goals_for = home_score if team_home else away_score
    goals_against = away_score if team_home else home_score

    if goals_for > goals_against:
        result = "W"
        points = 3
    elif goals_for < goals_against:
        result = "L"
        points = 0
    else:
        result = "D"
        points = 1

    return {
        "result": result,
        "points": points,
        "goalsFor": goals_for,
        "goalsAgainst": goals_against,
    }


def _compact_match(match):
    return {
        "id": match.get("id"),
        "utcDate": match.get("utcDate"),
        "status": match.get("status"),
        "matchday": match.get("matchday"),
        "stage": match.get("stage"),
        "venue": match.get("venue"),
        "broadcast": match.get("broadcast"),
        "homeTeam": match.get("homeTeam"),
        "awayTeam": match.get("awayTeam"),
        "competition": match.get("competition"),
        "score": match.get("score"),
        "homeScore": match.get("homeScore"),
        "awayScore": match.get("awayScore"),
        "teamScope": match.get("teamScope"),
        "events": match.get("events") or [],
        "ticketUrl": match.get("ticketUrl") or "",
        "directionsUrl": match.get("directionsUrl") or "",
    }


def route_matches(params) -> Response:
    """Return match rows in the public client contract."""
    try:
        status = params.get("status", [None])[0]
        statuses = parse_statuses(status)
        limit = int_param(params, "limit", 50, min_value=1, max_value=250)
        competition = optional_competition_param(params)
        team_scope = team_scope_param(params, optional=True)
        team_id = None
        if get_first(params, "team_id", None):
            team_id = int_param(params, "team_id", TEAM_ID, min_value=1, max_value=999999)
        from_date = params.get("from_date", [None])[0]
        from_date, date_error = validate_date(from_date)
        if date_error:
            raise RequestValidationError(date_error)
        to_date = params.get("to_date", [None])[0]
        to_date, date_error = validate_date(to_date, "to_date")
        if date_error:
            raise RequestValidationError(date_error)
    except RequestValidationError as error:
        return _json(400, _safe_error(code=str(error)), "no-store")

    if not is_configured():
        return _json(503, _safe_error(code="not_configured"), "no-store")

    try:
        finished_only = bool(statuses) and all(s in ("FINISHED", "PLAYING_TIME_FINISHED") for s in statuses)
        fetch_limit = 800 if (competition or team_id or team_scope) else max(limit * 3, 50)
        query_params = {
            "select": "*",
            "order": "utc_date.desc" if finished_only else "utc_date.asc",
            "limit": str(fetch_limit),
        }
        filters = []

        if statuses:
            if len(statuses) == 1:
                query_params["status"] = f"eq.{statuses[0]}"
            else:
                query_params["status"] = f'in.({",".join(statuses)})'
            if any(s in ("SCHEDULED", "TIMED", "IN_PLAY", "PAUSED") for s in statuses) and not from_date:
                from_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        if from_date:
            filters.append(("utc_date", f"gte.{from_date}"))
        if to_date:
            filters.append(("utc_date", f"lt.{_exclusive_end_date(to_date)}"))

        matches = supabase_get("matches", filters=filters, **query_params)
        if competition:
            matches = [m for m in matches if _row_competition_code(m) == competition]
        if team_id:
            matches = [m for m in matches if _row_has_team(m, team_id)]
        if team_scope:
            matches = [m for m in matches if _row_matches_scope(m, team_scope)]
        if finished_only:
            matches.sort(key=lambda x: x.get("utc_date", ""), reverse=True)
        matches = matches[:limit]
        return _json(200, {"matches": [transform_match(m) for m in matches]})
    except HTTPError as error:
        print(f"[api.matches] Supabase HTTP {error.code}", file=sys.stderr)
        return _json(upstream_status(error), _safe_error(code=f"supabase_{error.code}"), "no-store")
    except Exception as error:
        print(f"[api.matches] unexpected error: {type(error).__name__}", file=sys.stderr)
        return _json(500, _safe_error(code="internal_error"), "no-store")


def route_standings(params) -> Response:
    """Return league standings."""
    try:
        competition = competition_param(params)
        limit = int_param(params, "limit", 100, min_value=1, max_value=100)
    except RequestValidationError as error:
        return _json(400, _safe_error("standings", str(error)), "no-store")

    if not is_configured():
        return _json(503, _safe_error("standings", "not_configured"), "no-store")

    try:
        rows = supabase_get(
            "standings",
            select="*",
            competition=f"eq.{competition}",
            order="position.asc",
            limit=str(limit),
        )
        return _json(200, {"standings": [transform_standing(row) for row in rows]})
    except HTTPError as error:
        print(f"[api.standings] Supabase HTTP {error.code}", file=sys.stderr)
        return _json(upstream_status(error), _safe_error("standings", f"supabase_{error.code}"), "no-store")
    except Exception as error:
        print(f"[api.standings] unexpected error: {type(error).__name__}", file=sys.stderr)
        return _json(500, _safe_error("standings", "internal_error"), "no-store")


def route_competitions(params) -> Response:
    """Return Palmeiras competition summaries for a calendar year."""
    try:
        year = int_param(params, "year", datetime.now(BR_TZ).year, min_value=2020, max_value=2035)
        team_scope = team_scope_param(params, optional=True)
        default_team_id = TEAM_IDS.get(team_scope, TEAM_ID)
        team_id = int_param(params, "team_id", default_team_id, min_value=1, max_value=999999)
    except RequestValidationError as error:
        return _json(400, _competitions_error(str(error)), "no-store")

    if not is_configured():
        return _json(503, _competitions_error("not_configured"), "no-store")

    try:
        start_utc, end_utc = _year_window(year)
        rows = supabase_get(
            "matches",
            filters=[("utc_date", f"gte.{start_utc}"), ("utc_date", f"lt.{end_utc}")],
            select="*",
            order="utc_date.asc",
            limit="600",
        )
        matches = [
            transform_match(row)
            for row in rows
            if _row_has_team(row, team_id) and (not team_scope or _row_matches_scope(row, team_scope))
        ]

        standings_by_comp = {}
        try:
            standings_rows = supabase_get("standings", select="*", order="competition.asc,position.asc", limit="400")
            for row in standings_rows:
                standing = transform_standing(row)
                if standing.get("teamId") == team_id:
                    standings_by_comp[normalize_competition_code(row.get("competition"))] = standing
        except Exception as error:
            print(f"[api.competitions] standings summary warning: {type(error).__name__}", file=sys.stderr)

        summaries = {}
        now = datetime.now(timezone.utc)
        for match in matches:
            competition = match.get("competition") or {}
            code = normalize_competition_code(competition.get("code") or "OTHER") or "OTHER"
            name = competition.get("name") or code
            summary = summaries.setdefault(
                code,
                {
                    "code": code,
                    "name": name,
                    "year": year,
                    "totalMatches": 0,
                    "finished": 0,
                    "upcoming": 0,
                    "live": 0,
                    "record": {
                        "played": 0,
                        "wins": 0,
                        "draws": 0,
                        "losses": 0,
                        "goalsFor": 0,
                        "goalsAgainst": 0,
                        "goalDifference": 0,
                        "points": 0,
                    },
                    "nextMatch": None,
                    "lastMatch": None,
                    "currentStage": None,
                    "standing": standings_by_comp.get(code),
                },
            )

            summary["totalMatches"] += 1
            status = match.get("status")
            if status in ("IN_PLAY", "PAUSED"):
                summary["live"] += 1
            elif status in ("FINISHED", "PLAYING_TIME_FINISHED"):
                summary["finished"] += 1
            elif status in ("SCHEDULED", "TIMED"):
                summary["upcoming"] += 1

            result = _team_result(match, team_id)
            if result and status in ("FINISHED", "PLAYING_TIME_FINISHED", "IN_PLAY", "PAUSED"):
                record = summary["record"]
                record["played"] += 1
                record["goalsFor"] += result["goalsFor"]
                record["goalsAgainst"] += result["goalsAgainst"]
                record["goalDifference"] = record["goalsFor"] - record["goalsAgainst"]
                record["points"] += result["points"]
                if result["result"] == "W":
                    record["wins"] += 1
                elif result["result"] == "L":
                    record["losses"] += 1
                else:
                    record["draws"] += 1

            utc_date = match.get("utcDate")
            try:
                match_dt = datetime.fromisoformat(str(utc_date).replace("Z", "+00:00")) if utc_date else None
            except ValueError:
                match_dt = None

            compact = _compact_match(match)
            if status in ("IN_PLAY", "PAUSED") or (
                status in ("SCHEDULED", "TIMED") and match_dt and match_dt >= now - timedelta(hours=3)
            ):
                current_next = summary["nextMatch"]
                if not current_next or utc_date < current_next.get("utcDate", ""):
                    summary["nextMatch"] = compact

            if status in ("FINISHED", "PLAYING_TIME_FINISHED"):
                current_last = summary["lastMatch"]
                if not current_last or utc_date > current_last.get("utcDate", ""):
                    summary["lastMatch"] = compact

            if not summary["currentStage"] and match.get("stage"):
                summary["currentStage"] = match.get("stage")
            if summary["nextMatch"] and summary["nextMatch"].get("stage"):
                summary["currentStage"] = summary["nextMatch"].get("stage")
            elif summary["lastMatch"] and summary["lastMatch"].get("stage"):
                summary["currentStage"] = summary["lastMatch"].get("stage")

        competition_order = {"BSA": 0, "CLI": 1, "COPA": 2, "CPA": 3, "CAMPEONATO_PAULISTA": 3}
        competitions = sorted(
            summaries.values(),
            key=lambda item: (
                0 if item["live"] else 1,
                item["nextMatch"]["utcDate"] if item["nextMatch"] else "9999-12-31T00:00:00Z",
                competition_order.get(item["code"], 50),
                item["name"],
            ),
        )
        return _json(200, {
            "year": year,
            "teamId": team_id,
            "teamScope": team_scope or ("women" if team_id == WOMEN_TEAM_ID else "men"),
            "competitions": competitions,
        })
    except HTTPError as error:
        print(f"[api.competitions] Supabase HTTP {error.code}", file=sys.stderr)
        return _json(upstream_status(error), _competitions_error(f"supabase_{error.code}"), "no-store")
    except Exception as error:
        print(f"[api.competitions] unexpected error: {type(error).__name__}", file=sys.stderr)
        return _json(500, _competitions_error("internal_error"), "no-store")


def route_news(params) -> Response:
    """Return recent news."""
    try:
        limit = int_param(params, "limit", 20, min_value=1, max_value=50)
    except RequestValidationError as error:
        return _json(400, _safe_error("news", str(error)), "no-store")

    if not is_configured():
        return _json(503, _safe_error("news", "not_configured"), "no-store")

    try:
        rows = supabase_get("news", select="*", order="collected_at.desc", limit=str(limit * 3))
        return _json(200, {"news": _public_news_items(rows, limit)})
    except HTTPError as error:
        print(f"[api.news] Supabase HTTP {error.code}", file=sys.stderr)
        return _json(upstream_status(error), _safe_error("news", f"supabase_{error.code}"), "no-store")
    except Exception as error:
        print(f"[api.news] unexpected error: {type(error).__name__}", file=sys.stderr)
        return _json(500, _safe_error("news", "internal_error"), "no-store")


def route_calendar_monthly(params) -> Response:
    """Return matches grouped by local Sao Paulo calendar day."""
    try:
        year, month = year_month_params(params)
        team_scope = team_scope_param(params, optional=True)
    except RequestValidationError as error:
        return _json(400, _calendar_error(str(error)), "no-store")

    if not is_configured():
        return _json(503, _calendar_error("not_configured"), "no-store")

    try:
        start_utc, end_utc = month_window(year, month)
        rows = supabase_get(
            "matches",
            filters=[("utc_date", f"gte.{start_utc}"), ("utc_date", f"lt.{end_utc}")],
            select="*",
            order="utc_date.asc",
            limit="250",
        )

        days = {}
        eligible_rows = (
            row for row in rows
            if _row_matches_scope(row, team_scope) if team_scope
        ) if team_scope else (row for row in rows if _row_belongs_to_calendar(row))
        for row in eligible_rows:
            utc_date = row.get("utc_date")
            if not utc_date:
                continue
            try:
                dt = datetime.fromisoformat(utc_date.replace("Z", "+00:00")).astimezone(BR_TZ)
            except ValueError:
                continue
            if dt.year != year or dt.month != month:
                continue
            days.setdefault(dt.strftime("%Y-%m-%d"), []).append(calendar_match(row))

        return _json(200, {"year": year, "month": month, "days": days}, "public, max-age=900")
    except HTTPError as error:
        print(f"[api.calendar_monthly] Supabase HTTP {error.code}", file=sys.stderr)
        return _json(upstream_status(error), _calendar_error(f"supabase_{error.code}"), "no-store")
    except Exception as error:
        print(f"[api.calendar_monthly] unexpected error: {type(error).__name__}", file=sys.stderr)
        return _json(500, _calendar_error("internal_error"), "no-store")


def route_calendar(params) -> Response:
    """Return an iCalendar feed."""
    if not is_configured():
        return _text(503, "Calendar unavailable", cache_control="no-store")

    try:
        team_scope = team_scope_param(params, optional=True)
        rows = supabase_get("matches", select="*", order="utc_date.asc", limit="500")
        matches = [
            row for row in rows
            if _row_matches_scope(row, team_scope) if team_scope
        ] if team_scope else [row for row in rows if _row_belongs_to_calendar(row)]
        body = render_calendar(matches)
        return _text(200, body, content_type=ICS, cache_control="public, max-age=900")
    except HTTPError as error:
        print(f"[api.calendar] Supabase HTTP {error.code}", file=sys.stderr)
        return _text(upstream_status(error), "Calendar unavailable", cache_control="no-store")
    except Exception as error:
        print(f"[api.calendar] unexpected error: {type(error).__name__}", file=sys.stderr)
        return _text(500, "Calendar unavailable", cache_control="no-store")


def _history_payload(rows, *, scope, team_id, opponent_id=None, limit=250):
    matches = []
    for row in rows:
        if not _row_has_team(row, team_id) or not _row_matches_scope(row, scope):
            continue
        match = transform_match(row)
        if match.get("status") not in ("FINISHED", "PLAYING_TIME_FINISHED"):
            continue
        home_id = match["homeTeam"].get("id")
        away_id = match["awayTeam"].get("id")
        current_opponent = away_id if home_id == team_id else home_id
        if opponent_id and current_opponent != opponent_id:
            continue
        matches.append(match)

    matches.sort(key=lambda item: item.get("utcDate") or "", reverse=True)
    matches = matches[:limit]
    record = {
        "played": 0,
        "wins": 0,
        "draws": 0,
        "losses": 0,
        "goalsFor": 0,
        "goalsAgainst": 0,
        "goalDifference": 0,
    }
    seasons = {}
    opponents = {}
    form = []
    for match in matches:
        result = _team_result(match, team_id)
        if not result:
            continue
        record["played"] += 1
        record["goalsFor"] += result["goalsFor"]
        record["goalsAgainst"] += result["goalsAgainst"]
        record["goalDifference"] = record["goalsFor"] - record["goalsAgainst"]
        result_key = {"W": "wins", "D": "draws", "L": "losses"}[result["result"]]
        record[result_key] += 1
        if len(form) < 8:
            form.append(result["result"])

        date = _parse_iso_datetime(match.get("utcDate"))
        year = str(date.astimezone(BR_TZ).year if date else "—")
        season = seasons.setdefault(year, {"year": year, "played": 0, "wins": 0, "draws": 0, "losses": 0})
        season["played"] += 1
        season[result_key] += 1

        home = match["homeTeam"]
        away = match["awayTeam"]
        opponent = away if home.get("id") == team_id else home
        opponent_key = str(opponent.get("id") or opponent.get("name"))
        opponent_row = opponents.setdefault(opponent_key, {
            "id": opponent.get("id"),
            "name": opponent.get("name"),
            "shortName": opponent.get("shortName"),
            "crest": opponent.get("crest"),
            "played": 0,
            "wins": 0,
            "draws": 0,
            "losses": 0,
        })
        opponent_row["played"] += 1
        opponent_row[result_key] += 1

    return {
        "teamScope": scope,
        "teamId": team_id,
        "opponentId": opponent_id,
        "record": record,
        "form": form,
        "seasons": sorted(seasons.values(), key=lambda item: item["year"], reverse=True),
        "opponents": sorted(opponents.values(), key=lambda item: (-item["played"], item.get("name") or "")),
        "matches": [_compact_match(match) for match in matches],
    }


def route_history(params) -> Response:
    """Return the searchable historical archive and aggregate record."""
    try:
        scope = team_scope_param(params)
        if scope == "all":
            raise RequestValidationError("history requires men or women team_scope")
        team_id = TEAM_IDS[scope]
        opponent_id = None
        if get_first(params, "opponent_id", None):
            opponent_id = int_param(params, "opponent_id", 0, min_value=1, max_value=999999999)
        competition = optional_competition_param(params)
        from_year = int_param(params, "from_year", 2000, min_value=1900, max_value=2035)
        to_year = int_param(params, "to_year", datetime.now(BR_TZ).year, min_value=1900, max_value=2035)
        limit = int_param(params, "limit", 250, min_value=1, max_value=1000)
        if from_year > to_year:
            raise RequestValidationError("from_year must not exceed to_year")
    except RequestValidationError as error:
        return _json(400, {"error": str(error), "matches": []}, "no-store")

    if not is_configured():
        return _json(503, {"error": "not_configured", "matches": []}, "no-store")
    try:
        start_utc, _ = _year_window(from_year)
        _, end_utc = _year_window(to_year)
        rows = supabase_get(
            "matches",
            filters=[("utc_date", f"gte.{start_utc}"), ("utc_date", f"lt.{end_utc}")],
            select="*",
            order="utc_date.desc",
            limit="1400",
        )
        if competition:
            rows = [row for row in rows if _row_competition_code(row) == competition]
        return _json(200, _history_payload(
            rows,
            scope=scope,
            team_id=team_id,
            opponent_id=opponent_id,
            limit=limit,
        ), "public, max-age=900")
    except HTTPError as error:
        return _json(upstream_status(error), {"error": f"supabase_{error.code}", "matches": []}, "no-store")
    except Exception as error:
        print(f"[api.history] unexpected error: {type(error).__name__}", file=sys.stderr)
        return _json(500, {"error": "internal_error", "matches": []}, "no-store")


def route_h2h(params) -> Response:
    """Return the head-to-head record against one opponent."""
    if not get_first(params, "opponent_id", None):
        return _json(400, {"error": "opponent_id is required", "matches": []}, "no-store")
    return route_history({**params, "limit": [get_first(params, "limit", "20")]})


def route_match_detail(params) -> Response:
    """Return one match with its event feed and contextual head-to-head record."""
    match_id = str(get_first(params, "id", "") or "").strip()
    if not match_id or len(match_id) > 100 or not re.fullmatch(r"[A-Za-z0-9._:-]+", match_id):
        return _json(400, {"error": "invalid match id"}, "no-store")
    if not is_configured():
        return _json(503, {"error": "not_configured"}, "no-store")
    try:
        rows = supabase_get("matches", select="*", external_id=f"eq.{match_id}", limit="1")
        if not rows:
            return _json(404, {"error": "match_not_found"}, "no-store")
        match = transform_match(rows[0])
        scope = match.get("teamScope")
        team_id = TEAM_IDS.get(scope)
        opponent_id = None
        if team_id:
            opponent_id = (
                match["awayTeam"].get("id")
                if match["homeTeam"].get("id") == team_id
                else match["homeTeam"].get("id")
            )
        h2h = None
        if team_id and opponent_id:
            history_rows = supabase_get("matches", select="*", order="utc_date.desc", limit="1400")
            h2h = _history_payload(
                history_rows,
                scope=scope,
                team_id=team_id,
                opponent_id=opponent_id,
                limit=20,
            )
        return _json(200, {"match": match, "h2h": h2h})
    except HTTPError as error:
        return _json(upstream_status(error), {"error": f"supabase_{error.code}"}, "no-store")
    except Exception as error:
        print(f"[api.match] unexpected error: {type(error).__name__}", file=sys.stderr)
        return _json(500, {"error": "internal_error"}, "no-store")


def route_push_public_key(params) -> Response:
    """Return the VAPID application server key required by PushManager."""
    try:
        from .notifications import vapid_public_key

        return _json(200, {"publicKey": vapid_public_key()}, "public, max-age=86400")
    except Exception as error:
        print(f"[api.push.key] unexpected error: {type(error).__name__}", file=sys.stderr)
        return _json(503, {"error": "push_unavailable"}, "no-store")


def route_push_subscription(params, *, method="POST", body=None, context=None) -> Response:
    """Create, update, or delete a browser push subscription."""
    try:
        from .notifications import (
            SubscriptionValidationError,
            remove_subscription,
            save_subscription,
        )

        if method == "DELETE":
            result = remove_subscription(body or {})
            return _json(200, result, "no-store")
        if method != "POST":
            return _json(405, {"error": "method_not_allowed"}, "no-store")
        result = save_subscription(
            body or {},
            user_agent=(context or {}).get("user_agent", ""),
        )
        return _json(201, result, "no-store")
    except SubscriptionValidationError as error:
        return _json(400, {"error": str(error)}, "no-store")
    except Exception as error:
        print(f"[api.push.subscription] unexpected error: {type(error).__name__}", file=sys.stderr)
        return _json(500, {"error": "subscription_failed"}, "no-store")


def route_health(params) -> Response:
    """Return backend health and current API version."""
    start = datetime.now(timezone.utc)
    supabase_status = "disconnected"
    latency_ms = 0
    freshness = {"status": "unknown", "tables": {}}

    if is_configured():
        try:
            supabase_get("matches", select="id", limit="1")
            freshness = _data_freshness()
            elapsed = (datetime.now(timezone.utc) - start).total_seconds() * 1000
            supabase_status = "connected"
            latency_ms = round(elapsed)
        except HTTPError as error:
            print(f"[api.health] Supabase HTTP {error.code}", file=sys.stderr)
            supabase_status = "error"
        except Exception as error:
            print(f"[api.health] unexpected error: {type(error).__name__}", file=sys.stderr)
            supabase_status = "error"

    status_code = 200 if supabase_status == "connected" else 503
    health_status = (
        "ok"
        if supabase_status == "connected" and freshness.get("status") == "fresh"
        else "degraded"
    )
    body = {
        "status": health_status,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "services": {
            "supabase": {
                "status": supabase_status,
                "latency_ms": latency_ms,
            },
            "data_freshness": freshness,
        },
        "version": APP_VERSION,
    }
    return _json(status_code, body, "no-store")


def route_crest(params) -> Response:
    """Return a transparent, locally cached PNG for a known CBF women club."""
    try:
        team_id = int_param(params, "team_id", 0, min_value=1, max_value=999999)
    except RequestValidationError:
        return _json(400, {"error": "invalid team_id"}, "no-store")
    if team_id not in CBF_WOMEN_TEAM_IDS:
        return _json(400, {"error": "invalid team_id"}, "no-store")

    source_url = f"https://conteudo.cbf.com.br/clubes/{team_id}/escudo.jpg"
    local_url = get_or_download_crest(team_id, source_url)
    if not local_url:
        return _json(502, {"error": "crest_unavailable"}, "public, max-age=60")

    crest_path = CRESTS_DIR / f"{team_id}.png"
    try:
        return 200, crest_path.read_bytes(), PNG, "public, max-age=604800, immutable"
    except OSError:
        return _json(502, {"error": "crest_unavailable"}, "public, max-age=60")


API_ROUTE_ALIASES = {
    "/api/matches": route_matches,
    "/api/v1/matches": route_matches,
    "/api/standings": route_standings,
    "/api/v1/standings": route_standings,
    "/api/competitions": route_competitions,
    "/api/v1/competitions": route_competitions,
    "/api/news": route_news,
    "/api/v1/news": route_news,
    "/api/calendar_monthly": route_calendar_monthly,
    "/api/v1/calendar_monthly": route_calendar_monthly,
    "/api/calendar.ics": route_calendar,
    "/api/calendar": route_calendar,
    "/api/v1/calendar.ics": route_calendar,
    "/api/v1/calendar": route_calendar,
    "/api/history": route_history,
    "/api/v1/history": route_history,
    "/api/h2h": route_h2h,
    "/api/v1/h2h": route_h2h,
    "/api/match": route_match_detail,
    "/api/v1/match": route_match_detail,
    "/api/push/public-key": route_push_public_key,
    "/api/v1/push/public-key": route_push_public_key,
    "/api/push/subscriptions": route_push_subscription,
    "/api/v1/push/subscriptions": route_push_subscription,
    "/api/health": route_health,
    "/api/v1/health": route_health,
    "/api/crest": route_crest,
    "/api/v1/crest": route_crest,
}


def dispatch_request(path, query="", *, method="GET", body=None, context=None) -> Response | None:
    """Dispatch an HTTP request path/query to a route handler."""
    route = API_ROUTE_ALIASES.get(path)
    if route is None:
        return None
    params = parse_qs(query) if isinstance(query, str) else query
    if route is route_push_subscription:
        return route(params, method=method, body=body, context=context)
    if method not in ("GET", "HEAD"):
        return _json(405, {"error": "method_not_allowed"}, "no-store")
    return route(params)
