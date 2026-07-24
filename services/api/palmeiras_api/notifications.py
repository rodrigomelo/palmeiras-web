"""Persistent Web Push subscriptions and collector-driven deliveries.

The store intentionally lives outside the release directory in production so
deployments can be atomic without losing browser subscriptions or delivery
deduplication state.
"""

from __future__ import annotations

import base64
import json
import os
import re
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from .shared import TEAM_IDS, transform_match

PREFERENCE_KEYS = {
    "oneHour",
    "kickoff",
    "results",
    "news",
    "scheduleChanges",
    "liveEvents",
    "spoilerFree",
}
DEFAULT_PREFERENCES = {
    "oneHour": False,
    "kickoff": False,
    "results": False,
    "news": False,
    "scheduleChanges": True,
    "liveEvents": False,
    "spoilerFree": False,
}


class SubscriptionValidationError(ValueError):
    """Raised when a browser sends an unsafe or malformed subscription."""


def _state_dir() -> Path:
    configured = os.environ.get("PALMEIRAS_STATE_DIR", "").strip()
    path = Path(configured) if configured else Path("/tmp/palmeiras-agenda")  # nosec B108
    path.mkdir(parents=True, exist_ok=True)
    return path


def _db_path() -> Path:
    return _state_dir() / "notifications.sqlite3"


def _connect() -> sqlite3.Connection:
    connection = sqlite3.connect(_db_path(), timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA foreign_keys=ON")
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS subscriptions (
            endpoint TEXT PRIMARY KEY,
            p256dh TEXT NOT NULL,
            auth TEXT NOT NULL,
            preferences TEXT NOT NULL,
            followed_match_ids TEXT NOT NULL,
            team_scope TEXT NOT NULL,
            user_agent TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS deliveries (
            endpoint TEXT NOT NULL,
            event_key TEXT NOT NULL,
            delivered_at TEXT NOT NULL,
            PRIMARY KEY (endpoint, event_key),
            FOREIGN KEY (endpoint) REFERENCES subscriptions(endpoint) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS match_snapshots (
            match_id TEXT PRIMARY KEY,
            snapshot TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        """
    )
    return connection


def _base64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _private_key_path() -> Path:
    return _state_dir() / "vapid_private.pem"


def _ensure_private_key() -> Path:
    """Create a persistent P-256 VAPID key once, safe across concurrent services."""
    path = _private_key_path()
    if path.exists():
        return path

    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ec

    key = ec.generate_private_key(ec.SECP256R1())
    pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        return path
    with os.fdopen(fd, "wb") as handle:
        handle.write(pem)
    return path


def vapid_public_key() -> str:
    """Return the browser-compatible uncompressed P-256 public key."""
    from cryptography.hazmat.primitives import serialization

    private_key = serialization.load_pem_private_key(_ensure_private_key().read_bytes(), password=None)
    public_bytes = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.X962,
        format=serialization.PublicFormat.UncompressedPoint,
    )
    return _base64url(public_bytes)


def _validated_payload(payload) -> dict:
    if not isinstance(payload, dict):
        raise SubscriptionValidationError("JSON object required")
    subscription = payload.get("subscription")
    if not isinstance(subscription, dict):
        raise SubscriptionValidationError("subscription is required")
    endpoint = str(subscription.get("endpoint") or "").strip()
    parsed = urlparse(endpoint)
    if parsed.scheme != "https" or not parsed.netloc or len(endpoint) > 2048:
        raise SubscriptionValidationError("invalid subscription endpoint")
    keys = subscription.get("keys")
    if not isinstance(keys, dict):
        raise SubscriptionValidationError("subscription keys are required")
    p256dh = str(keys.get("p256dh") or "").strip()
    auth = str(keys.get("auth") or "").strip()
    if not (20 <= len(p256dh) <= 512 and 8 <= len(auth) <= 256):
        raise SubscriptionValidationError("invalid subscription keys")

    raw_preferences = payload.get("preferences") or {}
    if not isinstance(raw_preferences, dict):
        raise SubscriptionValidationError("invalid preferences")
    preferences = dict(DEFAULT_PREFERENCES)
    for key in PREFERENCE_KEYS:
        if key in raw_preferences:
            preferences[key] = bool(raw_preferences[key])

    raw_followed = payload.get("followedMatchIds") or []
    if not isinstance(raw_followed, list) or len(raw_followed) > 100:
        raise SubscriptionValidationError("invalid followedMatchIds")
    followed = []
    for value in raw_followed:
        match_id = str(value or "").strip()
        if not match_id or len(match_id) > 100 or not re.fullmatch(r"[A-Za-z0-9._:-]+", match_id):
            raise SubscriptionValidationError("invalid followedMatchIds")
        if match_id not in followed:
            followed.append(match_id)

    team_scope = str(payload.get("teamScope") or "men").lower()
    if team_scope not in ("men", "women", "all"):
        raise SubscriptionValidationError("invalid teamScope")
    return {
        "endpoint": endpoint,
        "p256dh": p256dh,
        "auth": auth,
        "preferences": preferences,
        "followed": followed,
        "team_scope": team_scope,
    }


def save_subscription(payload, *, user_agent="") -> dict:
    clean = _validated_payload(payload)
    now = datetime.now(timezone.utc).isoformat()
    with _connect() as connection:
        existing = connection.execute(
            "SELECT created_at FROM subscriptions WHERE endpoint = ?", (clean["endpoint"],)
        ).fetchone()
        created_at = existing["created_at"] if existing else now
        connection.execute(
            """
            INSERT OR REPLACE INTO subscriptions
                (endpoint, p256dh, auth, preferences, followed_match_ids, team_scope,
                 user_agent, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                clean["endpoint"],
                clean["p256dh"],
                clean["auth"],
                json.dumps(clean["preferences"], separators=(",", ":")),
                json.dumps(clean["followed"], separators=(",", ":")),
                clean["team_scope"],
                str(user_agent or "")[:300],
                created_at,
                now,
            ),
        )
    return {
        "subscribed": True,
        "preferences": clean["preferences"],
        "followedMatchIds": clean["followed"],
        "teamScope": clean["team_scope"],
    }


def remove_subscription(payload) -> dict:
    subscription = payload.get("subscription") if isinstance(payload, dict) else None
    endpoint = ""
    if isinstance(subscription, dict):
        endpoint = str(subscription.get("endpoint") or "").strip()
    if not endpoint and isinstance(payload, dict):
        endpoint = str(payload.get("endpoint") or "").strip()
    if not endpoint or len(endpoint) > 2048:
        raise SubscriptionValidationError("subscription endpoint is required")
    with _connect() as connection:
        cursor = connection.execute("DELETE FROM subscriptions WHERE endpoint = ?", (endpoint,))
    return {"subscribed": False, "removed": cursor.rowcount > 0}


def subscription_count() -> int:
    with _connect() as connection:
        return int(connection.execute("SELECT COUNT(*) FROM subscriptions").fetchone()[0])


def _parse_datetime(value):
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _team_name(team) -> str:
    return str((team or {}).get("shortName") or (team or {}).get("name") or "Adversário")


def _match_label(match) -> str:
    return f"{_team_name(match.get('homeTeam'))} x {_team_name(match.get('awayTeam'))}"


def _scope_matches(subscription, match) -> bool:
    scope = subscription["team_scope"]
    return scope == "all" or match.get("teamScope") == scope


def _notification_candidates(matches, news_rows, changed_ids, now):
    candidates = []
    live_statuses = {"IN_PLAY", "PAUSED"}
    finished_statuses = {"FINISHED", "PLAYING_TIME_FINISHED"}
    for match in matches:
        match_id = str(match.get("id") or "")
        kickoff = _parse_datetime(match.get("utcDate"))
        if not match_id or not kickoff:
            continue
        minutes = (kickoff - now).total_seconds() / 60
        label = _match_label(match)
        base_url = f"/?match={match_id}&tab=home"
        if 40 <= minutes <= 75 and match.get("status") in ("SCHEDULED", "TIMED"):
            candidates.append(("oneHour", f"match:{match_id}:one-hour", match, {
                "title": "Jogo em cerca de 1 hora",
                "body": label,
                "url": base_url,
                "tag": f"match-{match_id}-reminder",
            }))
        if match.get("status") in live_statuses or (-5 <= minutes <= 8 and match.get("status") in ("SCHEDULED", "TIMED")):
            candidates.append(("kickoff", f"match:{match_id}:kickoff", match, {
                "title": "A bola está rolando",
                "body": label,
                "url": base_url,
                "tag": f"match-{match_id}-kickoff",
            }))
        if match.get("status") in finished_statuses:
            candidates.append(("results", f"match:{match_id}:result", match, {
                "title": "Placar final disponível",
                "body": label,
                "scoreBody": f"{label}: {match.get('homeScore')}–{match.get('awayScore')}",
                "url": base_url,
                "tag": f"match-{match_id}-result",
            }))
        if match_id in changed_ids:
            candidates.append(("scheduleChanges", f"match:{match_id}:schedule:{match.get('utcDate')}:{match.get('venue')}", match, {
                "title": "Agenda do jogo atualizada",
                "body": label,
                "url": base_url,
                "tag": f"match-{match_id}-schedule",
            }))
        for event in match.get("events") or []:
            event_id = event.get("id") or f"{event.get('type')}:{event.get('minute')}:{event.get('teamId')}:{event.get('player')}"
            candidates.append(("liveEvents", f"match:{match_id}:event:{event_id}", match, {
                "title": str(event.get("label") or event.get("type") or "Lance importante"),
                "body": label,
                "url": base_url,
                "tag": f"match-{match_id}-live",
            }))

    for row in news_rows or []:
        news_id = row.get("id") or row.get("url")
        title = str(row.get("title") or "").strip()
        if news_id and title:
            candidates.append(("news", f"news:{news_id}", None, {
                "title": "Notícia do Palmeiras",
                "body": title[:160],
                "url": "/?tab=news",
                "tag": "palmeiras-news",
                "publishedAt": row.get("published_at") or row.get("collected_at"),
            }))
    return candidates


def _changed_match_ids(connection, matches) -> set[str]:
    changed = set()
    now = datetime.now(timezone.utc).isoformat()
    for match in matches:
        match_id = str(match.get("id") or "")
        if not match_id:
            continue
        snapshot = json.dumps(
            {"utcDate": match.get("utcDate"), "venue": match.get("venue"), "status": match.get("status")},
            sort_keys=True,
            separators=(",", ":"),
        )
        previous = connection.execute(
            "SELECT snapshot FROM match_snapshots WHERE match_id = ?", (match_id,)
        ).fetchone()
        if previous and previous["snapshot"] != snapshot:
            old = json.loads(previous["snapshot"])
            current = json.loads(snapshot)
            if old.get("utcDate") != current.get("utcDate") or old.get("venue") != current.get("venue"):
                changed.add(match_id)
        connection.execute(
            "INSERT OR REPLACE INTO match_snapshots (match_id, snapshot, updated_at) VALUES (?, ?, ?)",
            (match_id, snapshot, now),
        )
    return changed


def deliver_pending_notifications() -> dict:
    """Send due browser notifications once; called after each collector refresh."""
    from pywebpush import WebPushException, webpush

    from .shared import supabase_get

    with _connect() as connection:
        subscriptions = [dict(row) for row in connection.execute("SELECT * FROM subscriptions")]
        if not subscriptions:
            return {"subscriptions": 0, "sent": 0, "failed": 0, "removed": 0}
        match_rows = supabase_get("matches", select="*", order="utc_date.desc", limit="400")
        matches = [transform_match(row) for row in match_rows]
        changed_ids = _changed_match_ids(connection, matches)
        news_rows = supabase_get("news", select="*", order="collected_at.desc", limit="15")
        candidates = _notification_candidates(matches, news_rows, changed_ids, datetime.now(timezone.utc))

        sent = failed = removed = 0
        private_key = str(_ensure_private_key())
        for subscription in subscriptions:
            preferences = json.loads(subscription["preferences"])
            followed = set(json.loads(subscription["followed_match_ids"]))
            created_at = _parse_datetime(subscription["created_at"])
            web_subscription = {
                "endpoint": subscription["endpoint"],
                "keys": {"p256dh": subscription["p256dh"], "auth": subscription["auth"]},
            }
            for preference, event_key, match, payload in candidates:
                if not preferences.get(preference, False):
                    continue
                if match and not _scope_matches(subscription, match):
                    continue
                if preference == "liveEvents" and followed and str(match.get("id") or "") not in followed:
                    continue
                published_at = _parse_datetime(payload.get("publishedAt"))
                if preference == "news" and created_at and published_at and published_at < created_at:
                    continue
                already = connection.execute(
                    "SELECT 1 FROM deliveries WHERE endpoint = ? AND event_key = ?",
                    (subscription["endpoint"], event_key),
                ).fetchone()
                if already:
                    continue
                public_payload = dict(payload)
                public_payload.pop("publishedAt", None)
                score_body = public_payload.pop("scoreBody", None)
                if score_body and not preferences.get("spoilerFree"):
                    public_payload["body"] = score_body
                public_payload["icon"] = "/static/icon-192.png"
                public_payload["badge"] = "/static/icon-192.png"
                try:
                    webpush(
                        subscription_info=web_subscription,
                        data=json.dumps(public_payload, ensure_ascii=False),
                        vapid_private_key=private_key,
                        vapid_claims={"sub": "mailto:suporte@rodrigolanna.com.br"},
                        ttl=86400,
                    )
                    connection.execute(
                        "INSERT INTO deliveries (endpoint, event_key, delivered_at) VALUES (?, ?, ?)",
                        (subscription["endpoint"], event_key, datetime.now(timezone.utc).isoformat()),
                    )
                    sent += 1
                    time.sleep(0.02)
                except WebPushException as error:
                    status_code = getattr(getattr(error, "response", None), "status_code", None)
                    if status_code in (404, 410):
                        connection.execute(
                            "DELETE FROM subscriptions WHERE endpoint = ?", (subscription["endpoint"],)
                        )
                        removed += 1
                        break
                    failed += 1
        return {"subscriptions": len(subscriptions), "sent": sent, "failed": failed, "removed": removed}
