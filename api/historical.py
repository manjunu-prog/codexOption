"""
=========================================================
Option Terminal Pro
Historical Data Engine
=========================================================
"""

from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo
import pandas as pd

from api.candle_cache import SupabaseCandleCache
from api.fyers_login import FyersLogin


class HistoricalData:

    def __init__(self, client=None, credentials=None):

        self.client = client or FyersLogin(credentials=credentials).get_client()
        self.cache = SupabaseCandleCache()

    # =====================================================
    # Generic History Loader
    # =====================================================

    def get_candles(
        self,
        symbol,
        timeframe="5",
        days=5
    ):

        now_ist = datetime.now(ZoneInfo("Asia/Kolkata"))
        today = now_ist.replace(tzinfo=None)

        start = today - timedelta(days=days)

        session_date = now_ist.date()
        debug_messages = []

        cached_df = self.cache.get(symbol, timeframe, start, today)
        fetch_start = start
        if not cached_df.empty:
            fetch_start = cached_df.index.max().to_pydatetime() - timedelta(days=1)

        if timeframe != "D":
            today_df, today_message = self._get_today_by_date(symbol, timeframe, now_ist)
            debug_messages.append(f"today-date: {today_message}")
            if not self._has_session_date(today_df, session_date):
                epoch_df, epoch_message = self._get_intraday_session(symbol, timeframe, now_ist)
                debug_messages.append(f"today-epoch: {epoch_message}")
                if self._has_session_date(epoch_df, session_date):
                    today_df = epoch_df
        else:
            today_df = pd.DataFrame()

        payload = {

            "symbol": symbol,

            "resolution": timeframe,

            "date_format": "1",

            "range_from": fetch_start.strftime("%Y-%m-%d"),

            "range_to": today.strftime("%Y-%m-%d"),

            "cont_flag": "1"

        }

        fresh_df, fresh_message = self._history_to_dataframe(payload)
        debug_messages.append(f"range: {fresh_message}")

        if not today_df.empty:
            fresh_df = pd.concat([fresh_df, today_df]) if not fresh_df.empty else today_df
            fresh_df = self._dedupe(fresh_df)

        if fresh_df.empty and cached_df.empty:
            raise Exception("Unable to fetch historical data. " + " | ".join(debug_messages))

        if not fresh_df.empty:
            self.cache.upsert(symbol, timeframe, fresh_df)
            self.cache.cleanup(keep_days=4)

        combined = pd.concat([cached_df, fresh_df]) if not cached_df.empty and not fresh_df.empty else (
            cached_df if fresh_df.empty else fresh_df
        )
        combined = self._dedupe(combined)
        combined.attrs["history_debug"] = " | ".join(debug_messages)
        return combined[combined.index >= pd.Timestamp(start)]

    def _history_to_dataframe(self, payload: dict) -> tuple[pd.DataFrame, str]:
        response = self.client.history(payload)
        if response.get("s") != "ok":
            message = response.get("message", "Unable to fetch historical data.")
            return pd.DataFrame(), message

        fresh_df = self._to_dataframe(response.get("candles", []))
        return fresh_df, self._df_message(fresh_df)

    def _get_today_by_date(self, symbol: str, timeframe: str, now_ist: datetime) -> tuple[pd.DataFrame, str]:
        today = now_ist.strftime("%Y-%m-%d")
        payload = {
            "symbol": symbol,
            "resolution": timeframe,
            "date_format": "1",
            "range_from": today,
            "range_to": today,
            "cont_flag": "1",
        }
        return self._history_to_dataframe(payload)

    def _get_intraday_session(self, symbol: str, timeframe: str, now_ist: datetime) -> tuple[pd.DataFrame, str]:
        session_start = datetime.combine(now_ist.date(), time(9, 15), tzinfo=ZoneInfo("Asia/Kolkata"))
        payload = {
            "symbol": symbol,
            "resolution": timeframe,
            "date_format": "0",
            "range_from": str(int(session_start.timestamp())),
            "range_to": str(int(now_ist.timestamp())),
            "cont_flag": "1",
        }
        return self._history_to_dataframe(payload)

    @staticmethod
    def _df_message(df: pd.DataFrame) -> str:
        if df.empty:
            return "0 rows"
        return f"{len(df)} rows latest {df.index.max().strftime('%d %b %H:%M')}"

    @staticmethod
    def _has_session_date(df: pd.DataFrame, session_date) -> bool:
        return not df.empty and bool((df.index.date == session_date).any())

    # =====================================================
    # Today's Data
    # =====================================================

    def get_today(
        self,
        symbol,
        timeframe="5"
    ):

        today = datetime.now(ZoneInfo("Asia/Kolkata")).strftime("%Y-%m-%d")

        payload = {

            "symbol": symbol,

            "resolution": timeframe,

            "date_format": "1",

            "range_from": today,

            "range_to": today,

            "cont_flag": "1"

        }

        response = self.client.history(payload)

        if response.get("s") != "ok":

            raise Exception(
                response.get(
                    "message",
                    "Unable to fetch today's data."
                )
            )

        return self._to_dataframe(
            response["candles"]
        )

    # =====================================================
    # Last N Candles
    # =====================================================

    def get_last_candles(
        self,
        symbol,
        timeframe="5",
        candles=100
    ):

        df = self.get_today(
            symbol,
            timeframe
        )

        return df.tail(candles)

    # =====================================================
    # DataFrame Converter
    # =====================================================

    @staticmethod
    def _to_dataframe(candles):

        columns = ["timestamp", "open", "high", "low", "close", "volume"]
        rows = []
        for candle in candles or []:
            if isinstance(candle, dict):
                if not all(column in candle for column in columns):
                    continue
                rows.append([candle[column] for column in columns])
            elif isinstance(candle, (list, tuple)) and len(candle) >= len(columns):
                rows.append(list(candle[: len(columns)]))

        df = pd.DataFrame(rows, columns=columns)
        if df.empty:
            return df

        df["datetime"] = pd.to_datetime(

            df["timestamp"],

            unit="s",

            utc=True

        ).dt.tz_convert("Asia/Kolkata").dt.tz_localize(None)

        df.set_index(

            "datetime",

            inplace=True

        )

        return HistoricalData._dedupe(df)

    @staticmethod
    def _dedupe(df):
        if df.empty:
            return df
        clean = df.copy()
        if "timestamp" in clean.columns:
            clean["timestamp"] = pd.to_numeric(clean["timestamp"], errors="coerce").astype("Int64")
            clean = clean.dropna(subset=["timestamp"])
            clean = clean.drop_duplicates(subset=["timestamp"], keep="last")
        clean = clean[~clean.index.duplicated(keep="last")].sort_index()
        return clean

    # =====================================================
    # Lightweight Chart JSON
    # =====================================================

    @staticmethod
    def candle_json(df):

        candles = []

        clean_df = df[~df.index.duplicated(keep="last")].sort_index()

        for _, row in clean_df.iterrows():

            candles.append({

                "time": int(_.timestamp()),

                "open": float(row.open),

                "high": float(row.high),

                "low": float(row.low),

                "close": float(row.close)

            })

        return candles

    # =====================================================
    # Volume JSON
    # =====================================================

    @staticmethod
    def volume_json(df):

        volume = []

        clean_df = df[~df.index.duplicated(keep="last")].sort_index()

        for _, row in clean_df.iterrows():

            color = (

                "rgba(38,166,154,0.4)"

                if row.close >= row.open

                else "rgba(239,83,80,0.4)"

            )

            volume.append({

                "time": int(_.timestamp()),

                "value": int(row.volume),

                "color": color

            })

        return volume
