#!/usr/bin/env python3
"""Unit coverage for the official CBF women fixture split."""

import json

from services.collector.palmeiras_collector.women_collector import (
    PALMEIRAS_WOMEN_ID,
    _all_fixtures,
    _palmeiras_fixtures,
    _standings_records,
)


def _team(identifier, name):
    return {
        "id": identifier,
        "nome": name,
        "url_escudo": f"https://conteudo.cbf.com.br/clubes/{identifier}/escudo.jpg",
    }


def _fixture(identifier, home, away, home_goals, away_goals):
    return {
        "ref_jogo": identifier,
        "mandante": {**home, "gols": home_goals},
        "visitante": {**away, "gols": away_goals},
        "data": "01/03/2026",
        "hora": "18:00",
    }


def test_full_schedule_drives_standings_while_matches_stay_palmeiras_only():
    palmeiras = _team(PALMEIRAS_WOMEN_ID, "Palmeiras")
    corinthians = _team(20001, "Corinthians")
    sao_paulo = _team(20005, "São Paulo")
    payload = {
        "1ª Fase": {
            "jogos": [
                _fixture(1, palmeiras, corinthians, 2, 0),
                _fixture(2, sao_paulo, corinthians, 3, 1),
            ]
        }
    }

    all_fixtures = list(_all_fixtures(payload))
    palmeiras_fixtures = list(_palmeiras_fixtures(payload))
    standings = _standings_records(all_fixtures)

    assert len(all_fixtures) == 2
    assert [fixture["ref_jogo"] for fixture in palmeiras_fixtures] == [1]
    by_id = {json.loads(row["team"])["id"]: row for row in standings}
    assert by_id[PALMEIRAS_WOMEN_ID]["played_games"] == 1
    assert by_id[20001]["played_games"] == 2
    assert by_id[20005]["points"] == 3
