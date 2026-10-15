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

create table if not exists public.signal_alerts (
  signal_key text primary key,
  symbol text not null,
  signal_type text not null,
  signal_time bigint,
  message text,
  last_sent_at timestamptz,
  alert_until timestamptz,
  sent_count integer not null default 0,
  created_at timestamptz not null default now()
);

alter table public.signal_alerts
add column if not exists last_sent_at timestamptz;

alter table public.signal_alerts
add column if not exists alert_until timestamptz;

alter table public.signal_alerts
add column if not exists sent_count integer not null default 0;

create index if not exists signal_alerts_created_idx
on public.signal_alerts (created_at);

create table if not exists public.option_flow_snapshots (
  snapshot_key text primary key,
  snapshot_ts timestamptz not null,
  session_date date not null,
  snapshot_time text not null,
  symbol text not null,
  pe_volume double precision not null default 0,
  pe_volume_change double precision,
  ce_volume double precision not null default 0,
  ce_volume_change double precision,
  pe_oi double precision not null default 0,
  pe_oi_change_abs double precision not null default 0,
  pe_oi_change_pct double precision,
  ce_oi double precision not null default 0,
  ce_oi_change_abs double precision not null default 0,
  ce_oi_change_pct double precision,
  created_at timestamptz not null default now()
);

create index if not exists option_flow_snapshots_lookup_idx
on public.option_flow_snapshots (symbol, session_date, snapshot_ts);
