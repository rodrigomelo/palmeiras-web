"""Regression tests for public API validation and credential guardrails."""

import base64
import json
import os
import tempfile
from io import BytesIO
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch

from PIL import Image

from services.api.palmeiras_api import shared
from services.api.palmeiras_api.notifications import (
    remove_subscription,
    save_subscription,
)
from services.api.palmeiras_api.routes import (
    _history_payload,
    _public_news_items,
    route_crest,
    route_match_detail,
)
from services.collector.palmeiras_collector import crest_manager
from services.collector.palmeiras_collector.women_collector import _record


def _jwt_with_role(role):
    def encode(value):
        return base64.urlsafe_b64encode(json.dumps(value).encode("utf-8")).decode(
            "ascii"
        ).rstrip("=")

    return f"{encode({'alg': 'none'})}.{encode({'role': role})}.signature"


class PublicApiCredentialTests(TestCase):
    def test_rejects_service_role_jwt(self):
        self.assertFalse(shared.is_public_supabase_key(_jwt_with_role("service_role")))

    def test_rejects_new_secret_key_format(self):
        self.assertFalse(shared.is_public_supabase_key("sb_secret_example"))

    def test_accepts_anon_and_publishable_keys(self):
        self.assertTrue(shared.is_public_supabase_key(_jwt_with_role("anon")))
        self.assertTrue(shared.is_public_supabase_key("sb_publishable_example"))

    def test_configuration_requires_public_key_by_default(self):
        with patch.object(shared, "SUPABASE_URL", "https://example.supabase.co"), patch.object(
            shared, "ALLOW_SERVICE_ROLE_PUBLIC_API", False
        ):
            self.assertFalse(shared.is_configured(_jwt_with_role("service_role")))

    def test_configuration_requires_https(self):
        with patch.object(shared, "SUPABASE_URL", "http://example.supabase.co"), patch.object(
            shared, "ALLOW_SERVICE_ROLE_PUBLIC_API", False
        ):
            self.assertFalse(shared.is_configured(_jwt_with_role("anon")))


class DateValidationTests(TestCase):
    def test_accepts_real_iso_date(self):
        self.assertEqual(shared.validate_date("2026-07-17"), ("2026-07-17", None))

    def test_rejects_impossible_iso_date(self):
        value, error = shared.validate_date("2026-02-31")
        self.assertIsNone(value)
        self.assertIn("real YYYY-MM-DD", error)

    def test_rejects_non_iso_date(self):
        value, error = shared.validate_date("17/07/2026")
        self.assertIsNone(value)
        self.assertIn("format", error)


class NewsSanitizationTests(TestCase):
    def test_filters_malformed_and_social_rows_before_limit(self):
        rows = [
            {"title": "Short", "url": "https://example.com/short", "source": "Site"},
            {
                "title": "A valid but social-only Palmeiras story",
                "url": "https://x.com/example",
                "source": "X.com",
            },
            {
                "title": "A valid Palmeiras story from a public news source",
                "url": "https://example.com/story",
                "source": "Example",
            },
            {
                "title": "Another valid Palmeiras story from a public source",
                "url": "https://example.com/another",
                "source": "Example",
            },
        ]

        self.assertEqual(_public_news_items(rows, 1), [rows[2]])


class CrestTransparencyTests(TestCase):
    @staticmethod
    def _jpeg_fixture():
        image = Image.new("RGB", (24, 24), (247, 247, 247))
        pixels = image.load()
        for y in range(5, 19):
            for x in range(5, 19):
                pixels[x, y] = (12, 48, 31)
        for y in range(9, 15):
            for x in range(9, 15):
                pixels[x, y] = (255, 255, 255)
        output = BytesIO()
        image.save(output, format="JPEG", quality=95)
        return output.getvalue()

    def test_removes_only_edge_connected_jpeg_background(self):
        png = crest_manager.normalize_crest_image(
            self._jpeg_fixture(),
            remove_edge_background=True,
        )
        image = Image.open(BytesIO(png)).convert("RGBA")
        self.assertEqual(image.getpixel((0, 0))[3], 0)
        self.assertGreater(image.getpixel((12, 12))[3], 240)

    def test_crest_route_returns_cached_transparent_png(self):
        class Response:
            status_code = 200
            content = CrestTransparencyTests._jpeg_fixture()
            headers = {"content-type": "image/jpeg"}

        with tempfile.TemporaryDirectory() as directory, patch.object(
            crest_manager, "CRESTS_DIR", Path(directory)
        ), patch(
            "services.collector.palmeiras_collector.crest_manager.requests.get",
            return_value=Response(),
        ), patch(
            "services.api.palmeiras_api.routes.CRESTS_DIR", Path(directory)
        ):
            response = route_crest({"team_id": ["20002"]})
        self.assertEqual(response[0], 200)
        self.assertEqual(response[2], "image/png")
        image = Image.open(BytesIO(response[1])).convert("RGBA")
        self.assertEqual(image.getpixel((0, 0))[3], 0)
        self.assertGreater(image.getpixel((12, 12))[3], 240)

    def test_crest_route_rejects_unknown_team(self):
        response = route_crest({"team_id": ["999999"]})
        self.assertEqual(response[0], 400)


class TeamScopeTests(TestCase):
    def test_accepts_portuguese_team_scope_aliases(self):
        self.assertEqual(shared.team_scope_param({"team_scope": ["feminino"]}), "women")
        self.assertEqual(shared.team_scope_param({"team_scope": ["masculino"]}), "men")

    def test_transform_exposes_matchday_metadata(self):
        row = {
            "external_id": 42,
            "home_team": {"id": 20002, "name": "Palmeiras"},
            "away_team": {"id": 20001, "name": "Corinthians"},
            "area": {"teamScope": "women", "events": [{"type": "GOAL"}], "ticketUrl": "https://tickets.example"},
        }
        match = shared.transform_match(row)
        self.assertEqual(match["teamScope"], "women")
        self.assertEqual(match["events"][0]["type"], "GOAL")
        self.assertEqual(match["ticketUrl"], "https://tickets.example")


class HistoryTests(TestCase):
    def test_builds_h2h_record_and_form(self):
        rows = [{
            "external_id": 7,
            "utc_date": "2026-03-01T18:00:00Z",
            "status": "FINISHED",
            "home_team": {"id": 1769, "name": "Palmeiras"},
            "away_team": {"id": 1770, "name": "Rival"},
            "home_score": 2,
            "away_score": 1,
            "area": {"teamScope": "men"},
        }]
        payload = _history_payload(rows, scope="men", team_id=1769, opponent_id=1770)
        self.assertEqual(payload["record"]["wins"], 1)
        self.assertEqual(payload["record"]["goalsFor"], 2)
        self.assertEqual(payload["form"], ["W"])

    def test_match_detail_accepts_cbf_string_identifier(self):
        row = {
            "external_id": "cbf-women-832273",
            "utc_date": "2026-03-01T18:00:00Z",
            "status": "FINISHED",
            "home_team": {"id": 20002, "name": "Palmeiras"},
            "away_team": {"id": 59897, "name": "América"},
            "home_score": 2,
            "away_score": 0,
            "area": {"teamScope": "women"},
        }
        with patch("services.api.palmeiras_api.routes.is_configured", return_value=True), patch(
            "services.api.palmeiras_api.routes.supabase_get", side_effect=[[row], [row]]
        ):
            response = route_match_detail({"id": ["cbf-women-832273"]})
        self.assertEqual(response[0], 200)
        self.assertEqual(response[1]["match"]["id"], "cbf-women-832273")


class PushSubscriptionTests(TestCase):
    def test_subscription_round_trip_uses_persistent_store(self):
        payload = {
            "subscription": {
                "endpoint": "https://push.example/subscription/abc",
                "keys": {"p256dh": "p" * 80, "auth": "a" * 24},
            },
            "preferences": {"kickoff": True, "spoilerFree": True},
            "followedMatchIds": [1, "2", 2],
            "teamScope": "all",
        }
        with tempfile.TemporaryDirectory() as directory, patch.dict(
            os.environ, {"PALMEIRAS_STATE_DIR": directory}
        ):
            saved = save_subscription(payload, user_agent="test")
            removed = remove_subscription(payload)
        self.assertTrue(saved["subscribed"])
        self.assertEqual(saved["followedMatchIds"], ["1", "2"])
        self.assertTrue(removed["removed"])


class WomenCollectorTests(TestCase):
    def test_cbf_fixture_maps_to_shared_match_contract(self):
        fixture = {
            "ref_jogo": "832273",
            "rodada": "1",
            "data": " 13/02/2026",
            "hora": "21:00",
            "estadio": "Arena Barueri",
            "cidade": "Barueri",
            "uf": "SP",
            "transmissao": "TV Brasil",
            "mandante": {
                "nome": "Palmeiras",
                "url_escudo": "https://conteudo.cbf.com.br/clubes/20002/escudo.jpg",
                "gols": "4",
            },
            "visitante": {
                "nome": "América",
                "url_escudo": "https://conteudo.cbf.com.br/clubes/59897/escudo.jpg",
                "gols": "0",
            },
        }
        record = _record(fixture)
        area = json.loads(record["area"])
        self.assertEqual(record["home_score"], 4)
        self.assertEqual(area["teamScope"], "women")
        self.assertIn("maps/search", area["directionsUrl"])
