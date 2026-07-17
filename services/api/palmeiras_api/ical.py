"""iCalendar rendering for Palmeiras Agenda."""

from datetime import datetime, timezone, timedelta

from .shared import BR_TZ, TEAM_ID, parse_json

AWAY_STADIUMS = {
    1776: "Morumbi",
    1777: "Fonte Nova",
    1770: "Nilton Santos",
    1779: "Maracanã",
    1783: "Beira-Rio",
    1766: "Mineirão",
    1780: "Castelão",
    1765: "Arena MRV",
}


def fold_line(line):
    """Fold iCalendar lines to 75 octets-ish for client compatibility."""
    if not line:
        return ""
    result = []
    while len(line) > 75:
        result.append(line[:75])
        line = " " + line[75:]
    result.append(line)
    return "\r\n".join(result)


def escape_ics(text):
    """Escape text for an iCalendar property value."""
    if not text:
        return ""
    return (
        str(text)
        .replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\r", "")
        .replace("\n", "\\n")
    )


def render_calendar(matches):
    """Render Supabase match rows as a complete VCALENDAR string."""
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Palmeiras//Agenda//PT-BR",
        "X-WR-CALNAME:Palmeiras Agenda",
        "X-WR-TIMEZONE:America/Sao_Paulo",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        "BEGIN:VTIMEZONE",
        "TZID:America/Sao_Paulo",
        "BEGIN:STANDARD",
        "DTSTART:19700101T000000",
        "TZOFFSETFROM:-0300",
        "TZOFFSETTO:-0300",
        "TZNAME:BRT",
        "END:STANDARD",
        "END:VTIMEZONE",
    ]
    now = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    for match in matches:
        utc_date = match.get("utc_date")
        if not utc_date:
            continue
        try:
            dt = datetime.fromisoformat(utc_date.replace("Z", "+00:00")).astimezone(BR_TZ)
        except ValueError:
            continue

        home = parse_json(match.get("home_team", "{}"))
        away = parse_json(match.get("away_team", "{}"))
        comp = parse_json(match.get("competition", "{}"))
        referees = parse_json(match.get("referees", "[]"), [])

        home_name = home.get("name") or home.get("shortName") or "A definir"
        away_name = away.get("name") or away.get("shortName") or "A definir"
        is_home = home.get("id") == TEAM_ID
        status = match.get("status", "")
        home_score = match.get("home_score")
        away_score = match.get("away_score")

        venue = match.get("venue") or ("Allianz Parque" if is_home else AWAY_STADIUMS.get(home.get("id"), "A definir"))
        if status == "FINISHED" and home_score is not None and away_score is not None:
            summary = f"{home_name} {home_score} x {away_score} {away_name}"
        else:
            summary = f"{home_name} x {away_name}"

        desc_parts = []
        if comp.get("name"):
            desc_parts.append(f"Competição: {comp['name']}")
        if match.get("matchday"):
            desc_parts.append(f"Rodada: {match['matchday']}")
        if match.get("stage") and match.get("stage") != "REGULAR_SEASON":
            desc_parts.append(f"Fase: {match['stage']}")
        if venue:
            desc_parts.append(f"Estádio: {venue}")
        desc_parts.append(f"Transmissão: {match.get('broadcast') or 'A confirmar'}")
        if status == "FINISHED" and home_score is not None and away_score is not None:
            desc_parts.append(f"Placar: {home_score} x {away_score}")
            if match.get("half_time_home") is not None and match.get("half_time_away") is not None:
                desc_parts.append(f"Placar 1º tempo: {match['half_time_home']} x {match['half_time_away']}")
        ref_names = [r.get("name", "") for r in referees if isinstance(r, dict) and r.get("name")]
        if ref_names:
            desc_parts.append(f"Árbitros: {', '.join(ref_names)}")

        start = dt.strftime("%Y%m%dT%H%M%S")
        end = (dt + timedelta(hours=2)).strftime("%Y%m%dT%H%M%S")
        description = escape_ics("\n".join(desc_parts))
        lines.extend(
            [
                "BEGIN:VEVENT",
                f"UID:palmeiras-{escape_ics(match.get('external_id') or utc_date)}@agenda",
                f"DTSTAMP:{now}",
                f"DTSTART;TZID=America/Sao_Paulo:{start}",
                f"DTEND;TZID=America/Sao_Paulo:{end}",
                fold_line(f"SUMMARY:{escape_ics(summary)}"),
                fold_line(f"DESCRIPTION:{description}"),
            ]
        )
        if venue and venue != "A definir":
            lines.append(f"LOCATION:{escape_ics(venue)}")
        if comp.get("name"):
            lines.append(f"CATEGORIES:{escape_ics(comp['name'])}")
        lines.append("END:VEVENT")

    lines.append("END:VCALENDAR")
    return "\r\n".join(lines)
