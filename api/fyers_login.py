"""
=========================================================
Option Terminal Pro
Fyers Authentication Module
=========================================================
"""

import base64
import hashlib
from urllib.parse import parse_qs, urlparse

import pyotp
import requests
from fyers_apiv3 import fyersModel

from config import FYERS, FYERS_API


class FyersLogin:

    def __init__(self, credentials=None):
        self.session = requests.Session()
        self.access_token = None
        self.credentials = {**FYERS, **(credentials or {})}

    @staticmethod
    def _b64(value: str) -> str:
        return base64.b64encode(str(value).encode()).decode()

    @staticmethod
    def _generate_app_hash(app_id, app_secret):
        raw = f"{app_id}-100:{app_secret}"
        return hashlib.sha256(raw.encode()).hexdigest()

    def login(self):

        # ------------------------------------
        # STEP 1
        # Send OTP
        # ------------------------------------

        response = self.session.post(
            FYERS_API["LOGIN_OTP"],
            json={
                "fy_id": self._b64(self.credentials["FY_ID"]),
                "app_id": "2"
            }
        ).json()

        if "request_key" not in response:
            raise Exception(f"OTP Error : {response}")

        request_key = response["request_key"]

        # ------------------------------------
        # STEP 2
        # Verify OTP
        # ------------------------------------

        otp = pyotp.TOTP(
            self.credentials["TOTP_KEY"]
        ).now()

        response = self.session.post(
            FYERS_API["VERIFY_OTP"],
            json={
                "request_key": request_key,
                "otp": otp
            }
        ).json()

        if "request_key" not in response:
            raise Exception(f"OTP Verification Failed : {response}")

        request_key = response["request_key"]

        # ------------------------------------
        # STEP 3
        # Verify PIN
        # ------------------------------------

        response = self.session.post(
            FYERS_API["VERIFY_PIN"],
            json={
                "request_key": request_key,
                "identity_type": "pin",
                "identifier": self._b64(
                    self.credentials["PIN"]
                )
            }
        ).json()

        login_token = response.get(
            "data",
            {}
        ).get(
            "access_token"
        )

        if login_token is None:
            raise Exception("PIN Verification Failed")

        # ------------------------------------
        # STEP 4
        # Generate Auth Code
        # ------------------------------------

        response = self.session.post(
            FYERS_API["TOKEN"],
            headers={
                "Authorization": f"Bearer {login_token}"
            },
            json={
                "fyers_id": self.credentials["FY_ID"],
                "app_id": self.credentials["APP_ID"],
                "redirect_uri": self.credentials["REDIRECT_URI"],
                "appType": "100",
                "code_challenge": "",
                "state": "option_terminal",
                "scope": "",
                "nonce": "",
                "response_type": "code",
                "create_cookie": True
            }
        ).json()

        auth_url = response.get("Url")

        if auth_url is None:
            raise Exception(response)

        auth_code = parse_qs(
            urlparse(auth_url).query
        )["auth_code"][0]

        # ------------------------------------
        # STEP 5
        # Validate Auth Code
        # ------------------------------------

        app_hash = self._generate_app_hash(
            self.credentials["APP_ID"],
            self.credentials["APP_SECRET"]
        )

        response = self.session.post(
            FYERS_API["AUTHCODE"],
            json={
                "grant_type": "authorization_code",
                "appIdHash": app_hash,
                "code": auth_code
            }
        ).json()

        self.access_token = response.get(
            "access_token"
        )

        if self.access_token is None:
            raise Exception(response)

        return self.access_token

    def get_client(self):

        if self.access_token is None:
            self.login()

        return fyersModel.FyersModel(
            client_id=f"{self.credentials['APP_ID']}-100",
            token=self.access_token,
            is_async=False,
            log_path=""
        )
