#!/usr/bin/env python3
"""Tests for the scheduled collector runner."""
import os
import tempfile
from unittest import TestCase, main
from unittest.mock import patch

from services.collector.palmeiras_collector import runner


class CollectorRunnerTests(TestCase):
    def test_missing_environment_fails_before_running_steps(self):
        with patch.dict(os.environ, {}, clear=True):
            code, summary = runner.run(lock_path="/tmp/palmeiras-test-missing.lock")

        self.assertEqual(code, 2)
        self.assertEqual(summary["status"], "error")
        self.assertEqual(summary["error"], "missing_environment")
        self.assertIn("SUPABASE_URL", summary["missing"])

    def test_continues_after_step_failure_and_reports_failed_step(self):
        calls = []

        def ok(name, value=1):
            def _inner():
                calls.append(name)
                return value
            return _inner

        def fail():
            calls.append("standings")
            raise RuntimeError("boom")

        env = {
            "SUPABASE_URL": "https://example.supabase.co",
            "SUPABASE_KEY": "service-role",
            "FOOTBALL_API_KEY": "football",
        }
        with tempfile.TemporaryDirectory() as tmpdir, patch.dict(os.environ, env, clear=True), \
            patch.object(runner, "collect_matches", ok("matches")), \
            patch.object(runner, "collect_copa_brasil", ok("copa_brasil")), \
            patch.object(runner, "collect_standings", fail), \
            patch.object(runner, "resolve_scores", ok("score_resolver", (0, 0))), \
            patch.object(runner, "apply_broadcast_info", ok("broadcasts", 0)), \
            patch.object(runner, "collect_news", ok("news", 3)):
            code, summary = runner.run(include_world_cup=False, lock_path=f"{tmpdir}/collector.lock")

        self.assertEqual(code, 1)
        self.assertEqual(summary["status"], "error")
        self.assertEqual(summary["failed_steps"], ["standings"])
        self.assertEqual(
            calls,
            ["matches", "copa_brasil", "standings", "score_resolver", "broadcasts", "news"],
        )

    def test_missing_football_key_does_not_block_independent_steps(self):
        calls = []

        def ok(name, value=1):
            def _inner():
                calls.append(name)
                return value
            return _inner

        env = {
            "SUPABASE_URL": "https://example.supabase.co",
            "SUPABASE_KEY": "service-role",
        }
        with tempfile.TemporaryDirectory() as tmpdir, patch.dict(os.environ, env, clear=True), \
            patch.object(runner, "collect_matches", ok("matches")), \
            patch.object(runner, "collect_copa_brasil", ok("copa_brasil")), \
            patch.object(runner, "collect_standings", ok("standings")), \
            patch.object(runner, "resolve_scores", ok("score_resolver", (0, 0))), \
            patch.object(runner, "apply_broadcast_info", ok("broadcasts", 0)), \
            patch.object(runner, "collect_news", ok("news", 3)):
            code, summary = runner.run(include_world_cup=False, lock_path=f"{tmpdir}/collector.lock")

        self.assertEqual(code, 1)
        self.assertEqual(summary["failed_steps"], ["matches", "standings"])
        self.assertEqual(calls, ["copa_brasil", "score_resolver", "broadcasts", "news"])


if __name__ == "__main__":
    main()
