"""Match metadata enrichment for Palmeiras venue fallbacks."""

from __future__ import annotations

from typing import Any

PALMEIRAS_HOME = 'Allianz Parque'

# Conservative usual-home-ground fallbacks for Palmeiras away fixtures.
# These are used only when the primary match payload does not provide a venue.
PALMEIRAS_AWAY_VENUES = {
    1765: 'Maracanã',                  # Fluminense
    1766: 'Arena MRV',                 # Atlético-MG
    1767: 'Arena do Grêmio',
    1768: 'Ligga Arena',               # Athletico-PR
    1770: 'Estádio Nilton Santos',
    1771: 'Mineirão',                  # Cruzeiro
    1772: 'Arena Condá',
    1776: 'MorumBIS',                  # São Paulo
    1777: 'Arena Fonte Nova',
    1779: 'Neo Química Arena',         # Corinthians
    1780: 'São Januário',
    1782: 'Barradão',
    1783: 'Maracanã',                  # Flamengo
    4241: 'Couto Pereira',
    4286: 'Nabi Abi Chedid',
    4287: 'Baenão',                    # Remo
    4364: 'Maião',                     # Mirassol
    6684: 'Beira-Rio',
    6685: 'Vila Belmiro',
}


def palmeiras_venue_fallback(home_team: dict[str, Any], away_team: dict[str, Any]) -> str:
    home_id = home_team.get('id')
    away_id = away_team.get('id')
    if home_id == 1769:
        return PALMEIRAS_HOME
    if away_id == 1769:
        return PALMEIRAS_AWAY_VENUES.get(home_id, '')
    return ''

