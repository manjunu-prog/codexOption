"""Option Terminal Pro."""

import json
from pathlib import Path

import pandas as pd
import streamlit as st
from streamlit_autorefresh import st_autorefresh

from api.alerts import TelegramNotifier, app_login_code, format_signal_time, signal_key
from api.fyers_login import FyersLogin
from api.historical import HistoricalData
from api.option_chain import OptionChain
from chart.chart import TradingChart
from config import APP_NAME, FYERS, INDEX_CONFIG, TIMEFRAMES
from indicators.core import angle_market, alphatrend, cpr, ema, fvg_ifvg_order_blocks, market_structure, volume_delta, vwap

st.set_page_config(page_title=APP_NAME, layout="wide")

DATA_DIR = Path(__file__).parent / "data"
DATA_DIR.mkdir(exist_ok=True)
PREFERENCES_FILE = DATA_DIR / "last_activity.json"
INDICATOR_OPTIONS = ["AlphaTrend", "EMA", "VWAP", "CPR", "Angle Market", "FVG", "iFVG", "Order Blocks", "PA Toolkit"]
TOP_SPOT_QUOTES = {
    "CRUDEOIL": "MCX:CRUDEOIL26JULFUT",
    "BANKNIFTY": INDEX_CONFIG["BANKNIFTY"]["spot"],
    "SENSEX": INDEX_CONFIG["SENSEX"]["spot"],
}


def secrets_value(key: str, default: str = "") -> str:
    try:
        return st.secrets.get(key, default)
    except Exception:
        return default


def load_preferences() -> dict:
    if not PREFERENCES_FILE.exists():
        return {}
    try:
        return json.loads(PREFERENCES_FILE.read_text())
    except Exception:
        return {}


def save_preferences(values: dict) -> None:
    try:
        PREFERENCES_FILE.write_text(json.dumps(values, indent=2, sort_keys=True))
    except Exception:
        pass


def option_index(options: list, value, default: int = 0) -> int:
    try:
        return options.index(value)
    except ValueError:
        return default


def valid_options(options: list, values, default: list):
    if not isinstance(values, list):
        return default
    selected = [value for value in values if value in options]
    return selected or default


def preference_number(preferences: dict, key: str, default):
    value = preferences.get(key, default)
    return default if value is None else value


def require_login() -> None:
    code = app_login_code()
    if not code:
        return

    if st.session_state.get("app_unlocked"):
        return

    st.title("Option Terminal Pro")
    st.subheader("Enter access code")
    entered = st.text_input("Access code", type="password", max_chars=max(6, len(code)))
    if st.button("Unlock", width="stretch"):
        if entered == code:
            st.session_state["app_unlocked"] = True
            st.rerun()
        else:
            st.error("Invalid access code.")
    st.stop()


require_login()
st.title("Option Terminal Pro")
preferences = load_preferences()


def credentials_from_sidebar() -> dict:
    with st.sidebar.expander("FYERS Login", expanded=False):
        return {
            "FY_ID": st.text_input("Fyers ID", value=secrets_value("FYERS_FY_ID", FYERS["FY_ID"])),
            "PIN": st.text_input("PIN", value=secrets_value("FYERS_PIN", FYERS["PIN"]), type="password"),
            "TOTP_KEY": st.text_input("TOTP Key", value=secrets_value("FYERS_TOTP_KEY", FYERS["TOTP_KEY"]), type="password"),
            "APP_ID": st.text_input("App ID", value=secrets_value("FYERS_APP_ID", FYERS["APP_ID"])),
            "APP_SECRET": st.text_input(
                "App Secret",
                value=secrets_value("FYERS_APP_SECRET", FYERS["APP_SECRET"]),
                type="password",
            ),
            "REDIRECT_URI": st.text_input(
                "Redirect URI",
                value=secrets_value("FYERS_REDIRECT_URI", FYERS["REDIRECT_URI"]),
            ),
        }


@st.cache_resource(show_spinner=False)
def get_client(credentials: dict):
    return FyersLogin(credentials=credentials).get_client()


@st.cache_data(ttl=20, show_spinner=False)
def load_candles(_client, symbol: str, resolution: str, days: int, refresh_nonce: int = 0) -> pd.DataFrame:
    return HistoricalData(client=_client).get_candles(symbol, resolution, days)


@st.cache_data(ttl=8, show_spinner=False)
def load_chain(_client, symbol: str, strikecount: int) -> pd.DataFrame:
    return OptionChain(_client).fetch(symbol, strikecount=strikecount)


@st.cache_data(ttl=8, show_spinner=False)
def load_quotes(_client, symbols: list[str]) -> dict[str, float]:
    response = _client.quotes(data={"symbols": ",".join(symbols)})
    if response.get("s") != "ok":
        return {}
    quotes = {}
    for item in response.get("d", []):
        symbol = item.get("n")
        value = item.get("v", {})
        if symbol and value.get("lp") is not None:
            quotes[symbol] = float(value["lp"])
    return quotes


@st.cache_resource(show_spinner=False)
def get_notifier() -> TelegramNotifier:
    return TelegramNotifier()


def timeframe_seconds(resolution: str) -> int:
    if resolution == "D":
        return 24 * 60 * 60
    try:
        return int(resolution) * 60
    except Exception:
        return 300


def compact_number(value: float | int | None) -> str:
    if value is None or pd.isna(value):
        return "-"
    value = float(value)
    sign = "-" if value < 0 else ""
    value = abs(value)
    if value >= 10_000_000:
        return f"{sign}{value / 10_000_000:.2f}Cr"
    if value >= 100_000:
        return f"{sign}{value / 100_000:.2f}L"
    if value >= 1_000:
        return f"{sign}{value / 1_000:.2f}K"
    return f"{sign}{value:.0f}"


def percent_text(value: float | int | None) -> str:
    if value is None or pd.isna(value):
        return "-"
    return f"{float(value):,.2f}%"


def oi_change_percent(oi: float, oi_change: float, fallback_pct: float | None = None) -> float | None:
    if fallback_pct is not None and not pd.isna(fallback_pct) and float(fallback_pct) != 0:
        return float(fallback_pct)
    previous_oi = float(oi) - float(oi_change)
    if previous_oi == 0:
        return None
    return (float(oi_change) / previous_oi) * 100


def option_side_stats(row: pd.Series | None) -> dict:
    if row is None or row.empty:
        return {"ltp": None, "oi": None, "oi_change": None, "oi_change_pct": None, "volume": None}
    oi = float(row.get("oi", 0) or 0)
    oi_change = float(row.get("oi_change", 0) or 0)
    return {
        "ltp": float(row.get("ltp", 0) or 0),
        "oi": oi,
        "oi_change": oi_change,
        "oi_change_pct": oi_change_percent(oi, oi_change, row.get("oi_change_pct")),
        "volume": float(row.get("volume", 0) or 0),
    }


def strike_stats(chain_df: pd.DataFrame, strike: int | None) -> dict[str, dict]:
    empty_stats = {"CE": option_side_stats(None), "PE": option_side_stats(None)}
    if chain_df.empty or strike is None:
        return empty_stats
    stats = {}
    for side in ("CE", "PE"):
        rows = chain_df[(chain_df["strike"] == strike) & (chain_df["type"] == side)]
        stats[side] = option_side_stats(rows.iloc[0] if not rows.empty else None)
    return stats


def total_oi_change_stats(chain_df: pd.DataFrame) -> dict[str, dict]:
    stats = {"CE": {"oi_change": None, "oi_change_pct": None}, "PE": {"oi_change": None, "oi_change_pct": None}}
    if chain_df.empty:
        return stats
    for side in ("CE", "PE"):
        rows = chain_df[chain_df["type"] == side]
        if rows.empty:
            continue
        oi = float(rows["oi"].sum())
        oi_change = float(rows["oi_change"].sum()) if "oi_change" in rows else 0.0
        previous_oi = oi - oi_change
        stats[side] = {
            "oi_change": oi_change,
            "oi_change_pct": (oi_change / previous_oi) * 100 if previous_oi else None,
        }
    return stats


def render_index_oi_summary(chain_df: pd.DataFrame) -> None:
    stats = total_oi_change_stats(chain_df)
    st.caption("Total OI Change")
    cols = st.columns(2)
    for col, side in zip(cols, ("CE", "PE")):
        item = stats[side]
        col.metric(
            f"{side} OI Chg",
            percent_text(item["oi_change_pct"]),
            compact_number(item["oi_change"]),
        )


def render_strike_oi_summary(chain_df: pd.DataFrame, strike: int | None) -> None:
    stats = strike_stats(chain_df, strike)
    st.caption(f"Strike {strike or '-'} OI / Volume")
    cols = st.columns(2)
    for col, side in zip(cols, ("CE", "PE")):
        item = stats[side]
        col.metric(
            f"{side} OI Chg",
            percent_text(item["oi_change_pct"]),
            f"Vol {compact_number(item['volume'])} | OI {compact_number(item['oi'])}",
        )


with st.sidebar:
    st.header("Market")
    index_options = list(INDEX_CONFIG.keys())
    timeframe_options = list(TIMEFRAMES.keys())
    index_name = st.selectbox(
        "Index",
        index_options,
        index=option_index(index_options, preferences.get("index_name"), 0),
        key="index_name",
    )
    tf_label = st.selectbox(
        "Timeframe",
        timeframe_options,
        index=option_index(timeframe_options, preferences.get("tf_label"), 3),
        key="tf_label",
    )
    days = st.slider("History days", 1, 30, int(preference_number(preferences, "days", 5)), key="days")
    latest_session_only = st.toggle(
        "Latest session only",
        value=bool(preferences.get("latest_session_only", True)),
        key="latest_session_only",
    )
    strike_window = st.slider(
        "Strike window",
        5,
        40,
        int(preference_number(preferences, "strike_window", INDEX_CONFIG[index_name]["strikecount"])),
        key="strike_window",
    )
    auto_refresh = st.toggle("Auto refresh", value=bool(preferences.get("auto_refresh", True)), key="auto_refresh")
    refresh_seconds = st.slider(
        "Refresh seconds",
        5,
        120,
        int(preference_number(preferences, "refresh_seconds", 30)),
        key="refresh_seconds",
    )

credentials = credentials_from_sidebar()

if auto_refresh:
    st_autorefresh(interval=refresh_seconds * 1000, key="terminal_refresh")

missing = [key for key, value in credentials.items() if not value and key != "REDIRECT_URI"]
if missing:
    st.info("Add FYERS credentials in the sidebar or set FYERS_* environment variables.")
    st.stop()

try:
    client = get_client(credentials)
except Exception as exc:
    st.error(f"FYERS login failed: {exc}")
    st.stop()

top_quotes = load_quotes(client, list(TOP_SPOT_QUOTES.values()))
top_quote_cols = st.columns(len(TOP_SPOT_QUOTES))
for col, (name, symbol) in zip(top_quote_cols, TOP_SPOT_QUOTES.items()):
    price = top_quotes.get(symbol)
    col.metric(name, f"{price:,.2f}" if price is not None else "-")

index_cfg = INDEX_CONFIG[index_name]
spot_symbol = index_cfg["spot"]

try:
    chain_df = load_chain(client, spot_symbol, strike_window)
except Exception as exc:
    st.error(f"Option-chain fetch failed: {exc}")
    chain_df = pd.DataFrame()

atm = None
spot_ltp = None
try:
    quote = client.quotes(data={"symbols": spot_symbol})
    if quote.get("s") == "ok" and quote.get("d"):
        spot_ltp = float(quote["d"][0]["v"]["lp"])
        atm = round(spot_ltp / index_cfg["step"]) * index_cfg["step"]
except Exception:
    pass

selected_symbol = spot_symbol
selected_ce_strike = None
selected_pe_strike = None
index_chart_spec = {"title": "Index", "symbol": spot_symbol, "label": index_name, "chart_id": f"{index_name}:INDEX"}
ce_chart_spec = None
pe_chart_spec = None

show_ema = False
ema_periods = [20]
show_vwap = False
show_cpr = False
show_cpr_pivots = True
show_angle_market = False
angle_market_length = 5
angle_market_angle = 0.1
angle_market_deviation = 1.0
show_alphatrend = True
alphatrend_period = 14
alphatrend_coeff = 1.0
show_fvg = False
show_ifvg = False
show_ob = False
show_structure = False
structure_len = 9
show_liquidity = False
liquidity_len = 30

if not chain_df.empty:
    st.subheader("Strikes")
    strikes = sorted(chain_df["strike"].unique().tolist())
    default_idx = strikes.index(atm) if atm in strikes else len(strikes) // 2
    ce_default_idx = option_index(strikes, preferences.get("selected_ce_strike"), default_idx)
    pe_default_idx = option_index(strikes, preferences.get("selected_pe_strike"), default_idx)
    strike_cols = st.columns(2)
    selected_ce_strike = strike_cols[0].radio(
        "CE strike",
        strikes,
        index=ce_default_idx,
        key="ce_strike_main",
    )
    selected_pe_strike = strike_cols[1].radio(
        "PE strike",
        strikes,
        index=pe_default_idx,
        key="pe_strike_main",
    )

    ce_row = chain_df[(chain_df["strike"] == selected_ce_strike) & (chain_df["type"] == "CE")]
    if not ce_row.empty:
        ce_chart_spec = {
            "title": "CE",
            "symbol": ce_row.iloc[0]["symbol"],
            "label": f"{index_name} {selected_ce_strike} CE",
            "chart_id": f"{index_name}:CE",
        }

    pe_row = chain_df[(chain_df["strike"] == selected_pe_strike) & (chain_df["type"] == "PE")]
    if not pe_row.empty:
        pe_chart_spec = {
            "title": "PE",
            "symbol": pe_row.iloc[0]["symbol"],
            "label": f"{index_name} {selected_pe_strike} PE",
            "chart_id": f"{index_name}:PE",
        }

st.subheader("Indicators")
saved_indicators = preferences.get("selected_indicators", ["AlphaTrend"])
if isinstance(saved_indicators, str):
    saved_indicators = [saved_indicators] if saved_indicators in INDICATOR_OPTIONS else ["AlphaTrend"]
saved_indicators = [item for item in saved_indicators if item in INDICATOR_OPTIONS] or ["AlphaTrend"]
selected_indicators = st.multiselect(
    "Indicators",
    INDICATOR_OPTIONS,
    default=saved_indicators,
    key="selected_indicators_main",
)

show_alphatrend = "AlphaTrend" in selected_indicators
show_ema = "EMA" in selected_indicators
show_vwap = "VWAP" in selected_indicators
show_cpr = "CPR" in selected_indicators
show_angle_market = "Angle Market" in selected_indicators
show_fvg = "FVG" in selected_indicators
show_ifvg = "iFVG" in selected_indicators
show_ob = "Order Blocks" in selected_indicators
show_structure = "PA Toolkit" in selected_indicators

if show_ema:
    ema_options = [9, 20, 50, 100, 200]
    ema_periods = st.multiselect(
        "EMA periods",
        ema_options,
        default=valid_options(ema_options, preferences.get("ema_periods", [20]), [20]),
        key="ema_periods_main",
    )
if show_cpr:
    show_cpr_pivots = st.checkbox(
        "Show R/S levels",
        value=bool(preferences.get("show_cpr_pivots", True)),
        key="cpr_pivots_main",
    )
if show_alphatrend:
    alpha_cols = st.columns(2)
    alphatrend_period = alpha_cols[0].number_input(
        "Period",
        min_value=1,
        max_value=100,
        value=int(preference_number(preferences, "alphatrend_period", 14)),
        key="alphatrend_period_main",
    )
    alphatrend_coeff = alpha_cols[1].number_input(
        "Multiplier",
        min_value=0.1,
        max_value=10.0,
        value=float(preference_number(preferences, "alphatrend_coeff", 1.0)),
        step=0.1,
        key="alphatrend_coeff_main",
    )
if show_angle_market:
    angle_cols = st.columns(3)
    angle_market_length = angle_cols[0].number_input(
        "Length",
        min_value=2,
        max_value=50,
        value=int(preference_number(preferences, "angle_market_length", 5)),
        key="angle_market_length_main",
    )
    angle_market_angle = angle_cols[1].number_input(
        "Angle",
        min_value=0.0,
        max_value=1.0,
        value=float(preference_number(preferences, "angle_market_angle", 0.1)),
        step=0.01,
        key="angle_market_angle_main",
    )
    angle_market_deviation = angle_cols[2].number_input(
        "Deviation",
        min_value=0.1,
        max_value=10.0,
        value=float(preference_number(preferences, "angle_market_deviation", 1.0)),
        step=0.1,
        key="angle_market_deviation_main",
    )
if show_structure:
    pa_cols = st.columns(3)
    structure_len = pa_cols[0].number_input(
        "Structure length",
        min_value=2,
        max_value=50,
        value=int(preference_number(preferences, "structure_len", 9)),
        key="structure_len_main",
    )
    show_liquidity = pa_cols[1].checkbox(
        "Show Liquidity Sweeps",
        value=bool(preferences.get("show_liquidity", False)),
        key="show_liquidity_main",
    )
    liquidity_len = pa_cols[2].number_input(
        "Liquidity length",
        min_value=5,
        max_value=100,
        value=int(preference_number(preferences, "liquidity_len", 30)),
        key="liquidity_len_main",
    )

save_preferences(
    {
        "index_name": index_name,
        "tf_label": tf_label,
        "days": int(days),
        "latest_session_only": bool(latest_session_only),
        "strike_window": int(strike_window),
        "auto_refresh": bool(auto_refresh),
        "refresh_seconds": int(refresh_seconds),
        "selected_ce_strike": int(selected_ce_strike) if selected_ce_strike is not None else None,
        "selected_pe_strike": int(selected_pe_strike) if selected_pe_strike is not None else None,
        "selected_indicators": list(selected_indicators),
        "ema_periods": [int(period) for period in ema_periods],
        "show_cpr_pivots": bool(show_cpr_pivots),
        "alphatrend_period": int(alphatrend_period),
        "alphatrend_coeff": float(alphatrend_coeff),
        "angle_market_length": int(angle_market_length),
        "angle_market_angle": float(angle_market_angle),
        "angle_market_deviation": float(angle_market_deviation),
        "structure_len": int(structure_len),
        "show_liquidity": bool(show_liquidity),
        "liquidity_len": int(liquidity_len),
    }
)


def build_overlays(df: pd.DataFrame) -> dict:
    visible_kinds = set()
    if show_fvg:
        visible_kinds.add("fvg")
    if show_ifvg:
        visible_kinds.add("ifvg")
    if show_ob:
        visible_kinds.add("ob")

    all_zones = fvg_ifvg_order_blocks(df) if visible_kinds or get_notifier().enabled else []
    zones = [zone for zone in all_zones if zone.get("kind") in visible_kinds]
    return {
        "emas": [{"period": period, "data": ema(df, period)} for period in ema_periods] if show_ema else [],
        "vwap": vwap(df) if show_vwap else None,
        "cpr": cpr(df, show_pivots=show_cpr_pivots) if show_cpr else None,
        "angle_market": angle_market(
            df,
            length=int(angle_market_length),
            angle=float(angle_market_angle),
            deviation_size=float(angle_market_deviation),
        )
        if show_angle_market
        else None,
        "alphatrend": alphatrend(
            df,
            period=int(alphatrend_period),
            coeff=float(alphatrend_coeff),
        )
        if show_alphatrend
        else None,
        "zones": zones,
        "alert_zones": all_zones,
        "structure": market_structure(
            df,
            lookback=int(structure_len),
            liquidity_lookback=int(liquidity_len),
            show_liquidity=show_liquidity,
        )
        if show_structure
        else None,
    }


def latest_session_df(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty or TIMEFRAMES[tf_label] == "D":
        return df
    latest_date = df.index.max().date()
    return df[df.index.date == latest_date]


def trim_overlays(overlays: dict, df: pd.DataFrame) -> dict:
    if df.empty:
        return overlays
    start_ts = int(df.index.min().timestamp())
    end_ts = int(df.index.max().timestamp())

    def point_in_session(item: dict) -> bool:
        timestamp = int(item.get("time") or item.get("startTime") or item.get("endTime") or 0)
        return start_ts <= timestamp <= end_ts

    def line_touches_session(item: dict) -> bool:
        start = int(item.get("startTime") or item.get("time") or 0)
        end = int(item.get("endTime") or item.get("time") or start)
        return end >= start_ts and start <= end_ts

    trimmed = dict(overlays)
    trimmed["emas"] = [
        {**item, "data": [point for point in item.get("data", []) if point_in_session(point)]}
        for item in overlays.get("emas", [])
    ]
    if overlays.get("vwap"):
        trimmed["vwap"] = [point for point in overlays["vwap"] if point_in_session(point)]
    if overlays.get("alphatrend"):
        trimmed["alphatrend"] = {
            key: [item for item in value if point_in_session(item)]
            for key, value in overlays["alphatrend"].items()
        }
    if overlays.get("angle_market"):
        trimmed["angle_market"] = {
            "lines": [item for item in overlays["angle_market"].get("lines", []) if line_touches_session(item)],
            "labels": [item for item in overlays["angle_market"].get("labels", []) if point_in_session(item)],
        }
    if overlays.get("zones"):
        trimmed["zones"] = [item for item in overlays["zones"] if line_touches_session(item)]
    if overlays.get("structure"):
        trimmed["structure"] = {
            "markers": [item for item in overlays["structure"].get("markers", []) if point_in_session(item)],
            "levels": [item for item in overlays["structure"].get("levels", []) if line_touches_session(item)],
            "zones": [item for item in overlays["structure"].get("zones", []) if line_touches_session(item)],
            "trendLines": [item for item in overlays["structure"].get("trendLines", []) if line_touches_session(item)],
        }
    return trimmed


def send_fresh_alerts(spec: dict, df: pd.DataFrame, overlays: dict) -> None:
    notifier = get_notifier()
    if not notifier.enabled or df.empty:
        return

    last_ts = int(df.index.max().timestamp())
    freshness = 10 * 60
    signals: list[dict] = []

    for marker in (overlays.get("alphatrend") or {}).get("markers", []):
        text = marker.get("text")
        timestamp = int(marker.get("time", 0) or 0)
        if text not in {"BUY", "SELL"} or timestamp < last_ts - freshness:
            continue
        signals.append(
            {
                "kind": text,
                "time": timestamp,
                "price": marker.get("price"),
            }
        )

    for level in (overlays.get("structure") or {}).get("levels", []):
        label = str(level.get("label", ""))
        timestamp = int(level.get("endTime") or level.get("time") or 0)
        if label not in {"BoS", "CHoCH"} or timestamp < last_ts - freshness:
            continue
        signals.append(
            {
                "kind": label,
                "time": timestamp,
                "price": level.get("price"),
            }
        )

    for zone in overlays.get("alert_zones") or []:
        if zone.get("kind") != "ob":
            continue
        timestamp = int(zone.get("endTime") or zone.get("startTime") or 0)
        if timestamp < last_ts - freshness:
            continue
        direction = zone.get("direction")
        label = "Bullish OB" if direction == "bullish" else "Bearish OB"
        signals.append(
            {
                "kind": label,
                "time": timestamp,
                "price": zone.get("bottom") if direction == "bullish" else zone.get("top"),
            }
        )

    for item in signals:
        key = signal_key(spec["chart_id"], spec["symbol"], item["kind"], item["time"], item.get("price"))
        price_text = f" @ {float(item['price']):,.2f}" if item.get("price") is not None else ""
        message = (
            f"Option Terminal Signal\n"
            f"{spec['label']} | {tf_label}\n"
            f"{item['kind']}{price_text}\n"
            f"{format_signal_time(item['time'])}"
        )
        notifier.send_repeating(
            {
                "signal_key": key,
                "symbol": spec["label"],
                "signal_type": item["kind"],
                "signal_time": item["time"],
                "message": message,
            }
        )


def render_market_chart(spec: dict, height: int = 520) -> tuple[pd.DataFrame, dict] | tuple[None, None]:
    chart_id = spec.get("chart_id", spec["label"])
    nonce_key = f"refresh_nonce:{chart_id}"
    if nonce_key not in st.session_state:
        st.session_state[nonce_key] = 0
    if st.button(f"Refresh {spec['title']}", key=f"refresh_button:{chart_id}"):
        st.session_state[nonce_key] += 1

    try:
        chart_df = load_candles(client, spec["symbol"], TIMEFRAMES[tf_label], days, st.session_state[nonce_key])
    except Exception as exc:
        st.error(f"{spec['label']} candles failed: {exc}")
        return None, None

    if chart_df.empty:
        st.warning(f"{spec['label']} returned no candles.")
        return None, None

    display_df = latest_session_df(chart_df) if latest_session_only else chart_df
    overlays = trim_overlays(build_overlays(chart_df), display_df)
    send_fresh_alerts(spec, chart_df, overlays)
    last_row = display_df.iloc[-1]
    delta = volume_delta(display_df.tail(80))
    st.caption(
        f"{spec['label']} | Last {last_row.close:,.2f} | "
        f"Delta {delta['delta']:,.0f} ({delta['delta_pct']:.1f}%) | Candles {len(display_df):,}"
    )
    chart_args = {
        "candles": HistoricalData.candle_json(display_df),
        "volume": HistoricalData.volume_json(display_df),
        "emas": overlays["emas"],
        "vwap": overlays["vwap"],
        "cpr": overlays["cpr"],
        "angle_market": overlays["angle_market"],
        "alphatrend": overlays["alphatrend"],
        "zones": overlays["zones"],
        "structure": overlays["structure"],
        "symbol": spec["label"],
        "timeframe": tf_label,
        "chart_id": chart_id,
        "height": height,
    }
    chart_args.pop("summary", None)
    TradingChart().render(**chart_args)
    return chart_df, overlays


metric_cols = st.columns(4)
metric_cols[0].metric("Index", index_name)
metric_cols[1].metric("Spot", f"{spot_ltp:,.2f}" if spot_ltp else "-")
metric_cols[2].metric("ATM", f"{atm}" if atm else "-")
metric_cols[3].metric(
    "Strikes",
    f"CE {selected_ce_strike or '-'} / PE {selected_pe_strike or '-'}",
)

st.subheader(index_chart_spec["title"])
render_index_oi_summary(chain_df)
render_market_chart(index_chart_spec, height=760)

option_cols = st.columns(2)
for col, spec, strike in zip(option_cols, [ce_chart_spec, pe_chart_spec], [selected_ce_strike, selected_pe_strike]):
    with col:
        if not spec:
            st.info("Option chart is unavailable for the selected strike.")
            continue
        st.subheader(spec["title"])
        render_strike_oi_summary(chain_df, strike)
        render_market_chart(spec, height=760)
