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


def cpr(df: pd.DataFrame, show_pivots: bool = True) -> dict[str, list[dict]]:
    clean = df[~df.index.duplicated(keep="last")].sort_index()
    if clean.empty:
        return {"levels": []}

    dates = pd.Series(clean.index.date, index=clean.index)
    unique_dates = list(dict.fromkeys(dates.tolist()))
    if len(unique_dates) < 2:
        return {"levels": []}

    current_date = unique_dates[-1]
    previous_date = unique_dates[-2]
    previous = clean[dates == previous_date]
    current = clean[dates == current_date]
    if previous.empty or current.empty:
        return {"levels": []}

    previous_high = float(pd.to_numeric(previous["high"], errors="coerce").max())
    previous_low = float(pd.to_numeric(previous["low"], errors="coerce").min())
    previous_close = float(pd.to_numeric(previous["close"], errors="coerce").iloc[-1])
    if not all(pd.notna(value) for value in [previous_high, previous_low, previous_close]):
        return {"levels": []}

    pivot = (previous_high + previous_low + previous_close) / 3
    bc = (previous_high + previous_low) / 2
    tc = (pivot * 2) - bc
    top_cpr = max(tc, bc)
    bottom_cpr = min(tc, bc)
    start_time = int(current.index[0].timestamp())
    end_time = int(current.index[-1].timestamp())

    levels = [
        _cpr_level("TC", top_cpr, start_time, end_time, "#7c3aed", 3),
        _cpr_level("P", pivot, start_time, end_time, "#f59e0b", 3),
        _cpr_level("BC", bottom_cpr, start_time, end_time, "#7c3aed", 3),
    ]

    if show_pivots:
        r1 = (2 * pivot) - previous_low
        s1 = (2 * pivot) - previous_high
        r2 = pivot + (previous_high - previous_low)
        s2 = pivot - (previous_high - previous_low)
        r3 = previous_high + (2 * (pivot - previous_low))
        s3 = previous_low - (2 * (previous_high - pivot))
        levels.extend(
            [
                _cpr_level("R1", r1, start_time, end_time, "#ef4444", 2),
                _cpr_level("R2", r2, start_time, end_time, "#ef4444", 2),
                _cpr_level("R3", r3, start_time, end_time, "#ef4444", 2),
                _cpr_level("S1", s1, start_time, end_time, "#14a889", 2),
                _cpr_level("S2", s2, start_time, end_time, "#14a889", 2),
                _cpr_level("S3", s3, start_time, end_time, "#14a889", 2),
            ]
        )

    return {"levels": levels}


def _cpr_level(label: str, price: float, start_time: int, end_time: int, color: str, width: int) -> dict:
    return {
        "label": label,
        "price": float(price),
        "startTime": int(start_time),
        "endTime": int(end_time),
        "color": color,
        "width": int(width),
    }


def angle_market(
    df: pd.DataFrame,
    length: int = 5,
    angle: float = 0.1,
    deviation_size: float = 1.0,
) -> dict[str, list[dict]]:
    clean = df[~df.index.duplicated(keep="last")].sort_index()
    if len(clean) < max(length * 2 + 5, 20):
        return {"lines": [], "labels": []}

    rows = clean.reset_index().rename(columns={clean.reset_index().columns[0]: "datetime"})
    atr = _atr(clean, 200).reset_index(drop=True)
    lines: list[dict] = []
    labels: list[dict] = []
    highs: list[dict] = []
    lows: list[dict] = []
    ph_val: float | None = None
    ph_point: dict | None = None
    pl_val: float | None = None
    pl_point: dict | None = None
    count_up = 0
    count_down = 0
    latest_deviation: list[dict] = []

    for i, row in rows.iterrows():
        time_value = int(row["datetime"].timestamp())
        high = float(row["high"])
        low = float(row["low"])
        step = float(atr.iloc[min(i, len(atr) - 1)] or 0) * float(angle)
        deviation = float(atr.iloc[min(i, len(atr) - 1)] or 0) * float(deviation_size)

        pivot_index = i - length
        if pivot_index >= length and i >= length * 2:
            window = rows.iloc[pivot_index - length : pivot_index + length + 1]
            pivot = rows.iloc[pivot_index]
            pivot_time = int(pivot["datetime"].timestamp())
            pivot_high = float(pivot["high"])
            pivot_low = float(pivot["low"])

            if pivot_high == float(window["high"].max()):
                structure = "HH" if highs and pivot_high > highs[-1]["price"] else "LH" if highs else "H"
                point = {"index": pivot_index, "time": pivot_time, "price": pivot_high, "structure": structure}
                highs.append(point)
                ph_val = pivot_high
                ph_point = point
                labels.append(_angle_label(point, "anglePivotHigh", "#14b8a6"))

            if pivot_low == float(window["low"].min()):
                structure = "HL" if lows and pivot_low > lows[-1]["price"] else "LL" if lows else "L"
                point = {"index": pivot_index, "time": pivot_time, "price": pivot_low, "structure": structure}
                lows.append(point)
                pl_val = pivot_low
                pl_point = point
                labels.append(_angle_label(point, "anglePivotLow", "#be185d"))

        if ph_val is not None and ph_point is not None:
            ph_val -= step
            if high > ph_val:
                count_up += 1
                count_down = 0
                lines.append(
                    {
                        "startTime": ph_point["time"],
                        "startPrice": ph_point["price"],
                        "endTime": time_value,
                        "endPrice": ph_val,
                        "color": "#14b8a6",
                        "width": 2,
                    }
                )
                labels.append(
                    {
                        "time": ph_point["time"],
                        "price": ph_point["price"],
                        "text": f"{ph_point['structure']} {count_up}",
                        "tone": "angleHigh",
                    }
                )
                latest_deviation = _angle_deviation_lines(time_value, ph_val, deviation, "up")
                ph_val = None
                ph_point = None

        if pl_val is not None and pl_point is not None:
            pl_val += step
            if low < pl_val:
                count_down += 1
                count_up = 0
                lines.append(
                    {
                        "startTime": pl_point["time"],
                        "startPrice": pl_point["price"],
                        "endTime": time_value,
                        "endPrice": pl_val,
                        "color": "#be185d",
                        "width": 2,
                    }
                )
                labels.append(
                    {
                        "time": pl_point["time"],
                        "price": pl_point["price"],
                        "text": f"{pl_point['structure']} {count_down}",
                        "tone": "angleLow",
                    }
                )
                latest_deviation = _angle_deviation_lines(time_value, pl_val, deviation, "down")
                pl_val = None
                pl_point = None

    last_time = int(clean.index[-1].timestamp())
    future_time = last_time + (_infer_time_step([int(ts.timestamp()) for ts in clean.index]) * 5)
    for item in latest_deviation:
        item["endTime"] = future_time
        item["labelTime"] = future_time

    return {
        "lines": lines[-80:] + latest_deviation,
        "labels": labels[-160:],
    }


def _angle_label(point: dict, tone: str, color: str) -> dict:
    return {
        "time": point["time"],
        "price": point["price"],
        "text": "",
        "tone": tone,
        "color": color,
    }


def _angle_deviation_lines(start_time: int, base: float, deviation: float, direction: str) -> list[dict]:
    if deviation <= 0:
        return []
    sign = 1 if direction == "up" else -1
    items = []
    for multiple in [1, 2, 3]:
        price = base + (deviation * multiple * sign)
        items.append(
            {
                "startTime": start_time,
                "endTime": start_time,
                "startPrice": price,
                "endPrice": price,
                "color": "#111827",
                "width": 1,
                "style": "dashed" if multiple == 2 else "solid",
                "deviationLabel": f"{'+' if sign > 0 else '-'}{multiple}",
            }
        )
    return items


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
    clean = df[~df.index.duplicated(keep="last")].sort_index()
    rows = clean.reset_index()
    rows = rows.rename(columns={rows.columns[0]: "datetime"})
    if len(rows) < max(lookback * 2, 5):
        liquidity_levels, liquidity_markers = _liquidity_sweeps(clean, liquidity_lookback) if show_liquidity else ([], [])
        return {"markers": liquidity_markers, "levels": liquidity_levels, "zones": [], "trendLines": []}

    atr = _atr(clean, 14).reset_index(drop=True)
    markers: list[dict] = []
    levels: list[dict] = []
    high_points: list[dict] = []
    low_points: list[dict] = []
    bullish_orderblocks: list[dict] = []
    bearish_orderblocks: list[dict] = []
    trend = 1
    draw_up = False
    draw_down = False
    last_state: str | None = None

    for i, row in rows.iterrows():
        ts = row["datetime"]
        time_value = int(ts.timestamp())
        high = float(row["high"])
        low = float(row["low"])
        close = float(row["close"])

        if i >= lookback:
            pivot_index = i - lookback
            pivot = rows.iloc[pivot_index]
            recent = rows.iloc[max(0, i - lookback + 1) : i + 1]
            to_up = float(pivot["high"]) >= float(recent["high"].max())
            to_down = float(pivot["low"]) <= float(recent["low"].min())
        else:
            pivot_index = -1
            pivot = None
            to_up = False
            to_down = False

        previous_trend = trend
        if trend == 1 and to_down:
            trend = -1
        elif trend == -1 and to_up:
            trend = 1

        if pivot is not None and trend != previous_trend and trend == 1:
            high_points.append(
                {
                    "index": pivot_index,
                    "time": int(pivot["datetime"].timestamp()),
                    "price": float(pivot["high"]),
                }
            )
            draw_up = False

        if pivot is not None and trend != previous_trend and trend == -1:
            low_points.append(
                {
                    "index": pivot_index,
                    "time": int(pivot["datetime"].timestamp()),
                    "price": float(pivot["low"]),
                }
            )
            draw_down = False

        for block in list(bullish_orderblocks):
            block["endTime"] = time_value
            if close < block["value"]:
                bullish_orderblocks.remove(block)
        for block in list(bearish_orderblocks):
            block["endTime"] = time_value
            if close > block["value"]:
                bearish_orderblocks.remove(block)

        if len(low_points) > 1 and not draw_down:
            last_low = low_points[-1]
            if close < last_low["price"]:
                label = "CHoCH" if last_state in {None, "up"} else "BoS"
                levels.append(_structure_level(last_low, time_value, label, "#ef4444"))
                draw_down = True
                last_state = "down"
                block = _bearish_pa_orderblock(rows, atr, int(last_low["index"]), i, time_value)
                if block:
                    bearish_orderblocks.append(block)
                    bearish_orderblocks = bearish_orderblocks[-20:]

        if len(high_points) > 1 and not draw_up:
            last_high = high_points[-1]
            if close > last_high["price"]:
                label = "CHoCH" if last_state in {None, "down"} else "BoS"
                levels.append(_structure_level(last_high, time_value, label, "#14a889"))
                draw_up = True
                last_state = "up"
                block = _bullish_pa_orderblock(rows, atr, int(last_high["index"]), i, time_value)
                if block:
                    bullish_orderblocks.append(block)
                    bullish_orderblocks = bullish_orderblocks[-20:]

    liquidity_levels, liquidity_markers = _liquidity_sweeps(clean, liquidity_lookback) if show_liquidity else ([], [])
    zones = bullish_orderblocks[-2:] + bearish_orderblocks[-2:]
    return {
        "markers": liquidity_markers[-60:],
        "levels": (levels + liquidity_levels)[-120:],
        "zones": zones,
        "trendLines": _pa_trend_lines(clean, 20),
    }


def _structure_level(point: dict, end_time: int, label: str, color: str) -> dict:
    return {
        "startTime": int(point["time"]),
        "endTime": int(end_time),
        "labelTime": int((int(point["time"]) + int(end_time)) / 2),
        "time": int(end_time),
        "price": float(point["price"]),
        "label": label,
        "color": color,
        "style": "solid",
    }


def _atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    high = pd.to_numeric(df["high"], errors="coerce")
    low = pd.to_numeric(df["low"], errors="coerce")
    close = pd.to_numeric(df["close"], errors="coerce")
    previous_close = close.shift(1)
    true_range = pd.concat(
        [(high - low), (high - previous_close).abs(), (low - previous_close).abs()],
        axis=1,
    ).max(axis=1)
    return true_range.ewm(alpha=1 / period, adjust=False, min_periods=1).mean()


def _bearish_pa_orderblock(rows: pd.DataFrame, atr: pd.Series, start_index: int, end_index: int, end_time: int) -> dict | None:
    if start_index < 0 or end_index <= start_index:
        return None
    window = rows.iloc[start_index : end_index + 1]
    if window.empty:
        return None
    max_pos = int(window["high"].astype(float).idxmax())
    value = float(rows.iloc[max_pos]["high"])
    height = float(atr.iloc[min(max_pos, len(atr) - 1)] or 0)
    if height <= 0:
        height = max(value * 0.0005, 1.0)
    return _zone(
        kind="pa-ob",
        direction="bearish",
        label="",
        start_time=int(rows.iloc[max_pos]["datetime"].timestamp()),
        end_time=end_time,
        top=value,
        bottom=value - height,
        fill="rgba(239,68,68,0.14)",
        border="rgba(239,68,68,0.68)",
        text="rgba(239,68,68,0.92)",
        border_style="solid",
    ) | {"value": value}


def _bullish_pa_orderblock(rows: pd.DataFrame, atr: pd.Series, start_index: int, end_index: int, end_time: int) -> dict | None:
    if start_index < 0 or end_index <= start_index:
        return None
    window = rows.iloc[start_index : end_index + 1]
    if window.empty:
        return None
    min_pos = int(window["low"].astype(float).idxmin())
    value = float(rows.iloc[min_pos]["low"])
    height = float(atr.iloc[min(min_pos, len(atr) - 1)] or 0)
    if height <= 0:
        height = max(value * 0.0005, 1.0)
    return _zone(
        kind="pa-ob",
        direction="bullish",
        label="",
        start_time=int(rows.iloc[min_pos]["datetime"].timestamp()),
        end_time=end_time,
        top=value + height,
        bottom=value,
        fill="rgba(20,184,166,0.14)",
        border="rgba(20,184,166,0.68)",
        text="rgba(20,184,166,0.92)",
        border_style="solid",
    ) | {"value": value}


def _pa_trend_lines(df: pd.DataFrame, length: int = 30) -> list[dict]:
    lookback = max(10, int(length))
    highs, lows = _swing_points(df, lookback)
    lines: list[dict] = []
    if len(highs) >= 2:
        start, end = highs[-2], highs[-1]
        if end[1] < start[1]:
            lines.append(_extended_trend_line(df, start, end, "rgba(239,68,68,0.72)"))
    if len(lows) >= 2:
        start, end = lows[-2], lows[-1]
        if end[1] > start[1]:
            lines.append(_extended_trend_line(df, start, end, "rgba(20,184,166,0.78)"))
    return lines


def _extended_trend_line(df: pd.DataFrame, start: tuple[pd.Timestamp, float], end: tuple[pd.Timestamp, float], color: str) -> dict:
    start_ts, start_value = start
    end_ts, end_value = end
    end_time = int(df.index[-1].timestamp())
    start_time = int(start_ts.timestamp())
    pivot_end_time = int(end_ts.timestamp())
    if pivot_end_time == start_time:
        projected = end_value
    else:
        slope = (end_value - start_value) / (pivot_end_time - start_time)
        projected = start_value + (slope * (end_time - start_time))
    return {
        "startTime": start_time,
        "startPrice": float(start_value),
        "endTime": end_time,
        "endPrice": float(projected),
        "color": color,
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
