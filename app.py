"""Option Terminal Pro."""

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


def secrets_value(key: str, default: str = "") -> str:
    try:
        return st.secrets.get(key, default)
    except Exception:
        return default


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
def load_candles(_client, symbol: str, resolution: str, days: int) -> pd.DataFrame:
    return HistoricalData(client=_client).get_candles(symbol, resolution, days)


@st.cache_data(ttl=8, show_spinner=False)
def load_chain(_client, symbol: str, strikecount: int) -> pd.DataFrame:
    return OptionChain(_client).fetch(symbol, strikecount=strikecount)


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


with st.sidebar:
    st.header("Market")
    index_name = st.selectbox("Index", list(INDEX_CONFIG.keys()), index=0)
    tf_label = st.selectbox("Timeframe", list(TIMEFRAMES.keys()), index=3)
    days = st.slider("History days", 1, 30, 5)
    latest_session_only = st.toggle("Latest session only", value=True)
    strike_window = st.slider("Strike window", 5, 40, INDEX_CONFIG[index_name]["strikecount"])
    auto_refresh = st.toggle("Auto refresh", value=True)
    refresh_seconds = st.slider("Refresh seconds", 5, 120, 30)

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
    strike_cols = st.columns(2)
    selected_ce_strike = strike_cols[0].radio(
        "CE strike",
        strikes,
        index=default_idx,
        horizontal=True,
        key="ce_strike_main",
    )
    selected_pe_strike = strike_cols[1].radio(
        "PE strike",
        strikes,
        index=default_idx,
        horizontal=True,
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
indicator_choice = st.radio(
    "Indicator",
    ["AlphaTrend", "EMA", "VWAP", "CPR", "Angle Market", "FVG", "iFVG", "Order Blocks", "PA Toolkit", "None"],
    horizontal=True,
    key="indicator_choice_main",
)

show_alphatrend = indicator_choice == "AlphaTrend"
show_ema = indicator_choice == "EMA"
show_vwap = indicator_choice == "VWAP"
show_cpr = indicator_choice == "CPR"
show_angle_market = indicator_choice == "Angle Market"
show_fvg = indicator_choice == "FVG"
show_ifvg = indicator_choice == "iFVG"
show_ob = indicator_choice == "Order Blocks"
show_structure = indicator_choice == "PA Toolkit"

if indicator_choice == "EMA":
    ema_periods = st.multiselect(
        "EMA periods",
        [9, 20, 50, 100, 200],
        default=[20],
        key="ema_periods_main",
    )
elif indicator_choice == "CPR":
    show_cpr_pivots = st.checkbox("Show R/S levels", value=True, key="cpr_pivots_main")
elif indicator_choice == "AlphaTrend":
    alpha_cols = st.columns(2)
    alphatrend_period = alpha_cols[0].number_input(
        "Period",
        min_value=1,
        max_value=100,
        value=14,
        key="alphatrend_period_main",
    )
    alphatrend_coeff = alpha_cols[1].number_input(
        "Multiplier",
        min_value=0.1,
        max_value=10.0,
        value=1.0,
        step=0.1,
        key="alphatrend_coeff_main",
    )
elif indicator_choice == "Angle Market":
    angle_cols = st.columns(3)
    angle_market_length = angle_cols[0].number_input(
        "Length",
        min_value=2,
        max_value=50,
        value=5,
        key="angle_market_length_main",
    )
    angle_market_angle = angle_cols[1].number_input(
        "Angle",
        min_value=0.0,
        max_value=1.0,
        value=0.1,
        step=0.01,
        key="angle_market_angle_main",
    )
    angle_market_deviation = angle_cols[2].number_input(
        "Deviation",
        min_value=0.1,
        max_value=10.0,
        value=1.0,
        step=0.1,
        key="angle_market_deviation_main",
    )
elif indicator_choice == "PA Toolkit":
    pa_cols = st.columns(3)
    structure_len = pa_cols[0].number_input(
        "Structure length",
        min_value=2,
        max_value=50,
        value=9,
        key="structure_len_main",
    )
    show_liquidity = pa_cols[1].checkbox("Show Liquidity Sweeps", value=False, key="show_liquidity_main")
    liquidity_len = pa_cols[2].number_input(
        "Liquidity length",
        min_value=5,
        max_value=100,
        value=30,
        key="liquidity_len_main",
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
    try:
        chart_df = load_candles(client, spec["symbol"], TIMEFRAMES[tf_label], days)
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
    TradingChart().render(
        candles=HistoricalData.candle_json(display_df),
        volume=HistoricalData.volume_json(display_df),
        emas=overlays["emas"],
        vwap=overlays["vwap"],
        cpr=overlays["cpr"],
        angle_market=overlays["angle_market"],
        alphatrend=overlays["alphatrend"],
        zones=overlays["zones"],
        structure=overlays["structure"],
        symbol=spec["label"],
        timeframe=tf_label,
        chart_id=spec.get("chart_id", spec["label"]),
        height=height,
    )
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
render_market_chart(index_chart_spec, height=760)

option_cols = st.columns(2)
for col, spec in zip(option_cols, [ce_chart_spec, pe_chart_spec]):
    with col:
        if not spec:
            st.info("Option chart is unavailable for the selected strike.")
            continue
        st.subheader(spec["title"])
        render_market_chart(spec, height=760)
