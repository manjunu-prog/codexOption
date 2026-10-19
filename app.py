"""Option Terminal Pro."""

import html
import json
import os
from datetime import datetime, time, timedelta
from io import BytesIO
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import requests
import streamlit as st
import streamlit.components.v1 as components
import yfinance as yf
from streamlit_autorefresh import st_autorefresh

from api.alerts import TelegramNotifier, app_login_code
from api.candle_cache import SupabaseCandleCache
from api.fyers_login import FyersLogin
from api.historical import HistoricalData
from api.option_chain import OptionChain
from chart.chart import TradingChart
from config import APP_NAME, FYERS, INDEX_CONFIG, TIMEFRAMES
from indicators import core as indicator_core

angle_market = indicator_core.angle_market
alphatrend = indicator_core.alphatrend
cpr = indicator_core.cpr
ema = indicator_core.ema
fvg_ifvg_order_blocks = indicator_core.fvg_ifvg_order_blocks
market_structure = indicator_core.market_structure
smart_money_callouts = getattr(indicator_core, "smart_money_callouts", lambda *args, **kwargs: [])
volume_delta = indicator_core.volume_delta
volume_poc_profile = getattr(indicator_core, "volume_poc_profile", lambda *args, **kwargs: {"levels": []})
volume_area_pressure = getattr(indicator_core, "volume_area_pressure", lambda *args, **kwargs: {})
vwap = indicator_core.vwap

st.set_page_config(page_title=APP_NAME, layout="wide")

APP_BUILD = "2026-08-03-candle-v5"
DATA_DIR = Path(__file__).parent / "data"
DATA_DIR.mkdir(exist_ok=True)
PREFERENCES_FILE = DATA_DIR / "last_activity.json"
OPTION_FLOW_HISTORY_FILE = DATA_DIR / "option_flow_history.json"
OPTION_FLOW_SUPABASE_TABLE = "option_flow_snapshots"
INDICATOR_OPTIONS = [
    "AlphaTrend",
    "EMA",
    "VWAP",
    "CPR",
    "Volume POC Profile",
    "Angle Market",
    "FVG",
    "iFVG",
    "CISD",
    "Order Blocks",
    "PA Toolkit",
]
HTF_FVG_TIMEFRAMES = [
    ("15 Min", "15", "15m"),
    ("30 Min", "30", "30m"),
]
FVG_LOOKBACK_DAYS = 4
PNL_LEG_COUNT = 2
TOP_SPOT_QUOTES = {
    "CRUDEOIL": "MCX:CRUDEOIL26JULFUT",
    "BANKNIFTY": INDEX_CONFIG["BANKNIFTY"]["spot"],
    "SENSEX": INDEX_CONFIG["SENSEX"]["spot"],
}
MARKET_SNAPSHOT = [
    {"name": "Gift Nifty", "ticker": "^NSEI", "region": "Asia", "timezone": "Asia/Kolkata", "open": time(9, 15), "close": time(15, 30)},
    {"name": "Nikkei 225", "ticker": "^N225", "region": "Asia", "timezone": "Asia/Tokyo", "open": time(9, 0), "close": time(15, 30)},
    {"name": "Hang Seng", "ticker": "^HSI", "region": "Asia", "timezone": "Asia/Hong_Kong", "open": time(9, 30), "close": time(16, 0)},
    {"name": "Taiwan Index", "ticker": "^TWII", "region": "Asia", "timezone": "Asia/Taipei", "open": time(9, 0), "close": time(13, 30)},
    {"name": "S&P 500", "ticker": "^GSPC", "region": "America", "timezone": "America/New_York", "open": time(9, 30), "close": time(16, 0)},
    {"name": "DJIA", "ticker": "^DJI", "region": "America", "timezone": "America/New_York", "open": time(9, 30), "close": time(16, 0)},
    {"name": "Nasdaq", "ticker": "^IXIC", "region": "America", "timezone": "America/New_York", "open": time(9, 30), "close": time(16, 0)},
    {"name": "ASX 200", "ticker": "^AXJO", "region": "Australia", "timezone": "Australia/Sydney", "open": time(10, 0), "close": time(16, 0)},
    {"name": "FTSE 100", "ticker": "^FTSE", "region": "Europe", "timezone": "Europe/London", "open": time(8, 0), "close": time(16, 30)},
    {"name": "CAC 40", "ticker": "^FCHI", "region": "Europe", "timezone": "Europe/Paris", "open": time(9, 0), "close": time(17, 30)},
    {"name": "DAX", "ticker": "^GDAXI", "region": "Europe", "timezone": "Europe/Berlin", "open": time(9, 0), "close": time(17, 30)},
]
HEATMAP_WINDOWS = {
    "15 Min": 15,
    "30 Min": 30,
    "1 Hour": 60,
    "2 Hour": 120,
    "3 Hour": 180,
}

# Contract sizes can change when the exchanges revise lot specifications.
# They are defaults only; the analyser exposes the lot size so it can be
# corrected for the selected contract before calculating P&L.
DEFAULT_LOT_SIZES = {
    "NIFTY": 75,
    "BANKNIFTY": 35,
    "FINNIFTY": 65,
    "SENSEX": 20,
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


def load_option_flow_history_local(symbol: str, session_date: str) -> list[dict]:
    try:
        if not OPTION_FLOW_HISTORY_FILE.exists():
            return []
        payload = json.loads(OPTION_FLOW_HISTORY_FILE.read_text())
        rows = payload.get(symbol, []) if isinstance(payload, dict) else []
        return [row for row in rows if row.get("date") == session_date][-500:]
    except Exception:
        return []


def load_option_flow_history(symbol: str, session_date: str) -> list[dict]:
    cfg = option_flow_supabase_config()
    if cfg:
        try:
            response = requests.get(
                f"{cfg['url']}/rest/v1/{cfg['table']}",
                params={
                    "select": "*",
                    "symbol": f"eq.{symbol}",
                    "session_date": f"eq.{session_date}",
                    "order": "snapshot_ts.asc",
                    "limit": "500",
                },
                headers=option_flow_supabase_headers(),
                timeout=20,
            )
            response.raise_for_status()
            return [
                {
                    "date": row.get("session_date"),
                    "time": row.get("snapshot_time"),
                    **{key: row.get(key, 0) for key in (
                        "pe_volume", "pe_volume_change", "ce_volume", "ce_volume_change",
                        "pe_oi", "pe_oi_change_abs", "pe_oi_change_pct",
                        "ce_oi", "ce_oi_change_abs", "ce_oi_change_pct",
                    )},
                }
                for row in response.json()
            ][-500:]
        except (requests.RequestException, ValueError):
            pass
    return load_option_flow_history_local(symbol, session_date)


def save_option_flow_history(symbol: str, rows: list[dict]) -> None:
    cfg = option_flow_supabase_config()
    if cfg and rows:
        payload = [
            {
                "snapshot_key": f"{symbol}|{row.get('date')}|{row.get('time')}",
                "snapshot_ts": f"{row.get('date')}T{row.get('time')}+05:30",
                "session_date": row.get("date"),
                "snapshot_time": row.get("time"),
                "symbol": symbol,
                **{key: row.get(key) for key in (
                    "pe_volume", "pe_volume_change", "ce_volume", "ce_volume_change",
                    "pe_oi", "pe_oi_change_abs", "pe_oi_change_pct",
                    "ce_oi", "ce_oi_change_abs", "ce_oi_change_pct",
                )},
            }
            for row in rows
        ]
        try:
            response = requests.post(
                f"{cfg['url']}/rest/v1/{cfg['table']}",
                params={"on_conflict": "snapshot_key"},
                headers=option_flow_supabase_headers(),
                json=payload,
                timeout=20,
            )
            response.raise_for_status()
            return
        except requests.RequestException:
            pass

    # Fallback only when Supabase is unavailable.
    try:
        payload = {}
        if OPTION_FLOW_HISTORY_FILE.exists():
            loaded = json.loads(OPTION_FLOW_HISTORY_FILE.read_text())
            if isinstance(loaded, dict):
                payload = loaded
        payload[symbol] = rows[-500:]
        OPTION_FLOW_HISTORY_FILE.write_text(json.dumps(payload, indent=2))
    except Exception:
        pass


def option_flow_supabase_config() -> dict[str, str]:
    def secret(name: str) -> str:
        value = os.getenv(name, "").strip()
        if value:
            return value
        try:
            return str(st.secrets.get(name, "")).strip()
        except Exception:
            return ""

    url = secret("SUPABASE_URL").rstrip("/")
    key = secret("SUPABASE_SERVICE_ROLE_KEY") or secret("SUPABASE_KEY") or secret("SUPABASE_ANON_KEY")
    if not url or not key:
        return {}
    return {"url": url, "key": key, "table": OPTION_FLOW_SUPABASE_TABLE}


def option_flow_supabase_headers() -> dict[str, str]:
    cfg = option_flow_supabase_config()
    return {
        "apikey": cfg["key"],
        "Authorization": f"Bearer {cfg['key']}",
        "Content-Type": "application/json",
        "Prefer": "resolution=merge-duplicates",
    }


def option_flow_history_snapshot(chain_df: pd.DataFrame) -> dict | None:
    if chain_df.empty or not {"type", "volume", "oi"}.issubset(chain_df.columns):
        return None
    work = chain_df.copy()
    if "oi_change" not in work.columns:
        work["oi_change"] = 0.0
    grouped = work.groupby("type")[["volume", "oi", "oi_change"]].sum()

    def side_values(side: str) -> tuple[float, float, float, float | None]:
        if side not in grouped.index:
            return 0.0, 0.0, 0.0, None
        oi = float(grouped.loc[side, "oi"])
        oi_change = float(grouped.loc[side, "oi_change"])
        previous_oi = oi - oi_change
        oi_change_pct = (oi_change / previous_oi) * 100 if previous_oi else None
        return float(grouped.loc[side, "volume"]), oi, oi_change, oi_change_pct

    pe_volume, pe_oi, pe_oi_change, pe_oi_change_pct = side_values("PE")
    ce_volume, ce_oi, ce_oi_change, ce_oi_change_pct = side_values("CE")
    return {
        "pe_volume": pe_volume,
        "ce_volume": ce_volume,
        "pe_oi": pe_oi,
        "ce_oi": ce_oi,
        "pe_oi_change_abs": pe_oi_change,
        "ce_oi_change_abs": ce_oi_change,
        "pe_oi_change_pct": pe_oi_change_pct,
        "ce_oi_change_pct": ce_oi_change_pct,
    }


def record_option_flow_snapshot(symbol: str, chain_df: pd.DataFrame) -> list[dict]:
    now = datetime.now(ZoneInfo("Asia/Kolkata"))
    session_date = now.date().isoformat()
    rows = load_option_flow_history(symbol, session_date)

    # Streamlit may rerun for widget/chart events before the intended
    # auto-refresh interval. Respect the configured refresh cadence so those
    # reruns do not create second-by-second history rows.
    if rows:
        try:
            last_dt = datetime.combine(
                now.date(),
                datetime.strptime(str(rows[-1].get("time", "")), "%H:%M:%S").time(),
                tzinfo=now.tzinfo,
            )
            refresh_interval = max(60, int(globals().get("refresh_seconds", 300)))
            if (now - last_dt).total_seconds() < refresh_interval:
                return rows
        except (TypeError, ValueError):
            pass

    snapshot = option_flow_history_snapshot(chain_df)
    if snapshot is None:
        return rows

    previous = rows[-1] if rows else None
    signature = tuple(snapshot[key] for key in (
        "pe_volume", "ce_volume", "pe_oi", "ce_oi",
        "pe_oi_change_abs", "ce_oi_change_abs", "pe_oi_change_pct", "ce_oi_change_pct",
    ))
    previous_signature = tuple(previous.get(key) for key in (
        "pe_volume", "ce_volume", "pe_oi", "ce_oi",
        "pe_oi_change_abs", "ce_oi_change_abs", "pe_oi_change_pct", "ce_oi_change_pct",
    )) if previous else None
    if signature == previous_signature:
        return rows

    row = {
        "date": session_date,
        "time": now.strftime("%H:%M:%S"),
        **snapshot,
        "pe_volume_change": snapshot["pe_volume"] - previous["pe_volume"] if previous else None,
        "ce_volume_change": snapshot["ce_volume"] - previous["ce_volume"] if previous else None,
    }
    rows.append(row)
    save_option_flow_history(symbol, rows)
    return rows


def option_flow_history_display(rows: list[dict]) -> pd.DataFrame:
    columns = [
        "Time", "PE Vol", "PE Vol Δ", "CE Vol", "CE Vol Δ",
        "PE OI Chg %", "PE OI Chg", "CE OI Chg %", "CE OI Chg",
    ]
    display_rows = []
    for row in rows:
        display_rows.append(
            {
                "Time": row["time"],
                "PE Vol": compact_number(row["pe_volume"]),
                "PE Vol Δ": compact_number(row["pe_volume_change"]),
                "CE Vol": compact_number(row["ce_volume"]),
                "CE Vol Δ": compact_number(row["ce_volume_change"]),
                "PE OI Chg %": percent_text(row.get("pe_oi_change_pct")),
                "PE OI Chg": compact_number(row.get("pe_oi_change_abs")),
                "CE OI Chg %": percent_text(row.get("ce_oi_change_pct")),
                "CE OI Chg": compact_number(row.get("ce_oi_change_abs")),
            }
        )
    return pd.DataFrame(display_rows, columns=columns)


def option_flow_style(display_df: pd.DataFrame, rows: list[dict]):
    styles = pd.DataFrame("", index=display_df.index, columns=display_df.columns)
    compare_pairs = [
        ("PE Vol", "pe_volume", "CE Vol", "ce_volume"),
        ("PE Vol Δ", "pe_volume_change", "CE Vol Δ", "ce_volume_change"),
        ("PE OI Chg %", "pe_oi_change_pct", "CE OI Chg %", "ce_oi_change_pct"),
        ("PE OI Chg", "pe_oi_change_abs", "CE OI Chg", "ce_oi_change_abs"),
    ]
    for row_index, row in enumerate(rows[: len(display_df)]):
        for left_column, left_key, right_column, right_key in compare_pairs:
            try:
                left_value = float(row.get(left_key))
                right_value = float(row.get(right_key))
            except (TypeError, ValueError):
                continue
            maximum = max(abs(left_value), abs(right_value), 1.0)
            if abs(left_value - right_value) < 1e-9:
                styles.at[row_index, left_column] = "background-color: rgba(234, 179, 8, 0.16); color: #854D0E"
                styles.at[row_index, right_column] = "background-color: rgba(234, 179, 8, 0.16); color: #854D0E"
            elif abs(left_value) > abs(right_value):
                intensity = 0.14 + 0.34 * abs(left_value) / maximum
                styles.at[row_index, left_column] = f"background-color: rgba(22, 163, 74, {intensity:.3f}); color: #FFFFFF; font-weight: 600"
                styles.at[row_index, right_column] = "background-color: rgba(220, 38, 38, 0.22); color: #FFFFFF; font-weight: 600"
            else:
                styles.at[row_index, right_column] = f"background-color: rgba(22, 163, 74, {0.14 + 0.34 * abs(right_value) / maximum:.3f}); color: #FFFFFF; font-weight: 600"
                styles.at[row_index, left_column] = "background-color: rgba(220, 38, 38, 0.22); color: #FFFFFF; font-weight: 600"
    return styles


def option_flow_excel_bytes(index_name: str, display_df: pd.DataFrame, rows: list[dict]) -> bytes:
    buffer = BytesIO()
    with pd.ExcelWriter(buffer, engine="xlsxwriter") as writer:
        display_df.to_excel(writer, sheet_name="Option Flow", index=False, startrow=2)
        workbook = writer.book
        worksheet = writer.sheets["Option Flow"]
        title = workbook.add_format({"bold": True, "font_size": 16, "font_color": "#FFFFFF", "bg_color": "#111827"})
        header = workbook.add_format({"bold": True, "font_color": "#FFFFFF", "bg_color": "#374151", "border": 1, "align": "center"})
        stronger = workbook.add_format({"bg_color": "#DCFCE7", "font_color": "#166534"})
        weaker = workbook.add_format({"bg_color": "#FEE2E2", "font_color": "#991B1B"})
        equal = workbook.add_format({"bg_color": "#FEF3C7", "font_color": "#854D0E"})
        normal = workbook.add_format()
        worksheet.merge_range(0, 0, 0, max(len(display_df.columns) - 1, 0), f"{index_name} Option Flow History", title)
        for column_index, column in enumerate(display_df.columns):
            worksheet.write(2, column_index, column, header)
            worksheet.set_column(column_index, column_index, max(12, min(22, len(str(column)) + 3)))
        raw_keys = {
            "PE Vol": "pe_volume",
            "CE Vol": "ce_volume",
            "PE Vol Δ": "pe_volume_change",
            "CE Vol Δ": "ce_volume_change",
            "PE OI Chg %": "pe_oi_change_pct",
            "PE OI Chg": "pe_oi_change_abs",
            "CE OI Chg %": "ce_oi_change_pct",
            "CE OI Chg": "ce_oi_change_abs",
        }
        comparison_pairs = {
            "PE Vol": ("pe_volume", "ce_volume"),
            "CE Vol": ("ce_volume", "pe_volume"),
            "PE Vol Δ": ("pe_volume_change", "ce_volume_change"),
            "CE Vol Δ": ("ce_volume_change", "pe_volume_change"),
            "PE OI Chg %": ("pe_oi_change_pct", "ce_oi_change_pct"),
            "CE OI Chg %": ("ce_oi_change_pct", "pe_oi_change_pct"),
            "PE OI Chg": ("pe_oi_change_abs", "ce_oi_change_abs"),
            "CE OI Chg": ("ce_oi_change_abs", "pe_oi_change_abs"),
        }
        for row_index, display_row in display_df.iterrows():
            raw_row = rows[row_index] if row_index < len(rows) else {}
            for column_index, column in enumerate(display_df.columns):
                fmt = normal
                key = raw_keys.get(column)
                if key:
                    try:
                        value = float(raw_row.get(key))
                        if column in comparison_pairs:
                            _, other_key = comparison_pairs[column]
                            other_value = float(raw_row.get(other_key))
                            fmt = equal if abs(value - other_value) < 1e-9 else stronger if abs(value) > abs(other_value) else weaker
                        else:
                            fmt = normal
                    except (TypeError, ValueError):
                        pass
                worksheet.write(row_index + 3, column_index, display_row[column], fmt)
        worksheet.freeze_panes(3, 1)
        worksheet.autofilter(2, 0, 2 + len(display_df), len(display_df.columns) - 1)
        worksheet.set_landscape()
        worksheet.fit_to_pages(1, 0)
    return buffer.getvalue()


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


def clamp_number(value, low: int, high: int, default: int) -> int:
    try:
        number = int(value)
    except Exception:
        number = default
    return max(low, min(high, number))


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
st.caption(f"Build {APP_BUILD}")
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
def load_candles(
    _client,
    symbol: str,
    resolution: str,
    days: int,
    refresh_nonce: int = 0,
    parser_version: str = APP_BUILD,
) -> pd.DataFrame:
    return HistoricalData(client=_client).get_candles(symbol, resolution, days)


@st.cache_data(ttl=8, show_spinner=False)
def load_chain(_client, symbol: str, strikecount: int) -> pd.DataFrame:
    return OptionChain(_client).fetch(symbol, strikecount=strikecount)


@st.cache_data(ttl=60, show_spinner=False)
def load_pnl_leg_candles(_client, symbol: str, session_date: str) -> pd.DataFrame:
    """Load 2-minute candles for one option leg for the selected session."""
    candles = HistoricalData(client=_client).get_candles(symbol, "2", days=3)
    if candles.empty:
        return candles
    day = pd.Timestamp(session_date).date()
    return candles[candles.index.date == day].copy()


def pnl_leg_symbol_options(chain_df: pd.DataFrame) -> list[str]:
    if chain_df.empty or "symbol" not in chain_df.columns:
        return []
    return sorted({str(value) for value in chain_df["symbol"].dropna() if str(value)})


def pnl_leg_label(symbol: str, chain_df: pd.DataFrame) -> str:
    if not symbol or chain_df.empty:
        return symbol or "-"
    row = chain_df[chain_df["symbol"] == symbol]
    if row.empty:
        return symbol
    item = row.iloc[0]
    return f"{int(item['strike'])} {item['type']}"


def calculate_pnl_analysis(
    legs: list[dict],
    client,
    session_date: str,
    start_value: time,
    end_value: time,
) -> tuple[pd.DataFrame, pd.DataFrame, str | None]:
    """Return 2-minute leg prices, P&L, and ratio metrics for two legs."""
    if len(legs) != PNL_LEG_COUNT:
        return pd.DataFrame(), pd.DataFrame(), "Select exactly two option legs."
    if start_value >= end_value:
        return pd.DataFrame(), pd.DataFrame(), "End time must be after start time."

    series: dict[str, pd.Series] = {}
    errors: list[str] = []
    for index, leg in enumerate(legs, start=1):
        symbol = leg.get("symbol", "")
        if not symbol:
            errors.append(f"Leg {index} has no option selected.")
            continue
        try:
            candles = load_pnl_leg_candles(client, symbol, session_date)
        except Exception as exc:
            errors.append(f"Leg {index}: {exc}")
            continue
        if candles.empty or "close" not in candles.columns:
            errors.append(f"Leg {index} has no 2-minute candles for {session_date}.")
            continue
        series[f"leg_{index}"] = candles["close"].astype(float)

    if errors:
        return pd.DataFrame(), pd.DataFrame(), " ".join(errors)

    prices = pd.concat(series, axis=1).sort_index().dropna(how="all")
    start_dt = pd.Timestamp.combine(pd.Timestamp(session_date).date(), start_value)
    end_dt = pd.Timestamp.combine(pd.Timestamp(session_date).date(), end_value)
    prices = prices[(prices.index >= start_dt) & (prices.index <= end_dt)]
    if prices.empty:
        return pd.DataFrame(), pd.DataFrame(), "No 2-minute option prices were returned in that time window."

    # The first available 2-minute price at/after the requested start is the
    # simulated entry price. Forward-fill later missing leg candles so one
    # temporarily absent quote does not erase the combined P&L row.
    prices = prices.ffill().dropna()
    if prices.empty:
        return pd.DataFrame(), pd.DataFrame(), "No complete two-leg 2-minute rows were returned."

    entry_prices = prices.iloc[0]
    output = pd.DataFrame(index=prices.index)
    output.index.name = "Time"
    output["Net P&L"] = 0.0
    for index, leg in enumerate(legs, start=1):
        key = f"leg_{index}"
        ltp_col = f"L{index} LTP"
        pnl_col = f"L{index} P&L"
        quantity = float(leg["lots"]) * float(leg["lot_size"])
        direction = str(leg["side"]).upper()
        output[ltp_col] = prices[key]
        if direction == "BUY":
            output[pnl_col] = (prices[key] - entry_prices[key]) * quantity
        else:
            output[pnl_col] = (entry_prices[key] - prices[key]) * quantity
        output["Net P&L"] += output[pnl_col]

    # Premium ratio is calculated per option type from the selected leg LTPs.
    # For a single CE sell at 180 and CE buy at 60 this displays 3.00x,
    # matching the requested 180/60 ratio. The percentage column shows the
    # change from the first analysed 2-minute row.
    for option_type in ("CE", "PE"):
        sell_indices = [i for i, leg in enumerate(legs, start=1) if leg["type"] == option_type and leg["side"] == "SELL"]
        buy_indices = [i for i, leg in enumerate(legs, start=1) if leg["type"] == option_type and leg["side"] == "BUY"]
        pnl_indices = [i for i, leg in enumerate(legs, start=1) if leg["type"] == option_type]
        output[f"{option_type} Hedge P&L"] = output[[f"L{i} P&L" for i in pnl_indices]].sum(axis=1) if pnl_indices else 0.0
        if sell_indices and buy_indices:
            sell = output[[f"L{i} LTP" for i in sell_indices]].mean(axis=1)
            buy = output[[f"L{i} LTP" for i in buy_indices]].mean(axis=1)
            ratio = pd.to_numeric(sell.div(buy.replace(0, pd.NA)), errors="coerce")
            output[f"{option_type} LTP Ratio"] = ratio

    display = output.reset_index()
    display["Time"] = display["Time"].dt.strftime("%H:%M")
    return output, display, None


def render_pnl_analyser(chain_df: pd.DataFrame, client, index_name: str, strike_window: int) -> None:
    st.subheader("P&L 2-min Analyser")
    st.caption("Choose two option legs. Entry is the first available 2-minute price at or after the start time; P&L is calculated through the selected end time.")
    pnl_index_options = [name for name in ("NIFTY", "BANKNIFTY", "SENSEX") if name in INDEX_CONFIG]
    if st.session_state.pop("pnl_reset_requested", False):
        reset_keys = [
            "pnl_underlying", "pnl_session_date", "pnl_start_time", "pnl_end_time",
            "pnl_analysis_2min", "pnl_analysis_3min",
            *[f"pnl_lot_size:{name}" for name in pnl_index_options],
            *[f"pnl_leg_{field}:{index}" for index in range(1, 5) for field in ("symbol", "side", "lots")],
        ]
        for key in reset_keys:
            st.session_state.pop(key, None)
    pnl_index_name = st.selectbox("Underlying", pnl_index_options, index=option_index(pnl_index_options, index_name, 0), key="pnl_underlying")
    if pnl_index_name == index_name:
        # The chart can use a narrow strike window, but the P&L analyser
        # needs a wider range so users can build spreads farther from ATM.
        try:
            pnl_chain_df = load_chain(
                client,
                INDEX_CONFIG[pnl_index_name]["spot"],
                max(50, strike_window, INDEX_CONFIG[pnl_index_name]["strikecount"]),
            )
        except Exception as exc:
            st.error(f"Unable to load {pnl_index_name} option chain: {exc}")
            return
    else:
        try:
            pnl_chain_df = load_chain(
                client,
                INDEX_CONFIG[pnl_index_name]["spot"],
                max(50, strike_window, INDEX_CONFIG[pnl_index_name]["strikecount"]),
            )
        except Exception as exc:
            st.error(f"Unable to load {pnl_index_name} option chain: {exc}")
            return
    symbols = pnl_leg_symbol_options(pnl_chain_df)
    if not symbols:
        st.info("Option-chain data is required before the P&L analyser can be used.")
        return

    today = datetime.now(ZoneInfo("Asia/Kolkata")).date()
    with st.form("pnl_2min_analyser_form", clear_on_submit=False):
        control_cols = st.columns(4)
        session_date = control_cols[0].date_input("Trading date", value=today, key="pnl_session_date")
        start_value = control_cols[1].time_input("Start time", value=time(9, 20), key="pnl_start_time")
        end_value = control_cols[2].time_input("End time", value=time(15, 10), key="pnl_end_time")
        lot_size = control_cols[3].number_input(
            "Lot size",
            min_value=1,
            value=int(DEFAULT_LOT_SIZES.get(pnl_index_name, 1)),
            step=1,
            key=f"pnl_lot_size:{index_name}",
            help="Verify the current exchange lot size before using the result.",
        )

        legs: list[dict] = []
        for index in range(1, PNL_LEG_COUNT + 1):
            st.markdown(f"**Leg {index}**")
            cols = st.columns([2.4, 1, 1, 1])
            selected = cols[0].selectbox(
                "Strike / type",
                symbols,
                format_func=lambda value: pnl_leg_label(value, pnl_chain_df),
                key=f"pnl_leg_symbol:{index}",
                label_visibility="collapsed",
            )
            side = cols[1].selectbox("Side", ["SELL", "BUY"], key=f"pnl_leg_side:{index}", label_visibility="collapsed")
            lots = cols[2].number_input("Lots", min_value=1, value=1, step=1, key=f"pnl_leg_lots:{index}", label_visibility="collapsed")
            selected_row = pnl_chain_df[pnl_chain_df["symbol"] == selected].iloc[0]
            legs.append({
                "symbol": selected,
                "type": str(selected_row["type"]),
                "strike": int(selected_row["strike"]),
                "side": side,
                "lots": int(lots),
                "lot_size": int(lot_size),
            })

        analyze = st.form_submit_button("Analyze P&L", type="primary", width="stretch")

    reset_col, _ = st.columns([1, 3])
    if reset_col.button("Reset P&L Analyser", key="reset_pnl_2min_analyser", width="stretch"):
        st.session_state["pnl_reset_requested"] = True
        st.rerun()

    if analyze:
        raw, display, error = calculate_pnl_analysis(
            legs,
            client,
            session_date.isoformat(),
            start_value,
            end_value,
        )
        if error:
            st.error(error)
            return
        leg_column_names = {}
        used_leg_labels: dict[str, int] = {}
        for index, leg in enumerate(legs, start=1):
            base_label = f"{leg['strike']} {leg['type']}"
            used_leg_labels[base_label] = used_leg_labels.get(base_label, 0) + 1
            suffix = f" ({used_leg_labels[base_label]})" if used_leg_labels[base_label] > 1 else ""
            leg_column_names[f"L{index} LTP"] = f"{base_label}{suffix} LTP"
            leg_column_names[f"L{index} P&L"] = f"{base_label}{suffix} P&L"
        display = display.rename(columns=leg_column_names)
        st.session_state["pnl_analysis_2min"] = {
            "raw": raw,
            "display": display,
            "legs": legs,
            "index_name": pnl_index_name,
        }
    else:
        saved_analysis = st.session_state.get("pnl_analysis_2min")
        if not saved_analysis:
            return
        raw = saved_analysis["raw"]
        display = saved_analysis["display"]
        legs = saved_analysis["legs"]
        pnl_index_name = saved_analysis["index_name"]
        if len(legs) != PNL_LEG_COUNT:
            st.session_state.pop("pnl_analysis_2min", None)
            st.info("The saved analysis used four legs. Please click Analyze P&L again with exactly two legs.")
            return
        if display.columns.duplicated().any():
            st.session_state.pop("pnl_analysis_2min", None)
            st.info("The saved analysis used duplicate leg headers. Please click Analyze P&L again to rebuild it with unique strike labels.")
            return

    final_pnl = float(raw["Net P&L"].iloc[-1])
    st.metric("Net P&L at end", f"₹{final_pnl:,.2f}")
    ratio_rows = []
    for option_type in ("CE", "PE"):
        sell_legs = [leg for leg in legs if leg["type"] == option_type and leg["side"] == "SELL"]
        buy_legs = [leg for leg in legs if leg["type"] == option_type and leg["side"] == "BUY"]
        sell_lots = sum(leg["lots"] for leg in sell_legs)
        buy_lots = sum(leg["lots"] for leg in buy_legs)
        ratio_col = f"{option_type} LTP Ratio"
        ratio_rows.append({
            "Type": option_type,
            "SELL lots": sell_lots,
            "BUY lots": buy_lots,
            "Lot ratio (SELL:BUY)": f"{sell_lots}:{buy_lots}" if sell_lots and buy_lots else "-",
            "Current LTP ratio": float(raw[ratio_col].iloc[-1]) if ratio_col in raw and pd.notna(raw[ratio_col].iloc[-1]) else None,
            "Hedge P&L": float(raw[f"{option_type} Hedge P&L"].iloc[-1]),
        })
    ratio_df = pd.DataFrame(ratio_rows)
    st.caption("Premium ratio compares average SELL-leg LTP with average BUY-leg LTP. Hedge P&L totals all CE or PE legs separately.")
    st.dataframe(ratio_df.round(2), hide_index=True, width="stretch")

    def pnl_cell_colour(value, column: pd.Series) -> str:
        if pd.isna(value):
            return ""
        negative = column[column < 0]
        positive = column[column > 0]
        if value < 0 and not negative.empty:
            intensity = abs(float(value)) / max(abs(float(negative.min())), 1.0)
            return f"background-color: rgba(220, 38, 38, {0.12 + 0.68 * intensity:.3f}); color: #fff"
        if value > 0 and not positive.empty:
            intensity = float(value) / max(float(positive.max()), 1.0)
            return f"background-color: rgba(22, 163, 74, {0.12 + 0.68 * intensity:.3f}); color: #fff"
        return "color: #a1a1aa"

    styled_display = display.round(2).style
    pnl_columns = [column for column in display.columns if column == "Net P&L" or column.endswith(" P&L")]
    for column in pnl_columns:
        styled_display = styled_display.map(
            lambda value, series=display[column]: pnl_cell_colour(value, series),
            subset=[column],
        )
    st.dataframe(styled_display, hide_index=True, width="stretch")
    csv_data = display.to_csv(index=False).encode("utf-8")
    csv_name = f"{pnl_index_name.lower()}_pnl_2min.csv"
    excel_buffer = BytesIO()
    export_display = display.copy()
    numeric_columns = export_display.select_dtypes(include="number").columns
    export_display[numeric_columns] = export_display[numeric_columns].round(2)
    export_ratio = ratio_df.copy()
    ratio_numeric_columns = export_ratio.select_dtypes(include="number").columns
    export_ratio[ratio_numeric_columns] = export_ratio[ratio_numeric_columns].round(2)
    with pd.ExcelWriter(excel_buffer, engine="xlsxwriter") as writer:
        export_display.to_excel(writer, sheet_name="P&L Analysis", index=False, startrow=2)
        export_ratio.to_excel(writer, sheet_name="P&L Analysis", index=False, startrow=len(export_display) + 7)
        workbook = writer.book
        worksheet = writer.sheets["P&L Analysis"]
        title_format = workbook.add_format({"bold": True, "font_size": 16, "font_color": "#FFFFFF", "bg_color": "#111827"})
        header_format = workbook.add_format({"bold": True, "font_color": "#FFFFFF", "bg_color": "#374151", "border": 1, "align": "center"})
        section_format = workbook.add_format({"bold": True, "font_color": "#FFFFFF", "bg_color": "#1F2937"})
        number_format = workbook.add_format({"num_format": "0.00"})
        worksheet.merge_range(0, 0, 0, max(len(export_display.columns) - 1, 0), f"{pnl_index_name} P&L 2-minute Analysis", title_format)
        for column_index, column in enumerate(export_display.columns):
            worksheet.write(2, column_index, column, header_format)
            worksheet.set_column(column_index, column_index, max(12, min(20, len(str(column)) + 3)), number_format if column != "Time" else None)
        ratio_header_row = len(export_display) + 7
        worksheet.write(ratio_header_row - 1, 0, "Ratio Summary", section_format)
        for column_index, column in enumerate(export_ratio.columns):
            worksheet.write(ratio_header_row, column_index, column, header_format)
            worksheet.set_column(column_index, column_index, max(14, min(24, len(str(column)) + 3)))
        worksheet.freeze_panes(3, 1)
        worksheet.autofilter(2, 0, 2 + len(export_display), len(export_display.columns) - 1)
        for column_index, column in enumerate(export_display.columns):
            if column == "Net P&L" or column.endswith(" P&L"):
                worksheet.conditional_format(
                    3, column_index, 2 + len(export_display), column_index,
                    {"type": "3_color_scale", "min_color": "#FECACA", "mid_color": "#FEF3C7", "max_color": "#BBF7D0"},
                )
        worksheet.set_landscape()
        worksheet.fit_to_pages(1, 0)
    excel_data = excel_buffer.getvalue()
    excel_name = f"{pnl_index_name.lower()}_pnl_2min.xlsx"
    export_col, telegram_col = st.columns(2)
    export_col.download_button(
        "Export formatted Excel report",
        data=excel_data,
        file_name=excel_name,
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        key="export_pnl_2min_excel",
        width="stretch",
    )
    export_col.download_button(
        "Export raw CSV",
        data=csv_data,
        file_name=csv_name,
        mime="text/csv",
        key="export_pnl_2min_csv",
        width="stretch",
    )
    notifier = get_notifier()
    if telegram_col.button(
        "Send formatted report to Telegram",
        key="send_pnl_2min_csv",
        disabled=not notifier.enabled,
        width="stretch",
    ):
        ok, message = notifier.send_document(
            excel_name,
            excel_data,
            caption=f"{pnl_index_name} P&L 2-minute analysis",
        )
        (st.success if ok else st.error)(message)
    if not notifier.enabled:
        st.caption("Configure Telegram bot recipients to enable report delivery.")


def quote_number(value: dict, keys: tuple[str, ...]) -> float | None:
    for key in keys:
        raw = value.get(key)
        if raw is None or raw == "":
            continue
        try:
            return float(raw)
        except (TypeError, ValueError):
            continue
    return None


def is_market_live(market: dict, now_utc: datetime) -> bool:
    local_now = now_utc.astimezone(ZoneInfo(market["timezone"]))
    if local_now.weekday() >= 5:
        return False
    return market["open"] <= local_now.time() <= market["close"]


def is_india_market_live(now_ist: datetime | None = None) -> bool:
    now_ist = now_ist or datetime.now(ZoneInfo("Asia/Kolkata"))
    if now_ist.weekday() >= 5:
        return False
    return time(9, 15) <= now_ist.time() <= time(15, 30)


@st.cache_data(ttl=120, show_spinner=False)
def load_market_snapshot() -> list[dict]:
    now_utc = datetime.now(ZoneInfo("UTC"))
    rows = []
    for market in MARKET_SNAPSHOT:
        ltp = change = change_pct = None
        updated = now_utc.astimezone(ZoneInfo("Asia/Kolkata"))
        try:
            info = yf.Ticker(market["ticker"]).fast_info
            ltp = float(info.get("last_price") or info.get("lastPrice"))
            previous_close = float(info.get("previous_close") or info.get("previousClose"))
            if previous_close:
                change = ltp - previous_close
                change_pct = (change / previous_close) * 100
        except Exception:
            pass
        rows.append(
            {
                "name": market["name"],
                "ltp": ltp,
                "change": change,
                "change_pct": change_pct,
                "region": market["region"],
                "status": "Live" if is_market_live(market, now_utc) else "Closed",
                "updated": updated.strftime("%d %b, %I:%M %p").lstrip("0"),
            }
        )
    return rows


def render_market_snapshot() -> None:
    rows = load_market_snapshot()
    html_rows = []
    for row in rows:
        change = row["change"]
        change_pct = row["change_pct"]
        tone = "positive" if (change or 0) >= 0 else "negative"
        ltp_text = f"{row['ltp']:,.2f}" if row["ltp"] is not None else "-"
        change_text = f"{change:+,.2f} ({change_pct:+,.2f}%)" if change is not None and change_pct is not None else "-"
        status_class = "live" if row["status"] == "Live" else "closed"
        html_rows.append(
            "<tr>"
            f"<td>{html.escape(row['name'])}</td>"
            f"<td class='numeric'><div>{ltp_text}</div><div class='{tone}'>{change_text}</div></td>"
            f"<td>{html.escape(row['region'])}</td>"
            f"<td><span class='dot {status_class}'></span>{html.escape(row['status'])}</td>"
            f"<td>{html.escape(row['updated'])}</td>"
            "</tr>"
        )

    st.subheader("Market Snapshot")
    st.markdown(
        """
        <style>
        .market-snapshot-table{
            width:100%;
            border-collapse:collapse;
            border:1px solid #e5e7eb;
            font-size:17px;
        }
        .market-snapshot-table th{
            background:#eeeeee;
            color:#333333;
            text-align:left;
            padding:16px 18px;
            font-weight:500;
        }
        .market-snapshot-table td{
            padding:14px 18px;
            border-top:1px solid #f1f5f9;
            color:#2f2f2f;
        }
        .market-snapshot-table tr:nth-child(even) td{
            background:#fafafa;
        }
        .market-snapshot-table .numeric{
            text-align:right;
            font-size:20px;
            line-height:1.28;
        }
        .market-snapshot-table .positive{
            color:#0b8a3a;
            font-size:15px;
        }
        .market-snapshot-table .negative{
            color:#c21f0a;
            font-size:15px;
        }
        .market-snapshot-table .dot{
            display:inline-block;
            width:12px;
            height:12px;
            border-radius:999px;
            margin-right:18px;
            background:#737373;
            vertical-align:middle;
        }
        .market-snapshot-table .dot.live{
            background:#087f3f;
        }
        </style>
        <table class="market-snapshot-table">
            <thead>
                <tr>
                    <th>Index</th>
                    <th>LTP</th>
                    <th>Region</th>
                    <th>Status</th>
                    <th>Last Updated</th>
                </tr>
            </thead>
            <tbody>
        """
        + "".join(html_rows)
        + """
            </tbody>
        </table>
        """,
        unsafe_allow_html=True,
    )


@st.cache_data(ttl=120, show_spinner=False)
def load_market_heatmap(minutes: int) -> list[dict]:
    tickers = [market["ticker"] for market in MARKET_SNAPSHOT]
    names_by_ticker = {market["ticker"]: market["name"] for market in MARKET_SNAPSHOT}
    region_by_ticker = {market["ticker"]: market["region"] for market in MARKET_SNAPSHOT}
    try:
        data = yf.download(
            tickers,
            period="5d",
            interval="5m",
            progress=False,
            threads=True,
            auto_adjust=False,
        )
    except Exception:
        data = pd.DataFrame()

    if data.empty:
        return [
            {"name": market["name"], "region": market["region"], "change_pct": None}
            for market in MARKET_SNAPSHOT
        ]

    close_data = data.get("Close", pd.DataFrame())
    if isinstance(close_data, pd.Series):
        close_data = close_data.to_frame(tickers[0])

    rows = []
    for ticker in tickers:
        if ticker not in close_data:
            rows.append({"name": names_by_ticker[ticker], "region": region_by_ticker[ticker], "change_pct": None})
            continue
        series = pd.to_numeric(close_data[ticker], errors="coerce").dropna()
        if series.empty:
            rows.append({"name": names_by_ticker[ticker], "region": region_by_ticker[ticker], "change_pct": None})
            continue

        latest_time = series.index[-1]
        target_time = latest_time - pd.Timedelta(minutes=minutes)
        previous = series[series.index <= target_time]
        base = float(previous.iloc[-1] if not previous.empty else series.iloc[0])
        latest = float(series.iloc[-1])
        change_pct = ((latest - base) / base) * 100 if base else None
        rows.append(
            {
                "name": names_by_ticker[ticker],
                "region": region_by_ticker[ticker],
                "change_pct": change_pct,
            }
        )
    return rows


def heatmap_color(change_pct: float | None) -> str:
    if change_pct is None:
        return "#6b7280"
    strength = min(abs(change_pct) / 1.5, 1.0)
    if change_pct >= 0:
        lightness = 42 - int(strength * 22)
        return f"hsl(138, 72%, {lightness}%)"
    lightness = 42 - int(strength * 14)
    return f"hsl(5, 62%, {lightness}%)"


def render_market_heatmap() -> None:
    st.subheader("Heatmap")
    selected_window = st.radio(
        "Heatmap window",
        list(HEATMAP_WINDOWS.keys()),
        index=0,
        horizontal=True,
        key="global_heatmap_window",
    )
    rows = load_market_heatmap(HEATMAP_WINDOWS[selected_window])
    tiles = []
    for row in rows:
        value = row["change_pct"]
        value_text = f"{value:+.2f}%" if value is not None else "-"
        tiles.append(
            (
                f'<div class="market-heatmap-tile" style="background:{heatmap_color(value)}">'
                f'<div class="market-heatmap-name">{html.escape(row["name"])}</div>'
                f'<div class="market-heatmap-value">{value_text}</div>'
                f'<div class="market-heatmap-region">{html.escape(row["region"])}</div>'
                "</div>"
            )
        )

    components.html(
        """
        <style>
        body{margin:0;font-family:Inter,Segoe UI,Arial,sans-serif;background:#ffffff;}
        .market-heatmap-grid{
            display:grid;
            grid-template-columns:repeat(6, minmax(110px, 1fr));
            gap:3px;
            margin-top:6px;
        }
        .market-heatmap-tile{
            min-height:58px;
            padding:8px 8px;
            color:#ffffff;
            display:flex;
            flex-direction:column;
            align-items:center;
            justify-content:center;
            text-align:center;
            border:2px solid #ffffff;
        }
        .market-heatmap-name{
            font-size:12px;
            font-weight:700;
            line-height:1.15;
        }
        .market-heatmap-value{
            font-size:13px;
            font-weight:800;
            margin-top:2px;
        }
        .market-heatmap-region{
            font-size:9px;
            opacity:.82;
            margin-top:3px;
        }
        @media (max-width: 900px){
            .market-heatmap-grid{
                grid-template-columns:repeat(3, minmax(90px, 1fr));
            }
        }
        </style>
        <div class="market-heatmap-grid">
        """
        + "".join(tiles)
        + "</div>",
        height=150,
        scrolling=False,
    )


@st.cache_data(ttl=8, show_spinner=False)
def load_quotes(_client, symbols: list[str]) -> dict[str, dict]:
    response = _client.quotes(data={"symbols": ",".join(symbols)})
    if response.get("s") != "ok":
        return {}
    quotes = {}
    for item in response.get("d", []):
        symbol = item.get("n")
        value = item.get("v", {})
        ltp = quote_number(value, ("lp", "ltp"))
        if symbol and ltp is not None:
            quotes[symbol] = {
                "ltp": ltp,
                "change": quote_number(value, ("ch", "change", "netChg")),
                "change_pct": quote_number(value, ("chp", "changePercent", "pctChg")),
            }
    return quotes


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


def option_volume_callout(chain_df: pd.DataFrame, timestamp: int, price: float) -> dict | None:
    if chain_df.empty or "volume" not in chain_df or "type" not in chain_df:
        return None
    totals = chain_df.groupby("type")["volume"].sum()
    call_volume = float(totals.get("CE", 0) or 0)
    put_volume = float(totals.get("PE", 0) or 0)
    if call_volume <= 0 and put_volume <= 0:
        return None
    if put_volume > call_volume:
        dominant, ratio, tone = "PUT", put_volume / call_volume if call_volume else None, "optionPut"
    elif call_volume > put_volume:
        dominant, ratio, tone = "CALL", call_volume / put_volume if put_volume else None, "optionCall"
    else:
        dominant, ratio, tone = "BALANCED", 1.0, "optionNeutral"
    ratio_text = f"PE {ratio:.2f}x CE" if dominant == "PUT" and ratio is not None else (
        f"CE {ratio:.2f}x PE" if dominant == "CALL" and ratio is not None else "BALANCED"
    )
    pressure = "BUYING" if dominant == "CALL" else "SELLING" if dominant == "PUT" else "BALANCED"
    return {
        "time": int(timestamp),
        "price": float(price),
        "label": f"OPTION PRESSURE: {pressure} {ratio_text} | PE {compact_number(put_volume)} / CE {compact_number(call_volume)}",
        "tone": "pressureBuy" if pressure == "BUYING" else "pressureSell" if pressure == "SELLING" else "pressureNeutral",
        "direction": "bullish" if pressure == "BUYING" else "bearish" if pressure == "SELLING" else "neutral",
    }


def option_chart_pressure(chain_df: pd.DataFrame, side: str, strike: int | None = None) -> dict | None:
    """Compare aggregate CE/PE volume using the same totals as the history table.

    The chart is for a selected strike, but the pressure label is intentionally
    based on the full option-chain totals so it agrees with Option Flow History.
    """
    if chain_df.empty or not {"type", "volume"}.issubset(chain_df.columns) or side not in {"CE", "PE"}:
        return None
    totals = chain_df.groupby("type")["volume"].sum()
    ce_volume = float(totals.get("CE", 0) or 0)
    pe_volume = float(totals.get("PE", 0) or 0)
    if ce_volume <= 0 and pe_volume <= 0:
        return None

    own_volume = ce_volume if side == "CE" else pe_volume
    other_volume = pe_volume if side == "CE" else ce_volume
    buying = own_volume > other_volume
    selling = own_volume < other_volume
    leading, trailing = (own_volume, other_volume) if buying else (other_volume, own_volume)

    if leading == trailing:
        return {
            "label": "OPTION PRESSURE: BALANCED",
            "tone": "pressureNeutral",
            "direction": "neutral",
        }

    pressure = "SELLING" if selling else "BUYING"
    ratio = leading / trailing if trailing else None
    ratio_text = f"{ratio:.2f}x" if ratio is not None else "∞"
    return {
        "label": f"OPTION PRESSURE: {pressure} {ratio_text}",
        "tone": "pressureSell" if pressure == "SELLING" else "pressureBuy",
        "direction": "bearish" if pressure == "SELLING" else "bullish",
    }


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


def render_option_flow_history(symbol: str, index_name: str, rows: list[dict]) -> None:
    st.subheader("Option Flow History")
    st.caption("Volume deltas compare with the previous snapshot; OI change uses the option-chain API percentage and absolute change.")
    st.caption(
        "Source: FYERS direct API → Supabase"
        if option_flow_supabase_config()
        else "Source: FYERS direct API → local fallback"
    )
    display_df = option_flow_history_display(rows)
    if display_df.empty:
        st.info("Waiting for the first option-chain snapshot.")
        return

    st.dataframe(display_df.style.apply(lambda _: option_flow_style(display_df, rows), axis=None), hide_index=True, width="stretch")
    csv_data = pd.DataFrame(rows).to_csv(index=False).encode("utf-8")
    excel_data = option_flow_excel_bytes(index_name, display_df, rows)
    download_col, telegram_col = st.columns(2)
    download_col.download_button(
        "Export Option Flow CSV",
        data=csv_data,
        file_name=f"{index_name.lower()}_option_flow.csv",
        mime="text/csv",
        key="export_option_flow_csv",
        width="stretch",
    )
    download_col.download_button(
        "Export Option Flow Excel",
        data=excel_data,
        file_name=f"{index_name.lower()}_option_flow.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        key="export_option_flow_excel",
        width="stretch",
    )
    notifier = get_notifier()
    if telegram_col.button(
        "Send CSV to Telegram",
        key="send_option_flow_csv",
        disabled=not notifier.enabled,
        width="stretch",
    ):
        ok, message = notifier.send_document(
            f"{index_name.lower()}_option_flow.csv",
            csv_data,
            caption=f"{index_name} option flow history",
        )
        (st.success if ok else st.error)(message)
    if not notifier.enabled:
        st.caption("Configure Telegram bot recipients to enable CSV delivery.")


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
    days = st.slider("History days", 1, 30, int(preference_number(preferences, "days", 5)), key="days")
    latest_session_only = st.toggle(
        "Latest session only",
        value=bool(preferences.get("latest_session_only", True)),
        key="latest_session_only",
    )
    strike_window = st.slider(
        "Strike window",
        1,
        10,
        min(10, int(preference_number(preferences, "strike_window", INDEX_CONFIG[index_name]["strikecount"]))),
        key="strike_window",
    )
    auto_refresh = st.toggle("Auto refresh", value=bool(preferences.get("auto_refresh", True)), key="auto_refresh")
    saved_refresh_seconds = preference_number(preferences, "refresh_seconds", 300)
    try:
        saved_refresh_number = int(saved_refresh_seconds or 0)
    except Exception:
        saved_refresh_number = 300
    if saved_refresh_number < 60:
        saved_refresh_seconds = 300
    refresh_seconds = st.slider(
        "Refresh seconds",
        60,
        600,
        clamp_number(saved_refresh_seconds, 60, 600, 300),
        step=60,
        key="refresh_seconds",
    )

    with st.expander("Data Maintenance", expanded=False):
        reset_confirmed = st.checkbox("Confirm Supabase candle reset", key="reset_supabase_confirmed")
        if st.button("Reset Supabase Data", disabled=not reset_confirmed, key="reset_supabase_data"):
            ok, message = SupabaseCandleCache().reset_all()
            if ok:
                load_candles.clear()
                st.success(message)
            else:
                st.error(message)

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
    quote_item = top_quotes.get(symbol) or {}
    price = quote_item.get("ltp")
    change = quote_item.get("change")
    change_pct = quote_item.get("change_pct")
    if change is not None and change_pct is not None:
        delta = f"{change:,.2f} ({change_pct:,.2f}%)"
    elif change is not None:
        delta = f"{change:,.2f}"
    elif change_pct is not None:
        delta = f"{change_pct:,.2f}%"
    else:
        delta = None
    col.metric(name, f"{price:,.2f}" if price is not None else "-", delta=delta)

index_cfg = INDEX_CONFIG[index_name]
spot_symbol = index_cfg["spot"]

try:
    chain_df = load_chain(client, spot_symbol, strike_window)
except Exception as exc:
    st.error(f"Option-chain fetch failed: {exc}")
    chain_df = pd.DataFrame()

option_flow_history = record_option_flow_snapshot(spot_symbol, chain_df)

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
show_volume_poc = False
volume_poc_bins = 28
volume_poc_levels = 3
show_angle_market = False
angle_market_length = 5
angle_market_angle = 0.1
angle_market_deviation = 1.0
show_alphatrend = True
alphatrend_period = 14
alphatrend_coeff = 1.0
show_fvg = False
show_ifvg = False
show_cisd = False
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

st.subheader("Chart Timeframes")
fallback_tf = preferences.get("tf_label", "5 Min")
index_tf_default = preferences.get("index_tf_label", fallback_tf)
ce_tf_default = preferences.get("ce_tf_label", index_tf_default)
pe_tf_default = preferences.get("pe_tf_label", index_tf_default)
tf_cols = st.columns(3)
index_tf_label = tf_cols[0].selectbox(
    "Index timeframe",
    timeframe_options,
    index=option_index(timeframe_options, index_tf_default, 3),
    key="index_tf_label_main",
)
ce_tf_label = tf_cols[1].selectbox(
    "CE timeframe",
    timeframe_options,
    index=option_index(timeframe_options, ce_tf_default, option_index(timeframe_options, index_tf_label, 3)),
    key="ce_tf_label_main",
)
pe_tf_label = tf_cols[2].selectbox(
    "PE timeframe",
    timeframe_options,
    index=option_index(timeframe_options, pe_tf_default, option_index(timeframe_options, index_tf_label, 3)),
    key="pe_tf_label_main",
)
index_chart_spec["tf_label"] = index_tf_label
if ce_chart_spec:
    ce_chart_spec["tf_label"] = ce_tf_label
if pe_chart_spec:
    pe_chart_spec["tf_label"] = pe_tf_label

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
show_volume_poc = "Volume POC Profile" in selected_indicators
show_angle_market = "Angle Market" in selected_indicators
show_fvg = "FVG" in selected_indicators
show_ifvg = "iFVG" in selected_indicators
show_cisd = "CISD" in selected_indicators
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
if show_volume_poc:
    volume_poc_cols = st.columns(2)
    volume_poc_bins = volume_poc_cols[0].number_input(
        "POC rows",
        min_value=8,
        max_value=80,
        value=int(preference_number(preferences, "volume_poc_bins", 28)),
        step=2,
        key="volume_poc_bins_main",
    )
    volume_poc_levels = volume_poc_cols[1].number_input(
        "POC marks",
        min_value=1,
        max_value=5,
        value=int(preference_number(preferences, "volume_poc_levels", 3)),
        key="volume_poc_levels_main",
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
        "tf_label": index_tf_label,
        "index_tf_label": index_tf_label,
        "ce_tf_label": ce_tf_label,
        "pe_tf_label": pe_tf_label,
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
        "volume_poc_bins": int(volume_poc_bins),
        "volume_poc_levels": int(volume_poc_levels),
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
    if show_cisd:
        visible_kinds.add("fvg")

    all_zones = fvg_ifvg_order_blocks(df, max_zones=90) if visible_kinds else []
    confluence_zones = all_zones if all_zones else fvg_ifvg_order_blocks(df, max_zones=90)
    zones = [
        zone for zone in all_zones
        if zone.get("kind") in visible_kinds and (show_fvg or zone.get("kind") != "fvg")
    ]
    cisd = [
        zone["cisd"] for zone in all_zones
        if show_cisd and zone.get("cisd")
    ]
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
        "cisd": cisd,
        "callouts": smart_money_callouts(df, confluence_zones),
        "structure": market_structure(
            df,
            lookback=int(structure_len),
            liquidity_lookback=int(liquidity_len),
            show_liquidity=show_liquidity,
        )
        if show_structure
        else None,
    }


def higher_timeframe_fvg_zones(symbol: str, current_resolution: str, nonce: int) -> list[dict]:
    if not show_fvg:
        return []

    zones: list[dict] = []
    for label, resolution, short_label in HTF_FVG_TIMEFRAMES:
        if resolution == current_resolution:
            continue
        try:
            htf_df = load_candles(client, symbol, resolution, max(days, FVG_LOOKBACK_DAYS), nonce)
        except Exception:
            continue
        if htf_df.empty:
            continue
        htf_zones = [zone for zone in fvg_ifvg_order_blocks(htf_df, max_zones=45) if zone.get("kind") == "fvg"]
        for zone in htf_zones:
            direction = zone.get("direction")
            zones.append(
                {
                    **zone,
                    "label": f"{short_label} FVG - {'BULL' if direction == 'bullish' else 'BEAR'}",
                    # Keep the original FVG palette for higher timeframes.
                    "fill": "rgba(34,197,94,0.12)" if direction == "bullish" else "rgba(239,68,68,0.12)",
                    "border": "rgba(22,163,74,0.82)" if direction == "bullish" else "rgba(220,38,38,0.82)",
                    "text": "rgba(22,163,74,0.98)" if direction == "bullish" else "rgba(220,38,38,0.98)",
                    "borderStyle": "solid" if resolution == "30" else "dashed",
                    "sourceTf": short_label,
                }
            )
    return zones


def keep_recent_fvg_zones_alive(zones: list[dict], chart_df: pd.DataFrame, chart_resolution: str) -> list[dict]:
    if not show_fvg or chart_df.empty or chart_resolution == "D":
        return zones

    last_ts = int(chart_df.index.max().timestamp())
    cutoff_ts = int((chart_df.index.max() - timedelta(days=FVG_LOOKBACK_DAYS)).timestamp())
    extend_to = last_ts + max(timeframe_seconds(chart_resolution), 300)
    latest_chart_date = pd.Timestamp.fromtimestamp(last_ts, tz="Asia/Kolkata").date()
    active_zones = []
    for zone in zones:
        if zone.get("kind") != "fvg":
            active_zones.append(zone)
            continue
        start_time = int(zone.get("startTime") or zone.get("time") or 0)
        if start_time < cutoff_ts:
            continue
        source_tf = str(zone.get("sourceTf") or "")
        zone_date = (
            pd.Timestamp.fromtimestamp(start_time, tz="Asia/Kolkata").date()
            if source_tf in {"15m", "30m"}
            else None
        )
        if source_tf in {"15m", "30m"} and zone_date != latest_chart_date:
            active_zones.append(zone)
        else:
            active_zones.append({**zone, "endTime": max(int(zone.get("endTime") or start_time), extend_to)})
    return active_zones


def compact_chart_zones(zones: list[dict]) -> list[dict]:
    """Keep the newest useful overlays so the browser does not build hundreds of DOM nodes."""
    limits = {"local": 36, "15m": 18, "30m": 18}
    grouped: dict[tuple[str, str], list[dict]] = {}
    passthrough: list[dict] = []
    for zone in zones:
        kind = str(zone.get("kind") or "")
        if kind not in {"fvg", "ifvg"}:
            passthrough.append(zone)
            continue
        source = str(zone.get("sourceTf") or "local")
        grouped.setdefault((source, kind), []).append(zone)

    selected_ids: set[int] = set()
    for (source, kind), items in grouped.items():
        limit = limits.get(source, 24)
        if kind == "ifvg":
            limit = min(limit, 24)
        selected_ids.update(id(item) for item in items[-limit:])

    return [
        zone for zone in zones
        if id(zone) in selected_ids or str(zone.get("kind") or "") not in {"fvg", "ifvg"}
    ]


def latest_session_df(df: pd.DataFrame, chart_tf_label: str) -> pd.DataFrame:
    if df.empty or TIMEFRAMES[chart_tf_label] == "D":
        return df
    today_ist = datetime.now(ZoneInfo("Asia/Kolkata")).date()
    if is_india_market_live() and bool((df.index.date == today_ist).any()):
        return df[df.index.date == today_ist]
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
    if overlays.get("cisd"):
        trimmed["cisd"] = [item for item in overlays["cisd"] if point_in_session(item)]
    if overlays.get("callouts"):
        trimmed["callouts"] = [item for item in overlays["callouts"] if point_in_session(item)]
    if overlays.get("structure"):
        trimmed["structure"] = {
            "markers": [item for item in overlays["structure"].get("markers", []) if point_in_session(item)],
            "levels": [item for item in overlays["structure"].get("levels", []) if line_touches_session(item)],
            "zones": [item for item in overlays["structure"].get("zones", []) if line_touches_session(item)],
            "trendLines": [item for item in overlays["structure"].get("trendLines", []) if line_touches_session(item)],
        }
    return trimmed


def render_market_chart(spec: dict, height: int = 520, strike: int | None = None) -> tuple[pd.DataFrame, dict] | tuple[None, None]:
    chart_id = spec.get("chart_id", spec["label"])
    chart_tf_label = spec.get("tf_label", index_tf_label)
    nonce_key = f"refresh_nonce:{chart_id}"
    if nonce_key not in st.session_state:
        st.session_state[nonce_key] = 0
    if st.button(f"Refresh {spec['title']}", key=f"refresh_button:{chart_id}"):
        st.session_state[nonce_key] += 1

    chart_resolution = TIMEFRAMES[chart_tf_label]
    candle_days = max(days, FVG_LOOKBACK_DAYS) if chart_resolution != "D" else days
    try:
        chart_df = load_candles(client, spec["symbol"], chart_resolution, candle_days, st.session_state[nonce_key])
    except Exception as exc:
        st.error(f"{spec['label']} candles failed [{APP_BUILD}]: {exc}")
        return None, None

    if chart_df.empty:
        st.warning(f"{spec['label']} returned no candles.")
        return None, None

    if latest_session_only and chart_resolution != "D":
        today_ist = datetime.now(ZoneInfo("Asia/Kolkata")).date()
        latest_available = chart_df.index.max()
        if is_india_market_live() and latest_available.date() < today_ist:
            debug = chart_df.attrs.get("history_debug", "")
            details = f" Fyers debug: {debug}" if debug else ""
            st.error(
                f"{spec['label']} has no candles for today's session yet. "
                f"Latest available candle is {latest_available.strftime('%d %b %H:%M')}.{details}"
            )
            return None, None

    display_df = latest_session_df(chart_df, chart_tf_label) if latest_session_only else chart_df
    raw_overlays = build_overlays(chart_df)
    if show_fvg and chart_resolution != "D":
        raw_overlays["zones"] = [
            *raw_overlays.get("zones", []),
            *higher_timeframe_fvg_zones(spec["symbol"], chart_resolution, st.session_state[nonce_key]),
        ]
        raw_overlays["zones"] = keep_recent_fvg_zones_alive(raw_overlays["zones"], chart_df, chart_resolution)
    raw_overlays["zones"] = compact_chart_zones(raw_overlays.get("zones", []))
    overlays = trim_overlays(raw_overlays, display_df)
    overlays["volume_poc"] = (
        volume_poc_profile(
            display_df,
            bins=int(volume_poc_bins),
            max_levels=int(volume_poc_levels),
        )
        if show_volume_poc
        else None
    )
    last_row = display_df.iloc[-1]
    pressure = volume_area_pressure(display_df, bins=int(volume_poc_bins))
    if spec["title"] == "Index":
        option_callout = option_volume_callout(chain_df, int(display_df.index[-1].timestamp()), float(last_row["close"]))
        if option_callout:
            option_callout["placement"] = "topLeft"
            overlays["callouts"].append(option_callout)
    elif pressure.get("pocPrice") is not None:
        option_pressure = option_chart_pressure(chain_df, spec["title"], strike=strike)
        if option_pressure:
            overlays["callouts"].append(
                {
                    **option_pressure,
                    "time": int(display_df.index[-1].timestamp()),
                    "price": float(pressure["pocPrice"]),
                    "placement": "topLeft",
                }
            )
    delta = volume_delta(display_df.tail(80))
    latest_candle_time = display_df.index.max().strftime("%d %b %H:%M")
    st.caption(
        f"{spec['label']} | Last {last_row.close:,.2f} | "
        f"Delta {delta['delta']:,.0f} ({delta['delta_pct']:.1f}%) | "
        f"Candles {len(display_df):,} | Latest {latest_candle_time}"
    )
    chart_args = {
        "candles": HistoricalData.candle_json(display_df),
        "volume": HistoricalData.volume_json(display_df),
        "emas": overlays["emas"],
        "vwap": overlays["vwap"],
        "cpr": overlays["cpr"],
        "volume_poc": overlays["volume_poc"],
        "angle_market": overlays["angle_market"],
        "alphatrend": overlays["alphatrend"],
        "zones": overlays["zones"],
        "cisd": overlays["cisd"],
        "callouts": overlays["callouts"],
        "structure": overlays["structure"],
        "symbol": spec["label"],
        "timeframe": chart_tf_label,
        "chart_id": chart_id,
        "height": height,
        "telegram_recipients": get_notifier().recipients,
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
render_option_flow_history(spot_symbol, index_name, option_flow_history)
render_market_chart(index_chart_spec, height=760)

for spec, strike in [(ce_chart_spec, selected_ce_strike), (pe_chart_spec, selected_pe_strike)]:
    if not spec:
        st.info("Option chart is unavailable for the selected strike.")
        continue
    st.subheader(spec["title"])
    render_strike_oi_summary(chain_df, strike)
    render_market_chart(spec, height=760, strike=strike)

render_pnl_analyser(chain_df, client, index_name, strike_window)
