"""Route handlers for the Palmeiras Agenda backend API."""

import sys
from datetime import datetime, timezone, timedelta
from urllib.error import HTTPError
from urllib.parse import parse_qs

from .ical import render_calendar
from .shared import (
    APP_VERSION,
    BR_TZ,
    TEAM_ID,
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
    transform_match,
    transform_standing,
    upstream_status,
    validate_date,
    year_month_params,
)

JSON = "application/json; charset=utf-8"
TEXT = "text/plain; charset=utf-8"
ICS = "text/calendar; charset=utf-8"
Response = tuple[int, object, str, str]


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
    }


def route_matches(params) -> Response:
    """Return match rows in the public client contract."""
    try:
        status = params.get("status", [None])[0]
        statuses = parse_statuses(status)
        limit = int_param(params, "limit", 50, min_value=1, max_value=250)
        competition = optional_competition_param(params)
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
        fetch_limit = 600 if (competition or team_id) else max(limit * 3, 50)
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
        team_id = int_param(params, "team_id", TEAM_ID, min_value=1, max_value=999999)
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
        matches = [transform_match(row) for row in rows if _row_has_team(row, team_id)]

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
        return _json(200, {"year": year, "teamId": team_id, "competitions": competitions})
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
        data = supabase_get("news", select="*", order="collected_at.desc", limit=str(limit))
        return _json(200, {"news": data})
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
        for row in (row for row in rows if _row_belongs_to_calendar(row)):
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
        rows = supabase_get("matches", select="*", order="utc_date.asc", limit="500")
        matches = [row for row in rows if _row_belongs_to_calendar(row)]
        body = render_calendar(matches)
        return _text(200, body, content_type=ICS, cache_control="public, max-age=900")
    except HTTPError as error:
        print(f"[api.calendar] Supabase HTTP {error.code}", file=sys.stderr)
        return _text(upstream_status(error), "Calendar unavailable", cache_control="no-store")
    except Exception as error:
        print(f"[api.calendar] unexpected error: {type(error).__name__}", file=sys.stderr)
        return _text(500, "Calendar unavailable", cache_control="no-store")


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
    "/api/health": route_health,
    "/api/v1/health": route_health,
}


def dispatch_request(path, query="") -> Response | None:
    """Dispatch an HTTP request path/query to a route handler."""
    route = API_ROUTE_ALIASES.get(path)
    if route is None:
        return None
    params = parse_qs(query) if isinstance(query, str) else query
    return route(params)
