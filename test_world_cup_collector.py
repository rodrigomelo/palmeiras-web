#!/usr/bin/env python3
"""Regression tests for World Cup and scraper match transformations."""
import json
from datetime import datetime, timezone
from unittest import TestCase, main

from collectors import (
    _deterministic_external_id,
    _match_to_record,
    _sanitize_match_record,
)


class WorldCupCollectorTests(TestCase):
    def test_world_cup_match_uses_wc_code_and_preserves_team_flags(self):
        match = {
            'id': 537327,
            'utcDate': '2026-06-11T19:00:00Z',
            'status': 'TIMED',
            'matchday': 1,
            'stage': 'GROUP_STAGE',
            'area': {'id': 2267, 'name': 'World', 'code': 'INT'},
            'competition': {'id': 2000, 'name': 'FIFA World Cup', 'code': 'WC'},
            'season': {'id': 2398, 'startDate': '2026-06-11', 'endDate': '2026-07-19'},
            'homeTeam': {
                'id': 769,
                'name': 'Mexico',
                'shortName': 'Mexico',
                'tla': 'MEX',
                'crest': 'https://crests.football-data.org/769.svg',
            },
            'awayTeam': {
                'id': 774,
                'name': 'South Africa',
                'shortName': 'South Africa',
                'tla': 'RSA',
                'crest': 'https://crests.football-data.org/9396.svg',
            },
            'score': {'fullTime': {'home': None, 'away': None}, 'halfTime': {'home': None, 'away': None}},
            'referees': [],
        }

        record = _match_to_record(
            match,
            datetime.now(timezone.utc).isoformat(),
            cache_crests=False,
            broadcast='',
        )

        self.assertEqual(record['external_id'], 537327)
        self.assertEqual(json.loads(record['competition'])['code'], 'WC')
        self.assertEqual(json.loads(record['home_team'])['crest'], 'https://crests.football-data.org/769.svg')
        self.assertEqual(json.loads(record['away_team'])['crest'], 'https://crests.football-data.org/9396.svg')
        self.assertEqual(record['broadcast'], '')

    def test_scraper_records_keep_integer_ids_and_drop_collector_only_fields(self):
        external_id = _deterministic_external_id('COPA', 'Palmeiras', 'Jacuipense', '2026-05-13')
        record = {
            'external_id': external_id,
            'utc_date': '2026-05-13T00:00:00+00:00',
            'status': 'SCHEDULED',
            'source': 'google',
        }

        clean = _sanitize_match_record(record)

        self.assertIsInstance(external_id, int)
        self.assertNotIn('source', clean)
        self.assertEqual(clean['external_id'], external_id)


if __name__ == '__main__':
    main()
