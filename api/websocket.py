"""
=========================================================
Option Terminal Pro
api/websocket.py
=========================================================
Basic Fyers WebSocket wrapper (v0.1)
=========================================================
"""

import json
from fyers_apiv3.FyersWebsocket import data_ws

from config import FYERS


class LiveMarket:

    def __init__(self, access_token: str):
        self.access_token = access_token
        self.ws = None
        self.on_tick_callback = None

    def on_open(self):
        print("✅ Fyers WebSocket Connected")

    def on_close(self, message=None):
        print("❌ WebSocket Closed", message)

    def on_error(self, message):
        print("⚠️ WebSocket Error:", message)

    def on_message(self, message):
        # Forward ticks to application
        if self.on_tick_callback:
            self.on_tick_callback(message)

    def connect(self, symbols):
        """
        symbols example:
        [
            "NSE:NIFTY50-INDEX",
            "NSE:NIFTYBANK-INDEX"
        ]
        """

        self.ws = data_ws.FyersDataSocket(
            access_token=self.access_token,
            log_path="",
            litemode=False,
            write_to_file=False,
            reconnect=True,
            on_connect=self.on_open,
            on_close=self.on_close,
            on_error=self.on_error,
            on_message=self.on_message,
        )

        self.ws.connect()

        self.ws.subscribe(
            symbols=symbols,
            data_type="SymbolUpdate"
        )

        self.ws.keep_running()

    def set_tick_handler(self, callback):
        """
        callback(message:dict)
        """
        self.on_tick_callback = callback

    def disconnect(self):
        if self.ws:
            self.ws.disconnect()


if __name__ == "__main__":

    print(
        "Example:\n"
        "from api.fyers_login import FyersLogin\n"
        "token = FyersLogin().login()\n"
        "live = LiveMarket(token)\n"
        "live.set_tick_handler(print)\n"
        "live.connect(['NSE:NIFTY50-INDEX'])"
    )
