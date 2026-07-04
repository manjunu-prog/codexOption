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
export TELEGRAM_BOT_TOKEN_2="friend-bot-token"
export TELEGRAM_CHAT_ID_2="friend-chat-id"
```

The app sends fresh BUY, SELL, BoS, CHoCH, Bullish OB, and Bearish OB alerts up to 10 times, spaced 30 seconds apart. It also supports one shared bot with multiple chats using `TELEGRAM_BOT_TOKEN` and comma-separated `TELEGRAM_CHAT_IDS`.

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
