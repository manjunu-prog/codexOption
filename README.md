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

Optional Supabase cache secrets:

```bash
export SUPABASE_URL="https://your-project.supabase.co"
export SUPABASE_SERVICE_ROLE_KEY="your-service-role-key"
```

Use the Supabase project API URL for `SUPABASE_URL`, not the database connection string that starts with `postgresql://`.

You can use `SUPABASE_ANON_KEY` instead of `SUPABASE_SERVICE_ROLE_KEY`, but then your Row Level Security policies must allow read/write/delete for the `candles` table.

Optional app lock and Telegram alert secrets:

```bash
export APP_LOGIN_CODE="123456"
export TELEGRAM_BOT_TOKEN_1="your-bot-token"
export TELEGRAM_CHAT_ID_1="your-chat-id"
export TELEGRAM_BOT_TOKEN="your-bot-token"
export TELEGRAM_CHAT_ID="your-chat-id"
export TELEGRAM_BOT_TOKEN_2="friend-bot-token"
export TELEGRAM_CHAT_ID_2="friend-chat-id"
```

The app sends fresh BUY, SELL, BoS, CHoCH, Bullish OB, and Bearish OB alerts up to 10 times, spaced 30 seconds apart. It also supports one shared bot with multiple chats using `TELEGRAM_BOT_TOKEN` and comma-separated `TELEGRAM_CHAT_IDS`.

## Option Flow History Backup

The existing `Option Flow History` table is backed up to Supabase when the Supabase variables above are configured. Run `supabase_schema.sql` to create `option_flow_snapshots`.

The repository also includes `.github/workflows/option-flow-history.yml`, which logs into FYERS, fetches the option chain, calculates PE/CE volume deltas and OI changes, and writes one row to Supabase. Add these GitHub repository secrets: `FYERS_FY_ID`, `FYERS_APP_ID`, `FYERS_APP_SECRET`, `FYERS_REDIRECT_URI`, `FYERS_PIN`, `FYERS_TOTP_KEY`, `SUPABASE_URL`, and `SUPABASE_SERVICE_ROLE_KEY`.

GitHub Actions' hosted scheduler has a documented five-minute minimum, so the workflow is set to every 5 minutes. For an exact 3-minute cadence, run the same `python scripts/collect_option_flow.py` command from a worker or scheduler that supports 3-minute intervals. The Streamlit app itself can still refresh at the configured cadence while open.

## Included

- Full-width index chart with CE and PE charts below
- Separate CE and PE strike selectors
- FYERS historical candles and option-chain table
- 30-second auto refresh by default
- EMA, VWAP, AlphaTrend, FVG/iFVG, order blocks, BoS/CHoCH, and liquidity overlays
- Click-to-focus candle zoom, chart view persistence, horizontal panning, and drawing delete support

## Deploy

GitHub can host the code repository. To run the Streamlit app publicly, deploy the repo to a Python app host such as Streamlit Community Cloud, Render, Railway, or a VPS. GitHub Pages alone will not run this app because it requires a Python backend.

## Supabase Candle Cache

Run this SQL in Supabase SQL Editor:

```sql
create table if not exists public.candles (
  symbol text not null,
  resolution text not null,
  timestamp bigint not null,
  open double precision not null,
  high double precision not null,
  low double precision not null,
  close double precision not null,
  volume bigint not null,
  created_at timestamptz not null default now(),
  primary key (symbol, resolution, timestamp)
);

create index if not exists candles_lookup_idx
on public.candles (symbol, resolution, timestamp);
```

The app keeps roughly the last 4 days by deleting older candle rows during refresh. If Supabase secrets are missing, the app automatically falls back to direct FYERS pulls.

The same SQL file also creates `signal_alerts`, which prevents duplicate Telegram alerts on refresh.

## Professional Paper Trading

Run the standalone paper-trading app with `python3 -m streamlit run paper_app.py`. It creates 12 independent paper portfolios:

- NIFTY Slot 1–4
- BANKNIFTY Slot 1–4
- SENSEX Slot 1–4

All portfolios use live FYERS quotes but simulated orders only. Market buys use the live ask and market sells use the live bid when available; limit and stop orders remain pending until the next refresh meets their trigger. Orders, fills, positions, cash, P&L, and equity snapshots are stored in `data/paper_trading.db` and can be exported as CSV or Excel. No paper action calls a FYERS order API.
