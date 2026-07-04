"""Optional Supabase-backed candle cache."""

from __future__ import annotations

from datetime import datetime, timedelta
import os
from typing import Any

import pandas as pd
import requests


def _secret_value(key: str) -> str:
    value = os.getenv(key, "")
    if value:
        return value
    try:
        import streamlit as st

        return st.secrets.get(key, "")
    except Exception:
        return ""


def _supabase_rest_url() -> str:
    url = _secret_value("SUPABASE_URL").strip().rstrip("/")
    if not url:
        return ""
    if url.startswith("https://") or url.startswith("http://"):
        if url.endswith("/rest/v1"):
            url = url[: -len("/rest/v1")]
        elif "/rest/v1/" in url:
            url = url.split("/rest/v1/", 1)[0]
        return url
    return ""


class SupabaseCandleCache:
    table = "candles"
    cache_version = "v2"

    def __init__(self):
        self.url = _supabase_rest_url()
        self.key = _secret_value("SUPABASE_SERVICE_ROLE_KEY") or _secret_value("SUPABASE_ANON_KEY")
        self.enabled = bool(self.url and self.key)

    @property
    def headers(self) -> dict[str, str]:
        return {
            "apikey": self.key,
            "Authorization": f"Bearer {self.key}",
            "Content-Type": "application/json",
            "Prefer": "resolution=merge-duplicates",
        }

    def get(self, symbol: str, resolution: str, start: datetime, end: datetime) -> pd.DataFrame:
        if not self.enabled:
            return pd.DataFrame()

        params = {
            "select": "timestamp,open,high,low,close,volume",
            "symbol": f"eq.{self.cache_symbol(symbol)}",
            "resolution": f"eq.{resolution}",
            "timestamp": f"gte.{int(start.timestamp())}",
            "order": "timestamp.asc",
            "limit": "10000",
        }
        try:
            response = requests.get(self.endpoint, headers=self.headers, params=params, timeout=12)
        except requests.RequestException:
            return pd.DataFrame()
        if response.status_code >= 400:
            return pd.DataFrame()

        rows: list[dict[str, Any]] = [
            row for row in response.json() if int(row.get("timestamp", 0)) <= int(end.timestamp())
        ]
        if not rows:
            return pd.DataFrame()
        return self.to_dataframe(rows)

    def upsert(self, symbol: str, resolution: str, df: pd.DataFrame) -> None:
        if not self.enabled or df.empty:
            return

        rows = []
        for ts, row in df[~df.index.duplicated(keep="last")].sort_index().iterrows():
            timestamp = int(row.timestamp) if "timestamp" in df.columns and pd.notna(row.timestamp) else int(ts.timestamp())
            rows.append(
                {
                    "symbol": self.cache_symbol(symbol),
                    "resolution": str(resolution),
                    "timestamp": timestamp,
                    "open": float(row.open),
                    "high": float(row.high),
                    "low": float(row.low),
                    "close": float(row.close),
                    "volume": int(row.volume),
                }
            )

        for start in range(0, len(rows), 500):
            try:
                requests.post(self.endpoint, headers=self.headers, json=rows[start : start + 500], timeout=20)
            except requests.RequestException:
                return

    def cleanup(self, keep_days: int = 4) -> None:
        if not self.enabled:
            return
        cutoff = int((datetime.now() - timedelta(days=keep_days)).timestamp())
        try:
            requests.delete(
                self.endpoint,
                headers=self.headers,
                params={"timestamp": f"lt.{cutoff}"},
                timeout=12,
            )
        except requests.RequestException:
            return

    @property
    def endpoint(self) -> str:
        return f"{self.url}/rest/v1/{self.table}"

    def cache_symbol(self, symbol: str) -> str:
        return f"{self.cache_version}:{symbol}"

    @staticmethod
    def to_dataframe(rows: list[dict[str, Any]]) -> pd.DataFrame:
        df = pd.DataFrame.from_records(rows)
        if df.empty:
            return df
        df["datetime"] = pd.to_datetime(df["timestamp"], unit="s", utc=True).dt.tz_convert("Asia/Kolkata").dt.tz_localize(None)
        df.set_index("datetime", inplace=True)
        return df[["timestamp", "open", "high", "low", "close", "volume"]].sort_index()
