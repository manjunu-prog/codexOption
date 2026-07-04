"""Login and Telegram signal alert helpers."""

from __future__ import annotations

from datetime import datetime
import hashlib
import os
from typing import Any

import requests

from api.candle_cache import _secret_value, _supabase_rest_url


def app_login_code() -> str:
    return _secret_value("APP_LOGIN_CODE") or _secret_value("APP_PASSCODE")


class SignalAlertStore:
    table = "signal_alerts"

    def __init__(self):
        self.url = _supabase_rest_url()
        self.key = _secret_value("SUPABASE_SERVICE_ROLE_KEY") or _secret_value("SUPABASE_ANON_KEY")
        self.enabled = bool(self.url and self.key)
        self.local_alerts: dict[str, dict[str, Any]] = {}

    @property
    def endpoint(self) -> str:
        return f"{self.url}/rest/v1/{self.table}"

    @property
    def headers(self) -> dict[str, str]:
        return {
            "apikey": self.key,
            "Authorization": f"Bearer {self.key}",
            "Content-Type": "application/json",
        }

    def should_send(self, signal_key: str, repeat_seconds: int, max_repeats: int) -> bool:
        now = datetime.utcnow()
        if not self.enabled:
            row = self.local_alerts.get(signal_key, {})
            sent_count = int(row.get("sent_count", 0) or 0)
            last_sent = row.get("last_sent_at")
            if sent_count >= max_repeats:
                return False
            return last_sent is None or (now - last_sent).total_seconds() >= repeat_seconds

        try:
            response = requests.get(
                self.endpoint,
                headers=self.headers,
                params={
                    "select": "signal_key,last_sent_at,sent_count",
                    "signal_key": f"eq.{signal_key}",
                    "limit": "1",
                },
                timeout=8,
            )
        except requests.RequestException:
            row = self.local_alerts.get(signal_key, {})
            sent_count = int(row.get("sent_count", 0) or 0)
            last_sent = row.get("last_sent_at")
            if sent_count >= max_repeats:
                return False
            return last_sent is None or (now - last_sent).total_seconds() >= repeat_seconds

        if response.status_code >= 400:
            row = self.local_alerts.get(signal_key, {})
            sent_count = int(row.get("sent_count", 0) or 0)
            last_sent = row.get("last_sent_at")
            if sent_count >= max_repeats:
                return False
            return last_sent is None or (now - last_sent).total_seconds() >= repeat_seconds

        rows = response.json()
        if not rows:
            return True

        row = rows[0]
        last_sent = _parse_dt(row.get("last_sent_at"))
        sent_count = int(row.get("sent_count", 0) or 0)
        self.local_alerts[signal_key] = {"last_sent_at": last_sent, "sent_count": sent_count}
        if sent_count >= max_repeats:
            return False
        if not last_sent:
            return True
        return (now - last_sent).total_seconds() >= repeat_seconds

    def mark_sent(self, signal_key: str, payload: dict[str, Any]) -> None:
        now = datetime.utcnow()
        row = self.local_alerts.get(signal_key, {})
        sent_count = int(row.get("sent_count", 0) or 0) + 1
        self.local_alerts[signal_key] = {"last_sent_at": now, "sent_count": sent_count}
        if not self.enabled:
            return

        row = {
            "signal_key": signal_key,
            "symbol": payload.get("symbol", ""),
            "signal_type": payload.get("signal_type", ""),
            "signal_time": payload.get("signal_time"),
            "message": payload.get("message", ""),
            "last_sent_at": now.isoformat(),
            "sent_count": sent_count,
        }
        try:
            requests.post(
                self.endpoint,
                headers={**self.headers, "Prefer": "resolution=merge-duplicates"},
                json=row,
                timeout=8,
            )
        except requests.RequestException:
            return


class TelegramNotifier:
    def __init__(self):
        self.recipients = self._recipients()
        self.enabled = bool(self.recipients)
        self.store = SignalAlertStore()

    def _recipients(self) -> list[tuple[str, str]]:
        recipients: list[tuple[str, str]] = []

        for index in range(1, 6):
            token = _secret_value(f"TELEGRAM_BOT_TOKEN_{index}")
            chat_id = _secret_value(f"TELEGRAM_CHAT_ID_{index}")
            if token and chat_id:
                recipients.append((token, chat_id))

        token = _secret_value("TELEGRAM_BOT_TOKEN")
        raw_chats = _secret_value("TELEGRAM_CHAT_IDS") or os.getenv("TELEGRAM_CHAT_IDS", "")
        if token and raw_chats:
            for chat_id in raw_chats.replace("\n", ",").split(","):
                chat_id = chat_id.strip()
                if chat_id:
                    recipients.append((token, chat_id))

        return recipients

    def send_repeating(self, payload: dict[str, Any], repeat_seconds: int = 30, max_repeats: int = 10) -> None:
        if not self.enabled:
            return

        signal_key = payload["signal_key"]
        if not self.store.should_send(signal_key, repeat_seconds=repeat_seconds, max_repeats=max_repeats):
            return

        sent = False
        for token, chat_id in self.recipients:
            try:
                response = requests.post(
                    f"https://api.telegram.org/bot{token}/sendMessage",
                    json={
                        "chat_id": chat_id,
                        "text": payload["message"],
                        "disable_web_page_preview": True,
                    },
                    timeout=8,
                )
                sent = sent or response.status_code < 400
            except requests.RequestException:
                continue
        if sent:
            self.store.mark_sent(signal_key, payload)


def signal_key(*parts: object) -> str:
    raw = "|".join(str(part) for part in parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def format_signal_time(timestamp: int) -> str:
    return datetime.fromtimestamp(int(timestamp)).strftime("%Y-%m-%d %H:%M")


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).replace(tzinfo=None)
    except Exception:
        return None
