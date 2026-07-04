# Option Terminal Pro

Local Streamlit trading terminal for NIFTY, BANKNIFTY, FINNIFTY, and SENSEX spot plus CE/PE option-strike candles using FYERS data.

## Run

```bash
cd OptionTerminal
python3 -m pip install -r requirements.txt
python3 -m streamlit run app.py
```

FYERS credentials can be entered in the sidebar or supplied as environment variables:

```bash
export FYERS_FY_ID="..."
export FYERS_PIN="..."
export FYERS_TOTP_KEY="..."
export FYERS_APP_ID="..."
export FYERS_APP_SECRET="..."
export FYERS_REDIRECT_URI="https://trade.fyers.in/api-login/redirect-uri/index.html"
```

Do not commit `.streamlit/secrets.toml`; keep production secrets in your deployment platform's secret manager.

## Included

- Full-width index chart with CE and PE charts below
- Separate CE and PE strike selectors
- FYERS historical candles and option-chain table
- 60-second auto refresh by default
- EMA, VWAP, AlphaTrend, FVG/iFVG, order blocks, BoS/CHoCH, and liquidity overlays
- Click-to-focus candle zoom, chart view persistence, horizontal panning, and drawing delete support

## Deploy

GitHub can host the code repository. To run the Streamlit app publicly, deploy the repo to a Python app host such as Streamlit Community Cloud, Render, Railway, or a VPS. GitHub Pages alone will not run this app because it requires a Python backend.
