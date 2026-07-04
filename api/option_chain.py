"""Option-chain access and normalization for FYERS."""

from __future__ import annotations

from typing import Any

import pandas as pd


class OptionChain:
    def __init__(self, client):
        self.client = client

    def fetch(self, symbol: str, strikecount: int = 25, greeks: bool = True) -> pd.DataFrame:
        payload = {
            "symbol": symbol,
            "strikecount": int(strikecount),
            "timestamp": "",
            "greeks": "1" if greeks else "0",
        }
        response: dict[str, Any] = self.client.optionchain(data=payload)
        if response.get("s") != "ok":
            raise RuntimeError(response.get("message", f"Option-chain fetch failed: {response}"))

        records = []
        for item in response.get("data", {}).get("optionsChain", []):
            option_type = item.get("option_type")
            if option_type not in {"CE", "PE"}:
                continue
            records.append(
                {
                    "symbol": item.get("symbol") or "",
                    "strike": int(float(item.get("strike_price", 0))),
                    "type": option_type,
                    "ltp": float(item.get("ltp", 0) or 0),
                    "oi": int(item.get("oi", 0) or 0),
                    "volume": int(item.get("volume", 0) or 0),
                    "iv": float(item.get("iv", 0) or 0),
                    "delta": float(item.get("delta", 0) or 0),
                    "gamma": float(item.get("gamma", 0) or 0),
                    "theta": float(item.get("theta", 0) or 0),
                    "vega": float(item.get("vega", 0) or 0),
                }
            )

        df = pd.DataFrame.from_records(records)
        if df.empty:
            return df
        return df.sort_values(["strike", "type"]).reset_index(drop=True)

    @staticmethod
    def pivot_for_display(df: pd.DataFrame, atm: int | None = None) -> pd.DataFrame:
        if df.empty:
            return df
        ce = df[df["type"] == "CE"].set_index("strike").add_prefix("CE ")
        pe = df[df["type"] == "PE"].set_index("strike").add_prefix("PE ")
        table = ce.join(pe, how="outer").sort_index()
        table.insert(0, "Strike", table.index.astype(int))
        if atm is not None:
            table.insert(1, "ATM", table.index.astype(int).map(lambda strike: "ATM" if strike == atm else ""))
        return table.reset_index(drop=True)
