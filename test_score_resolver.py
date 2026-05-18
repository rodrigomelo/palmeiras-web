#!/usr/bin/env python3
"""Regression tests for the score resolver safety checks."""
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase, main
from unittest.mock import patch

MODULE_PATH = Path(__file__).parent / 'collectors' / 'score_resolver.py'
SPEC = importlib.util.spec_from_file_location('score_resolver_under_test', MODULE_PATH)
score_resolver = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(score_resolver)


class GoogleSearchTests(TestCase):
    def setUp(self):
        self.match = {
            'external_id': 12345,
            'utc_date': '2026-05-18T22:30:00+00:00',
            'home_team': json.dumps({
                'id': 1769,
                'name': 'SE Palmeiras',
                'shortName': 'Palmeiras',
            }),
            'away_team': json.dumps({
                'id': 5,
                'name': 'SC Corinthians Paulista',
                'shortName': 'Corinthians',
            }),
            'competition': json.dumps({
                'code': 'BSA',
                'name': 'Campeonato Brasileiro Série A',
            }),
        }

    @patch('requests.get')
    def test_returns_score_only_when_date_and_competition_context_match(self, mock_get):
        mock_get.return_value = SimpleNamespace(
            status_code=200,
            text=(
                '<html>Brasileirão Série A 18/05/2026 '
                'Resultado final: Palmeiras 2 x 1 Corinthians</html>'
            ),
        )

        score = score_resolver.GoogleSearch().resolve_single(self.match)

        self.assertEqual(score, {'home_score': 2, 'away_score': 1})
        mock_get.assert_called_once()
        args, kwargs = mock_get.call_args
        self.assertEqual(args[0], 'https://www.google.com/search')
        self.assertIn('params', kwargs)
        self.assertIn('q', kwargs['params'])
        self.assertIn('18/05/2026', kwargs['params']['q'])
        self.assertIn('Campeonato Brasileiro Série A', kwargs['params']['q'])

    @patch('requests.get')
    def test_rejects_team_score_without_expected_date(self, mock_get):
        mock_get.return_value = SimpleNamespace(
            status_code=200,
            text='<html>Brasileirão Série A Palmeiras 2 x 1 Corinthians</html>',
        )

        score = score_resolver.GoogleSearch().resolve_single(self.match)

        self.assertIsNone(score)

    @patch('requests.get')
    def test_rejects_team_score_without_expected_competition(self, mock_get):
        mock_get.return_value = SimpleNamespace(
            status_code=200,
            text='<html>18/05/2026 Resultado final: Palmeiras 2 x 1 Corinthians Amistoso</html>',
        )

        score = score_resolver.GoogleSearch().resolve_single(self.match)

        self.assertIsNone(score)

    @patch('requests.get')
    def test_handles_swapped_team_order(self, mock_get):
        mock_get.return_value = SimpleNamespace(
            status_code=200,
            text=(
                '<html>Brasileirão Série A 18/05/2026 '
                'Encerrado: Corinthians 1 x 2 Palmeiras</html>'
            ),
        )

        score = score_resolver.GoogleSearch().resolve_single(self.match)

        self.assertEqual(score, {'home_score': 2, 'away_score': 1})

    @patch('requests.get')
    def test_rejects_yearless_date_as_ambiguous(self, mock_get):
        mock_get.return_value = SimpleNamespace(
            status_code=200,
            text=(
                '<html>Brasileirão Série A 18/05 Resultado final: '
                'Palmeiras 2 x 1 Corinthians</html>'
            ),
        )

        score = score_resolver.GoogleSearch().resolve_single(self.match)

        self.assertIsNone(score)

    @patch('requests.get')
    def test_rejects_score_without_final_signal(self, mock_get):
        mock_get.return_value = SimpleNamespace(
            status_code=200,
            text='<html>Brasileirão Série A 18/05/2026 Palmeiras 2 x 1 Corinthians</html>',
        )

        score = score_resolver.GoogleSearch().resolve_single(self.match)

        self.assertIsNone(score)

    @patch('requests.get')
    def test_rejects_context_from_neighboring_snippet(self, mock_get):
        mock_get.return_value = SimpleNamespace(
            status_code=200,
            text=(
                '<html>'
                '<div>Palmeiras 4 x 0 Corinthians</div>'
                '<div>Brasileirão Série A 18/05/2026 Resultado final: Santos 1 x 1 São Paulo</div>'
                '</html>'
            ),
        )

        score = score_resolver.GoogleSearch().resolve_single(self.match)

        self.assertIsNone(score)


if __name__ == '__main__':
    main()
