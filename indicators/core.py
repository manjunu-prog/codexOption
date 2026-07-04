"""Technical indicators and smart-money style structure annotations."""

from __future__ import annotations

import pandas as pd


def _clean_line(values: pd.Series) -> list[dict]:
    safe = pd.to_numeric(values, errors="coerce").replace([float("inf"), float("-inf")], pd.NA).dropna()
    return [{"time": int(ts.timestamp()), "value": float(value)} for ts, value in safe.items()]


def ema(df: pd.DataFrame, period: int) -> list[dict]:
    values = df["close"].ewm(span=period, adjust=False).mean()
    return _clean_line(values)


def vwap(df: pd.DataFrame) -> list[dict]:
    typical = (df["high"] + df["low"] + df["close"]) / 3
    volume = pd.to_numeric(df["volume"], errors="coerce").fillna(0)
    cumulative_volume = volume.cumsum()
    values = (typical * volume).cumsum() / cumulative_volume.where(cumulative_volume > 0)
    return _clean_line(values)


def alphatrend(
    df: pd.DataFrame,
    period: int = 14,
    coeff: float = 1.0,
    show_signals: bool = True,
    no_volume_data: bool = False,
) -> dict[str, list[dict]]:
    clean = df[~df.index.duplicated(keep="last")].sort_index()
    if clean.empty:
        return {"current": [], "lag": [], "markers": []}

    high = pd.to_numeric(clean["high"], errors="coerce")
    low = pd.to_numeric(clean["low"], errors="coerce")
    close = pd.to_numeric(clean["close"], errors="coerce")
    prev_close = close.shift(1)
    true_range = pd.concat(
        [(high - low), (high - prev_close).abs(), (low - prev_close).abs()],
        axis=1,
    ).max(axis=1)
    atr = true_range.rolling(period, min_periods=period).mean()
    up_trend = low - (atr * coeff)
    down_trend = high + (atr * coeff)

    if no_volume_data:
        direction_ok = _rsi(close, period) >= 50
    else:
        direction_ok = _mfi(high, low, close, clean["volume"], period) >= 50

    alpha: list[float | None] = []
    previous: float | None = None
    for i in range(len(clean)):
        if pd.isna(up_trend.iloc[i]) or pd.isna(down_trend.iloc[i]) or pd.isna(direction_ok.iloc[i]):
            alpha.append(None)
            continue

        if bool(direction_ok.iloc[i]):
            current = float(up_trend.iloc[i]) if previous is None else max(float(up_trend.iloc[i]), previous)
        else:
            current = float(down_trend.iloc[i]) if previous is None else min(float(down_trend.iloc[i]), previous)
        alpha.append(current)
        previous = current

    alpha_series = pd.Series(alpha, index=clean.index, dtype="float64")
    lag_series = alpha_series.shift(2)
    markers: list[dict] = []

    if show_signals:
        buy = _crossover(alpha_series, lag_series)
        sell = _crossunder(alpha_series, lag_series)
        last_buy_index: int | None = None
        last_sell_index: int | None = None
        buy_since: list[int | None] = []
        sell_since: list[int | None] = []

        for i, ts in enumerate(clean.index):
            if bool(buy.iloc[i]):
                last_buy_index = i
            if bool(sell.iloc[i]):
                last_sell_index = i
            buy_since.append(None if last_buy_index is None else i - last_buy_index)
            sell_since.append(None if last_sell_index is None else i - last_sell_index)

            previous_buy_since = buy_since[i - 1] if i > 0 else None
            previous_sell_since = sell_since[i - 1] if i > 0 else None
            lag_value = lag_series.iloc[i]
            if pd.isna(lag_value):
                continue

            if bool(buy.iloc[i]) and previous_buy_since is not None and sell_since[i] is not None and previous_buy_since > sell_since[i]:
                markers.append(
                    {
                        "time": int(ts.timestamp()),
                        "price": float(lag_value) * 0.9999,
                        "position": "belowBar",
                        "color": "#0022FC",
                        "shape": "arrowUp",
                        "text": "BUY",
                    }
                )
            if bool(sell.iloc[i]) and previous_sell_since is not None and buy_since[i] is not None and previous_sell_since > buy_since[i]:
                markers.append(
                    {
                        "time": int(ts.timestamp()),
                        "price": float(lag_value) * 1.0001,
                        "position": "aboveBar",
                        "color": "#80000B",
                        "shape": "arrowDown",
                        "text": "SELL",
                    }
                )

    current_points = _clean_line(alpha_series)
    lag_points = _clean_line(lag_series)
    lag_by_time = {point["time"]: point["value"] for point in lag_points}
    body_points = [
        {
            **point,
            "color": "rgba(0,230,15,0.72)" if point["value"] >= lag_by_time.get(point["time"], point["value"]) else "rgba(128,0,11,0.72)",
        }
        for point in current_points
    ]

    return {
        "body": body_points,
        "current": current_points,
        "lag": lag_points,
        "markers": markers[-80:],
    }


def _rsi(values: pd.Series, period: int) -> pd.Series:
    delta = values.diff()
    gain = delta.clip(lower=0).rolling(period, min_periods=period).mean()
    loss = (-delta.clip(upper=0)).rolling(period, min_periods=period).mean()
    rs = gain / loss.where(loss > 0)
    rsi = 100 - (100 / (1 + rs))
    return rsi.where(loss > 0, 100)


def _mfi(high: pd.Series, low: pd.Series, close: pd.Series, volume: pd.Series, period: int) -> pd.Series:
    typical = (high + low + close) / 3
    money_flow = typical * pd.to_numeric(volume, errors="coerce").fillna(0)
    positive = money_flow.where(typical > typical.shift(1), 0.0)
    negative = money_flow.where(typical < typical.shift(1), 0.0)
    positive_sum = positive.rolling(period, min_periods=period).sum()
    negative_sum = negative.rolling(period, min_periods=period).sum()
    ratio = positive_sum / negative_sum.where(negative_sum > 0)
    mfi = 100 - (100 / (1 + ratio))
    return mfi.where(negative_sum > 0, 100)


def _crossover(left: pd.Series, right: pd.Series) -> pd.Series:
    return (left > right) & (left.shift(1) <= right.shift(1))


def _crossunder(left: pd.Series, right: pd.Series) -> pd.Series:
    return (left < right) & (left.shift(1) >= right.shift(1))


def fair_value_gaps(df: pd.DataFrame, max_zones: int = 40) -> list[dict]:
    zones: list[dict] = []
    rows = df.reset_index()
    for i in range(2, len(rows)):
        left = rows.iloc[i - 2]
        current = rows.iloc[i]
        if current["low"] > left["high"]:
            zones.append(
                {
                    "time": int(current["datetime"].timestamp()),
                    "from": float(left["high"]),
                    "to": float(current["low"]),
                    "direction": "bullish",
                }
            )
        elif current["high"] < left["low"]:
            zones.append(
                {
                    "time": int(current["datetime"].timestamp()),
                    "from": float(current["high"]),
                    "to": float(left["low"]),
                    "direction": "bearish",
                }
            )
    return zones[-max_zones:]


def fvg_ifvg_order_blocks(
    df: pd.DataFrame,
    fvg_extend: int = 5,
    ifvg_extend: int = 5,
    ob_extend: int = 5,
    swing_lookback: int = 5,
    max_zones: int = 180,
) -> list[dict]:
    rows = df[~df.index.duplicated(keep="last")].sort_index().reset_index()
    if rows.empty:
        return []

    times = [int(ts.timestamp()) for ts in rows["datetime"]]
    step = _infer_time_step(times)

    def time_at(index: int) -> int:
        if index < len(times):
            return times[max(index, 0)]
        return times[-1] + ((index - len(times) + 1) * step)

    zones: list[dict] = []
    active_fvgs: list[dict] = []
    last_swing_high: float | None = None
    last_swing_low: float | None = None
    last_red: dict | None = None
    last_green: dict | None = None

    for i, row in rows.iterrows():
        open_price = float(row["open"])
        high = float(row["high"])
        low = float(row["low"])
        close = float(row["close"])

        pivot_index = i - swing_lookback
        if pivot_index >= swing_lookback and i >= swing_lookback * 2:
            window = rows.iloc[pivot_index - swing_lookback : pivot_index + swing_lookback + 1]
            pivot = rows.iloc[pivot_index]
            if float(pivot["high"]) == float(window["high"].max()):
                last_swing_high = float(pivot["high"])
            if float(pivot["low"]) == float(window["low"].min()):
                last_swing_low = float(pivot["low"])

        if close > open_price:
            last_green = {"index": i, "top": high, "bottom": low}
        elif close < open_price:
            last_red = {"index": i, "top": high, "bottom": low}

        if i >= 2:
            left = rows.iloc[i - 2]
            middle = rows.iloc[i - 1]
            bull_fvg = float(left["high"]) < low and float(middle["close"]) > float(left["high"])
            bear_fvg = float(left["low"]) > high and float(middle["close"]) < float(left["low"])

            if bull_fvg:
                zone = _zone(
                    kind="fvg",
                    direction="bullish",
                    label="FVG - BULL",
                    start_time=time_at(i - 2),
                    end_time=time_at(i + fvg_extend),
                    top=low,
                    bottom=float(left["high"]),
                    fill="rgba(46,125,50,0.18)",
                    border="rgba(46,125,50,0.65)",
                    text="rgba(74,222,128,0.95)",
                    border_style="dashed",
                )
                zones.append(zone)
                active_fvgs.append(zone)

            if bear_fvg:
                zone = _zone(
                    kind="fvg",
                    direction="bearish",
                    label="FVG - BEAR",
                    start_time=time_at(i - 2),
                    end_time=time_at(i + fvg_extend),
                    top=float(left["low"]),
                    bottom=high,
                    fill="rgba(198,40,40,0.18)",
                    border="rgba(198,40,40,0.70)",
                    text="rgba(248,113,113,0.95)",
                    border_style="dashed",
                )
                zones.append(zone)
                active_fvgs.append(zone)

        previous_close = float(rows.iloc[i - 1]["close"]) if i > 0 else close
        if last_swing_high is not None and previous_close <= last_swing_high < close and last_red is not None:
            zones.append(
                _zone(
                    kind="ob",
                    direction="bullish",
                    label="BULLISH OB",
                    start_time=time_at(last_red["index"]),
                    end_time=time_at(i + ob_extend),
                    top=last_red["top"],
                    bottom=last_red["bottom"],
                    fill="rgba(46,125,50,0.28)",
                    border="rgba(46,125,50,0.82)",
                    text="rgba(74,222,128,0.98)",
                    border_style="solid",
                )
            )
            last_swing_high = None

        if last_swing_low is not None and previous_close >= last_swing_low > close and last_green is not None:
            zones.append(
                _zone(
                    kind="ob",
                    direction="bearish",
                    label="BEARISH OB",
                    start_time=time_at(last_green["index"]),
                    end_time=time_at(i + ob_extend),
                    top=last_green["top"],
                    bottom=last_green["bottom"],
                    fill="rgba(198,40,40,0.28)",
                    border="rgba(198,40,40,0.82)",
                    text="rgba(248,113,113,0.98)",
                    border_style="solid",
                )
            )
            last_swing_low = None

        for zone in list(active_fvgs):
            if zone["direction"] == "bullish" and close < zone["bottom"]:
                zone.update(
                    {
                        "kind": "ifvg",
                        "direction": "bearish",
                        "label": "iFVG (INTERNAL)",
                        "endTime": time_at(i + ifvg_extend),
                        "fill": "rgba(106,27,154,0.20)",
                        "border": "rgba(106,27,154,0.72)",
                        "text": "rgba(216,180,254,0.96)",
                        "borderStyle": "dotted",
                    }
                )
                active_fvgs.remove(zone)
            elif zone["direction"] == "bearish" and close > zone["top"]:
                zone.update(
                    {
                        "kind": "ifvg",
                        "direction": "bullish",
                        "label": "iFVG (INTERNAL)",
                        "endTime": time_at(i + ifvg_extend),
                        "fill": "rgba(0,131,143,0.20)",
                        "border": "rgba(0,131,143,0.74)",
                        "text": "rgba(103,232,249,0.96)",
                        "borderStyle": "dotted",
                    }
                )
                active_fvgs.remove(zone)

    return zones[-max_zones:]


def _infer_time_step(times: list[int]) -> int:
    deltas = [b - a for a, b in zip(times, times[1:]) if b > a]
    if not deltas:
        return 300
    deltas.sort()
    return int(deltas[len(deltas) // 2])


def _zone(
    kind: str,
    direction: str,
    label: str,
    start_time: int,
    end_time: int,
    top: float,
    bottom: float,
    fill: str,
    border: str,
    text: str,
    border_style: str,
) -> dict:
    return {
        "kind": kind,
        "direction": direction,
        "label": label,
        "startTime": int(start_time),
        "endTime": int(end_time),
        "top": float(max(top, bottom)),
        "bottom": float(min(top, bottom)),
        "fill": fill,
        "border": border,
        "text": text,
        "borderStyle": border_style,
    }


def _swing_points(df: pd.DataFrame, lookback: int = 2) -> tuple[list[tuple[pd.Timestamp, float]], list[tuple[pd.Timestamp, float]]]:
    highs: list[tuple[pd.Timestamp, float]] = []
    lows: list[tuple[pd.Timestamp, float]] = []
    for i in range(lookback, len(df) - lookback):
        window = df.iloc[i - lookback : i + lookback + 1]
        row = df.iloc[i]
        ts = df.index[i]
        if row["high"] == window["high"].max():
            highs.append((ts, float(row["high"])))
        if row["low"] == window["low"].min():
            lows.append((ts, float(row["low"])))
    return highs, lows


def market_structure(df: pd.DataFrame, lookback: int = 9, liquidity_lookback: int = 30, show_liquidity: bool = True) -> dict[str, list[dict]]:
    swing_highs, swing_lows = _swing_points(df, lookback)
    markers: list[dict] = []
    levels: list[dict] = []
    last_state: str | None = None
    last_high: tuple[pd.Timestamp, float] | None = None
    last_low: tuple[pd.Timestamp, float] | None = None
    high_broken = False
    low_broken = False
    swing_high_map = {point[0]: point for point in swing_highs}
    swing_low_map = {point[0]: point for point in swing_lows}

    for ts, row in df.iterrows():
        close = float(row["close"])
        if ts in swing_high_map:
            last_high = swing_high_map[ts]
            high_broken = False
        if ts in swing_low_map:
            last_low = swing_low_map[ts]
            low_broken = False

        if last_high and not high_broken and close > last_high[1]:
            label = "CHoCH" if last_state in {None, "down"} else "BoS"
            last_state = "up"
            high_broken = True
            markers.append(
                {
                    "time": int(ts.timestamp()),
                    "position": "aboveBar",
                    "color": "#16a34a",
                    "shape": "arrowUp",
                    "text": f"{label} up",
                }
            )
            levels.append(
                {
                    "startTime": int(last_high[0].timestamp()),
                    "endTime": int(ts.timestamp()),
                    "labelTime": int((last_high[0].timestamp() + ts.timestamp()) / 2),
                    "time": int(ts.timestamp()),
                    "price": last_high[1],
                    "label": label,
                    "color": "#16a34a",
                }
            )
        if last_low and not low_broken and close < last_low[1]:
            label = "CHoCH" if last_state in {None, "up"} else "BoS"
            last_state = "down"
            low_broken = True
            markers.append(
                {
                    "time": int(ts.timestamp()),
                    "position": "belowBar",
                    "color": "#dc2626",
                    "shape": "arrowDown",
                    "text": f"{label} down",
                }
            )
            levels.append(
                {
                    "startTime": int(last_low[0].timestamp()),
                    "endTime": int(ts.timestamp()),
                    "labelTime": int((last_low[0].timestamp() + ts.timestamp()) / 2),
                    "time": int(ts.timestamp()),
                    "price": last_low[1],
                    "label": label,
                    "color": "#dc2626",
                }
            )

    liquidity_levels, liquidity_markers = _liquidity_sweeps(df, liquidity_lookback) if show_liquidity else ([], [])
    return {
        "markers": (markers + liquidity_markers)[-120:],
        "levels": (levels + liquidity_levels)[-120:],
    }


def _liquidity_sweeps(df: pd.DataFrame, lookback: int = 30) -> tuple[list[dict], list[dict]]:
    swing_highs, swing_lows = _swing_points(df, lookback)
    pending_highs = [{"time": ts, "price": price, "broken": False} for ts, price in swing_highs[-12:]]
    pending_lows = [{"time": ts, "price": price, "broken": False} for ts, price in swing_lows[-12:]]
    levels: list[dict] = []
    markers: list[dict] = []

    for ts, row in df.iterrows():
        high = float(row["high"])
        low = float(row["low"])
        close = float(row["close"])

        for level in pending_highs:
            if level["broken"] or ts <= level["time"]:
                continue
            price = float(level["price"])
            if high > price:
                level["broken"] = True
                levels.append(
                    {
                        "startTime": int(level["time"].timestamp()),
                        "endTime": int(ts.timestamp()),
                        "labelTime": int((level["time"].timestamp() + ts.timestamp()) / 2),
                        "time": int(ts.timestamp()),
                        "price": price,
                        "label": "Liquidity",
                        "color": "#dc2626",
                        "style": "dashed",
                    }
                )
                if close < price:
                    markers.append(
                        {
                            "time": int(ts.timestamp()),
                            "position": "aboveBar",
                            "color": "#a855f7",
                            "shape": "circle",
                            "text": "x",
                        }
                    )

        for level in pending_lows:
            if level["broken"] or ts <= level["time"]:
                continue
            price = float(level["price"])
            if low < price:
                level["broken"] = True
                levels.append(
                    {
                        "startTime": int(level["time"].timestamp()),
                        "endTime": int(ts.timestamp()),
                        "labelTime": int((level["time"].timestamp() + ts.timestamp()) / 2),
                        "time": int(ts.timestamp()),
                        "price": price,
                        "label": "Liquidity",
                        "color": "#14b8a6",
                        "style": "dashed",
                    }
                )
                if close > price:
                    markers.append(
                        {
                            "time": int(ts.timestamp()),
                            "position": "belowBar",
                            "color": "#14b8a6",
                            "shape": "circle",
                            "text": "x",
                        }
                    )

    return levels[-30:], markers[-30:]


def volume_delta(df: pd.DataFrame) -> dict[str, float]:
    up_volume = df.loc[df["close"] >= df["open"], "volume"].sum()
    down_volume = df.loc[df["close"] < df["open"], "volume"].sum()
    total = float(up_volume + down_volume)
    return {
        "buy_volume": float(up_volume),
        "sell_volume": float(down_volume),
        "delta": float(up_volume - down_volume),
        "delta_pct": float(((up_volume - down_volume) / total) * 100) if total else 0.0,
    }
