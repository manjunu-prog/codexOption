"""
===========================================================
Option Terminal Pro
Configuration File
===========================================================
"""

from pathlib import Path
import os

# =========================================================
# PROJECT PATHS
# =========================================================

ROOT_DIR = Path(__file__).parent

DATA_DIR = ROOT_DIR / "data"
LOG_DIR = ROOT_DIR / "logs"
ASSET_DIR = ROOT_DIR / "assets"

DATA_DIR.mkdir(exist_ok=True)
LOG_DIR.mkdir(exist_ok=True)
ASSET_DIR.mkdir(exist_ok=True)

# =========================================================
# APPLICATION
# =========================================================

APP_NAME = "Option Terminal Pro"

VERSION = "0.1.0"

AUTHOR = "Manjunath"

DEBUG = True

AUTO_REFRESH_SECONDS = 5

# =========================================================
# FYERS
# =========================================================

# Better: Store these in a .env file later.
# For now we'll keep placeholders.

FYERS = {
    "FY_ID": os.getenv("FYERS_FY_ID", ""),
    "APP_ID": os.getenv("FYERS_APP_ID", ""),
    "APP_SECRET": os.getenv("FYERS_APP_SECRET", ""),
    "REDIRECT_URI": os.getenv(
        "FYERS_REDIRECT_URI",
        "https://trade.fyers.in/api-login/redirect-uri/index.html",
    ),
    "PIN": os.getenv("FYERS_PIN", ""),
    "TOTP_KEY": os.getenv("FYERS_TOTP_KEY", ""),
}

# =========================================================
# API URLs
# =========================================================

FYERS_API = {
    "LOGIN_OTP":
        "https://api-t2.fyers.in/vagator/v2/send_login_otp_v2",

    "VERIFY_OTP":
        "https://api-t2.fyers.in/vagator/v2/verify_otp",

    "VERIFY_PIN":
        "https://api-t2.fyers.in/vagator/v2/verify_pin_v2",

    "TOKEN":
        "https://api-t1.fyers.in/api/v3/token",

    "AUTHCODE":
        "https://api-t1.fyers.in/api/v3/validate-authcode"
}

# =========================================================
# DEFAULT SYMBOLS
# =========================================================

WATCHLIST = [
    "NSE:NIFTY50-INDEX",
    "NSE:NIFTYBANK-INDEX",
    "NSE:FINNIFTY-INDEX",
    "NSE:MIDCPNIFTY-INDEX",
    "BSE:SENSEX-INDEX"
]

INDEX_CONFIG = {
    "NIFTY": {"spot": "NSE:NIFTY50-INDEX", "exchange": "NSE", "step": 50, "strikecount": 25},
    "BANKNIFTY": {"spot": "NSE:NIFTYBANK-INDEX", "exchange": "NSE", "step": 100, "strikecount": 25},
    "FINNIFTY": {"spot": "NSE:FINNIFTY-INDEX", "exchange": "NSE", "step": 50, "strikecount": 20},
    "SENSEX": {"spot": "BSE:SENSEX-INDEX", "exchange": "BSE", "step": 100, "strikecount": 25},
}

# =========================================================
# TIMEFRAMES
# =========================================================

TIMEFRAMES = {
    "1 Min": "1",
    "2 Min": "2",
    "3 Min": "3",
    "5 Min": "5",
    "10 Min": "10",
    "15 Min": "15",
    "30 Min": "30",
    "60 Min": "60",
    "120 Min": "120",
    "240 Min": "240",
    "Daily": "D"
}

DEFAULT_TIMEFRAME = "5"

# =========================================================
# CHART SETTINGS
# =========================================================

CHART = {

    "HEIGHT": 700,

    "BACKGROUND": "#131722",

    "TEXT": "#d1d4dc",

    "GRID": "#2A2E39",

    "UP": "#26a69a",

    "DOWN": "#ef5350",

    "VOLUME_UP": "rgba(38,166,154,0.4)",

    "VOLUME_DOWN": "rgba(239,83,80,0.4)"
}

# =========================================================
# INDICATORS
# =========================================================

DEFAULT_INDICATORS = {

    "EMA": True,

    "VWAP": False,

    "RSI": False,

    "MACD": False,

    "SuperTrend": False,

    "CPR": False,

    "FVG": False,

    "OrderBlocks": False,

    "Liquidity": False,

    "BOS": False,

    "CHOCH": False
}

# =========================================================
# EMA SETTINGS
# =========================================================

EMA_PERIODS = [

    9,

    20,

    50,

    100,

    200
]

# =========================================================
# CACHE
# =========================================================

CACHE = {

    "HISTORICAL_TTL": 30,

    "OPTION_CHAIN_TTL": 5,

    "QUOTE_TTL": 2
}

# =========================================================
# WEBSOCKET
# =========================================================

WEBSOCKET = {

    "AUTO_RECONNECT": True,

    "RECONNECT_DELAY": 5,

    "HEARTBEAT": 20
}

# =========================================================
# LOGGING
# =========================================================

LOGGING = {

    "LEVEL": "INFO",

    "FILE": LOG_DIR / "terminal.log"
}

# =========================================================
# MARKET
# =========================================================

MARKET_OPEN = "09:15"

MARKET_CLOSE = "15:30"

# =========================================================
# FUTURE MODULES
# =========================================================

ENABLE_AI = False

ENABLE_OPTION_CHAIN = True

ENABLE_HEATMAP = False

ENABLE_REPLAY = False

ENABLE_BACKTEST = False
