"""
=========================================================
Option Terminal Pro
Historical Data Engine
=========================================================
"""

from datetime import datetime, timedelta
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

        today = datetime.now()

        start = today - timedelta(days=days)

        cached_df = self.cache.get(symbol, timeframe, start, today)
        fetch_start = start
        if not cached_df.empty:
            fetch_start = cached_df.index.max().to_pydatetime() - timedelta(days=1)

        payload = {

            "symbol": symbol,

            "resolution": timeframe,

            "date_format": "1",

            "range_from": fetch_start.strftime("%Y-%m-%d"),

            "range_to": today.strftime("%Y-%m-%d"),

            "cont_flag": "1"

        }

        response = self.client.history(payload)

        if response.get("s") != "ok":

            raise Exception(
                response.get(
                    "message",
                    "Unable to fetch historical data."
                )
            )

        fresh_df = self._to_dataframe(response["candles"])
        self.cache.upsert(symbol, timeframe, fresh_df)
        self.cache.cleanup(keep_days=4)

        combined = pd.concat([cached_df, fresh_df]) if not cached_df.empty else fresh_df
        combined = self._dedupe(combined)
        return combined[combined.index >= pd.Timestamp(start)]

    # =====================================================
    # Today's Data
    # =====================================================

    def get_today(
        self,
        symbol,
        timeframe="5"
    ):

        today = datetime.now().strftime("%Y-%m-%d")

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

        df = pd.DataFrame(

            candles,

            columns=[

                "timestamp",

                "open",

                "high",

                "low",

                "close",

                "volume"

            ]

        )

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
