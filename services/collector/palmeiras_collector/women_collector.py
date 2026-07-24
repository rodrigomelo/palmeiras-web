"""Official CBF collector for Palmeiras Feminino fixtures and match events."""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote_plus
from zoneinfo import ZoneInfo

import requests

from . import MATCH_COLUMNS, get_supabase

CBF_COMPETITION_ID = os.environ.get("CBF_WOMEN_COMPETITION_ID", "1260614")
CBF_API_BASE = "https://www.cbf.com.br/api/cbf"
CBF_COMPETITION_URL = (
    "https://www.cbf.com.br/futebol-brasileiro/tabelas/"
    "campeonato-brasileiro/feminino-a1/2026"
)
PALMEIRAS_WOMEN_ID = 20002
SAO_PAULO_TZ = ZoneInfo("America/Sao_Paulo")
REQUEST_HEADERS = {
    "Accept": "application/json",
    "User-Agent": "PalmeirasAgenda/1.2 (+https://palmeiras.rodrigolanna.com.br)",
}
CBF_INTERMEDIATE_CA = (
    Path(__file__).resolve().parent
    / "certs"
    / "sectigo-public-server-authentication-ca-ov-r36.pem"
)


def _request(path, *, timeout=45):
    url = f"{CBF_API_BASE}{path}"
    try:
        response = requests.get(
            url,
            headers=REQUEST_HEADERS,
            timeout=timeout,
        )
        response.raise_for_status()
        return response.json()
    except requests.exceptions.SSLError:
        # CBF currently omits its direct Sectigo OV R36 intermediate. The
        # bundled AIA certificate is signature-verified against certifi's
        # trusted R46 root (SHA-256: 65:42:D1:76:BE:D5:0F:19:3C:0C:E2:97:
        # AE:44:EC:D8:A0:A8:6B:EC:2E:DE:68:27:69:34:40:59:B4:E7:85:30).
        # Hostname and certificate verification remain enabled.
        response = requests.get(
            url,
            headers=REQUEST_HEADERS,
            timeout=timeout,
            verify=str(CBF_INTERMEDIATE_CA),
        )
        response.raise_for_status()
        return response.json()


def _team_id(team) -> int | None:
    raw = team.get("id") if isinstance(team, dict) else None
    if raw:
        try:
            return int(raw)
        except (TypeError, ValueError):
            pass
    crest = str((team or {}).get("url_escudo") or "")
    match = re.search(r"/clubes/(\d+)/", crest)
    return int(match.group(1)) if match else None


def _team(team) -> dict:
    team = team or {}
    identifier = _team_id(team)
    name = str(team.get("nome") or "A definir").strip()
    return {
        "id": identifier,
        "name": name,
        "shortName": name,
        "tla": "PAL" if identifier == PALMEIRAS_WOMEN_ID else "",
        "crest": team.get("url_escudo") or (f"/static/crests/{identifier}.png" if identifier else ""),
        "sourceCrest": team.get("url_escudo") or "",
    }


def _score(value):
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def _fixture_datetime(game) -> datetime:
    date = str(game.get("data") or "").strip()
    hour = str(game.get("hora") or "00:00").strip() or "00:00"
    local = datetime.strptime(f"{date} {hour}", "%d/%m/%Y %H:%M")
    return local.replace(tzinfo=SAO_PAULO_TZ)


def _status(game, kickoff, now):
    home_score = _score((game.get("mandante") or {}).get("gols"))
    away_score = _score((game.get("visitante") or {}).get("gols"))
    if kickoff <= now <= kickoff + timedelta(hours=3):
        return "IN_PLAY"
    if home_score is not None and away_score is not None and now > kickoff:
        return "FINISHED"
    return "TIMED" if now < kickoff else "SCHEDULED"


def _minute(raw_minute, period) -> int | None:
    match = re.search(r"(\d{1,2})", str(raw_minute or ""))
    if not match:
        return None
    value = int(match.group(1))
    period_text = str(period or "").upper()
    if period_text in ("2", "TN2", "AC2"):
        value += 45
    return value


def _player_name(value) -> str:
    return re.sub(r"^\d+\s*-\s*", "", str(value or "")).strip()


def _events(game) -> list[dict]:
    events = []
    for penalty in game.get("penalidades") or []:
        result = str(penalty.get("resultado") or "").upper()
        penalty_type = str(penalty.get("tipo") or "").upper()
        if penalty_type == "GOL":
            event_type = "GOAL"
            label = f"Gol — {penalty.get('atleta_apelido') or penalty.get('atleta_nome') or 'Jogadora'}"
        elif "VERMELHO" in result:
            event_type = "RED_CARD"
            label = f"Cartão vermelho — {penalty.get('atleta_apelido') or penalty.get('atleta_nome') or 'Jogadora'}"
        elif "AMARELO" in result:
            event_type = "YELLOW_CARD"
            label = f"Cartão amarelo — {penalty.get('atleta_apelido') or penalty.get('atleta_nome') or 'Jogadora'}"
        else:
            continue
        events.append({
            "id": f"cbf-penalty-{penalty.get('id')}",
            "type": event_type,
            "label": label,
            "minute": _minute(penalty.get("minutos"), penalty.get("tempo_jogo")),
            "teamId": int(penalty["clube_id"]) if str(penalty.get("clube_id") or "").isdigit() else None,
            "player": penalty.get("atleta_apelido") or penalty.get("atleta_nome") or "",
        })

    for side in ("mandante", "visitante"):
        team = game.get(side) or {}
        athletes = {str(item.get("id")): item for item in team.get("atletas") or []}
        for index, change in enumerate(team.get("alteracoes") or []):
            player_out = athletes.get(str(change.get("codigo_jogador_saiu")), {})
            player_in = athletes.get(str(change.get("codigo_jogador_entrou")), {})
            in_name = _player_name(player_in.get("apelido") or player_in.get("nome"))
            out_name = _player_name(player_out.get("apelido") or player_out.get("nome"))
            events.append({
                "id": f"cbf-sub-{game.get('id_jogo')}-{side}-{index}",
                "type": "SUBSTITUTION",
                "label": f"Substituição — {in_name or 'Jogadora'} por {out_name or 'Jogadora'}",
                "minute": _minute(change.get("tempo_jogo"), change.get("tempo_subs")),
                "teamId": _team_id(team),
                "player": in_name,
            })
    return sorted(events, key=lambda item: (item.get("minute") is None, item.get("minute") or 999, item["id"]))


def _lineups(game) -> dict:
    result = {}
    for source_key, public_key in (("mandante", "home"), ("visitante", "away")):
        team = game.get(source_key) or {}
        players = []
        for athlete in team.get("atletas") or []:
            players.append({
                "id": int(athlete["id"]) if str(athlete.get("id") or "").isdigit() else None,
                "name": _player_name(athlete.get("apelido") or athlete.get("nome")),
                "shirt": athlete.get("numero_camisa"),
                "starter": str(athlete.get("entrou_jogando")).lower() == "true",
                "reserve": str(athlete.get("reserva")).lower() == "true",
                "goalkeeper": str(athlete.get("goleiro")).lower() == "true",
            })
        result[public_key] = players
    return result


def _detail_games(payload):
    result = {}
    for group in payload.get("jogos") or []:
        for game in group.get("jogo") or []:
            result[str(game.get("id_jogo"))] = game
    return result


def _all_fixtures(payload):
    for phase in (payload or {}).values():
        if not isinstance(phase, dict):
            continue
        for game in phase.get("jogos") or []:
            yield game


def _palmeiras_fixtures(payload):
    for game in _all_fixtures(payload):
        team_ids = (
            _team_id(game.get("mandante") or {}),
            _team_id(game.get("visitante") or {}),
        )
        if PALMEIRAS_WOMEN_ID in team_ids:
            yield game


def _record(game, *, detail=None, now=None) -> dict:
    now = now or datetime.now(SAO_PAULO_TZ)
    kickoff = _fixture_datetime(game)
    detail = detail or {}
    home_source = detail.get("mandante") or game.get("mandante") or {}
    away_source = detail.get("visitante") or game.get("visitante") or {}
    home = _team(home_source)
    away = _team(away_source)
    venue_parts = [
        str(detail.get("local") or game.get("estadio") or "").strip(),
        str(game.get("cidade") or "").strip(),
        str(game.get("uf") or "").strip(),
    ]
    venue = " - ".join(part for part in venue_parts if part and part != "- A Definir")
    events = _events(detail) if detail else []
    lineups = _lineups(detail) if detail else {}
    external_id = int(game.get("ref_jogo") or detail.get("id_jogo"))
    source_url = f"{CBF_COMPETITION_URL}?documento=Tabela+Detalhada"
    home_score = _score(home_source.get("gols"))
    away_score = _score(away_source.get("gols"))
    area = {
        "id": 76,
        "name": "Brazil",
        "code": "BRA",
        "teamScope": "women",
        "events": events,
        "lineups": lineups,
        "sourceUrl": source_url,
        "directionsUrl": f"https://www.google.com/maps/search/?api=1&query={quote_plus(venue)}" if venue else "",
        "ticketUrl": "https://www.ingressospalmeiras.com.br/" if home.get("id") == PALMEIRAS_WOMEN_ID else "",
        "documents": detail.get("documentos") or [],
        "provider": "CBF",
    }
    return {
        "external_id": external_id,
        "home_team": json.dumps(home, ensure_ascii=False),
        "away_team": json.dumps(away, ensure_ascii=False),
        "home_score": home_score,
        "away_score": away_score,
        "half_time_home": None,
        "half_time_away": None,
        "utc_date": kickoff.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
        "status": _status(game, kickoff, now),
        "competition": json.dumps({"id": int(CBF_COMPETITION_ID), "name": "Brasileiro Feminino A1", "code": "BFA1"}, ensure_ascii=False),
        "season": json.dumps({"id": int(CBF_COMPETITION_ID), "startDate": "2026-02-12", "endDate": "2026-10-04", "currentMatchday": int(game.get("rodada") or 0)}, ensure_ascii=False),
        "matchday": int(game.get("rodada") or 0),
        "stage": "1ª Fase",
        "venue": venue,
        "area": json.dumps(area, ensure_ascii=False),
        "referees": json.dumps(detail.get("arbitros") or [], ensure_ascii=False),
        "broadcast": str(game.get("transmissao") or "").strip(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


def _standings_records(fixtures) -> list[dict]:
    teams = {}
    form = {}
    for fixture in fixtures:
        for side in ("mandante", "visitante"):
            team = _team(fixture.get(side) or {})
            identifier = team.get("id")
            if not identifier:
                continue
            teams.setdefault(identifier, {
                "team": team,
                "played_games": 0,
                "won": 0,
                "drawn": 0,
                "lost": 0,
                "goals_for": 0,
                "goals_against": 0,
                "points": 0,
            })
            form.setdefault(identifier, [])

    for fixture in sorted(fixtures, key=_fixture_datetime):
        home = _team_id(fixture.get("mandante") or {})
        away = _team_id(fixture.get("visitante") or {})
        home_score = _score((fixture.get("mandante") or {}).get("gols"))
        away_score = _score((fixture.get("visitante") or {}).get("gols"))
        if not home or not away or home_score is None or away_score is None:
            continue
        home_row, away_row = teams[home], teams[away]
        home_row["played_games"] += 1
        away_row["played_games"] += 1
        home_row["goals_for"] += home_score
        home_row["goals_against"] += away_score
        away_row["goals_for"] += away_score
        away_row["goals_against"] += home_score
        if home_score > away_score:
            home_row["won"] += 1
            home_row["points"] += 3
            away_row["lost"] += 1
            form[home].append("W")
            form[away].append("L")
        elif home_score < away_score:
            away_row["won"] += 1
            away_row["points"] += 3
            home_row["lost"] += 1
            form[home].append("L")
            form[away].append("W")
        else:
            home_row["drawn"] += 1
            away_row["drawn"] += 1
            home_row["points"] += 1
            away_row["points"] += 1
            form[home].append("D")
            form[away].append("D")

    ordered = sorted(
        teams.items(),
        key=lambda item: (
            -item[1]["points"],
            -(item[1]["goals_for"] - item[1]["goals_against"]),
            -item[1]["goals_for"],
            -item[1]["won"],
            item[1]["team"]["name"],
        ),
    )
    now = datetime.now(timezone.utc).isoformat()
    records = []
    for position, (identifier, row) in enumerate(ordered, start=1):
        records.append({
            "competition": "BFA1",
            "position": position,
            "team": json.dumps(row["team"], ensure_ascii=False),
            "played_games": row["played_games"],
            "won": row["won"],
            "drawn": row["drawn"],
            "lost": row["lost"],
            "goals_for": row["goals_for"],
            "goals_against": row["goals_against"],
            "goal_difference": row["goals_for"] - row["goals_against"],
            "points": row["points"],
            "form": ",".join(form[identifier][-5:]),
            "updated_at": now,
        })
    return records


def collect_women_matches():
    """Upsert the complete CBF women schedule and enrich the active round."""
    client = get_supabase()
    if not client:
        raise RuntimeError("Missing Supabase credentials")
    schedule = _request(f"/jogos/tabela-detalhada/campeonato/{CBF_COMPETITION_ID}")
    competition_fixtures = list(_all_fixtures(schedule))
    fixtures = list(_palmeiras_fixtures(schedule))
    now = datetime.now(SAO_PAULO_TZ)

    rounds_to_enrich = set()
    for fixture in fixtures:
        kickoff = _fixture_datetime(fixture)
        if now - timedelta(days=3) <= kickoff <= now + timedelta(days=4):
            rounds_to_enrich.add(int(fixture.get("rodada") or 0))
    detail_by_id = {}
    for round_number in sorted(rounds_to_enrich):
        if round_number <= 0:
            continue
        detail_by_id.update(_detail_games(_request(
            f"/jogos/campeonato/{CBF_COMPETITION_ID}/rodada/{round_number}/fase"
        )))

    records = []
    for fixture in fixtures:
        identifier = str(fixture.get("ref_jogo") or "")
        record = _record(fixture, detail=detail_by_id.get(identifier), now=now)
        records.append({key: value for key, value in record.items() if key in MATCH_COLUMNS})
    if records:
        client.table("matches").upsert(records, on_conflict="external_id").execute()
    standings = _standings_records(competition_fixtures)
    client.table("standings").delete().eq("competition", "BFA1").execute()
    if standings:
        client.table("standings").insert(standings).execute()
    return len(records), f"standings={len(standings)}", f"enriched_rounds={','.join(map(str, sorted(rounds_to_enrich))) or 'none'}"
