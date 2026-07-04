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
