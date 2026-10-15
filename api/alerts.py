"""Login and Telegram chart-photo helpers."""

from __future__ import annotations

import os
from typing import Any

import requests

from api.candle_cache import _secret_value


def app_login_code() -> str:
    return _secret_value("APP_LOGIN_CODE") or _secret_value("APP_PASSCODE")


class TelegramNotifier:
    def __init__(self):
        self.recipients = self._recipients()
        self.enabled = bool(self.recipients)

    def _recipients(self) -> list[tuple[str, str]]:
        recipients: list[tuple[str, str]] = []

        for index in range(1, 6):
            token = _secret_value(f"TELEGRAM_BOT_TOKEN_{index}")
            chat_id = _secret_value(f"TELEGRAM_CHAT_ID_{index}")
            if token and chat_id:
                recipients.append((token, chat_id))

        token = _secret_value("TELEGRAM_BOT_TOKEN")
        raw_chats = _secret_value("TELEGRAM_CHAT_IDS") or os.getenv("TELEGRAM_CHAT_IDS", "")
        single_chat = _secret_value("TELEGRAM_CHAT_ID")
        if token and not raw_chats and single_chat:
            raw_chats = single_chat
        if token and raw_chats:
            for chat_id in raw_chats.replace("\n", ",").split(","):
                chat_id = chat_id.strip()
                if chat_id:
                    recipients.append((token, chat_id))

        return recipients

    def send_document(self, filename: str, content: bytes, caption: str = "") -> tuple[bool, str]:
        if not self.recipients:
            return False, "Telegram recipients are not configured."

        failures: list[str] = []
        for token, chat_id in self.recipients:
            try:
                response = requests.post(
                    f"https://api.telegram.org/bot{token}/sendDocument",
                    data={"chat_id": chat_id, "caption": caption},
                    files={"document": (filename, content, "text/csv")},
                    timeout=20,
                )
                payload: dict[str, Any] = response.json()
                if response.status_code >= 400 or not payload.get("ok"):
                    failures.append(str(payload.get("description") or f"HTTP {response.status_code}"))
            except (requests.RequestException, ValueError) as exc:
                failures.append(str(exc))

        if failures:
            return False, "; ".join(failures[:2])
        return True, f"CSV sent to {len(self.recipients)} Telegram recipient(s)."
