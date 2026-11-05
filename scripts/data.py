"""Hyperliquid public data layer (no keys): candles + funding, with local CSV cache under ./data.

Uses MAINNET public Info API for realistic history (testnet books are thin).
Only the most recent ~5000 candles per coin+interval are available.

CLI:
  python data.py candles ETH --granularity 1h --start 2026-04-01
  python data.py candles BTC --market futures --granularity 4h --start 2025-01-01
  python data.py funding ETH
  python data.py symbols --market futures
"""
from __future__ import annotations
import argparse, os, time
import pandas as pd

CACHE = os.environ.get("HL_DATA_DIR", "data")
MAINNET = "https://api.hyperliquid.xyz"
TESTNET = "https://api.hyperliquid-testnet.xyz"
# HL intervals
GRAN = {"1m": 60_000, "3m": 180_000, "5m": 300_000, "15m": 900_000, "30m": 1_800_000,
        "1h": 3_600_000, "2h": 7_200_000, "4h": 14_400_000, "8h": 28_800_000,
        "12h": 43_200_000, "1d": 86_400_000, "3d": 259_200_000, "1w": 604_800_000}
ALIAS = {"1H": "1h", "4H": "4h", "1D": "1d", "1day": "1d", "1week": "1w", "60m": "1h"}
MAX_CANDLES = 5000  # HL API hard cap

def _norm(g): return ALIAS.get(g, g)

def _ms(x):
    if x is None: return None
    if isinstance(x, (int, float)): return int(x)
    return int(pd.Timestamp(x, tz="UTC").timestamp() * 1000)

def _info(base_url=None):
    from hyperliquid.info import Info
    return Info(base_url or MAINNET, skip_ws=True)

def _norm_symbol(symbol: str) -> str:
    s = symbol.strip().upper().replace("-", "").replace("/", "")
    for suf in ("USDT", "USDC", "USD"):
        if s.endswith(suf) and len(s) > len(suf):
            s = s[:-len(suf)]
            break
    return s

def fetch_candles(symbol, market="futures", granularity="1h", start=None, end=None,
                  kind="trade", use_cache=True, verbose=True, network="mainnet"):
    """Return ascending OHLCV DataFrame indexed by UTC ts.
    market: futures (perp coin name) | spot (use coin like PURR or @index — prefer futures for lab).
    kind is accepted for API compatibility with the Bitget skill; HL only has trade candles.
    """
    coin = _norm_symbol(symbol)
    g = _norm(granularity)
    if g not in GRAN:
        raise ValueError(f"unsupported granularity {granularity}; choose from {sorted(GRAN)}")
    end_ms = _ms(end) or int(time.time() * 1000)
    start_ms = _ms(start) or (end_ms - MAX_CANDLES * GRAN[g])
    # Cap request window to ~5000 bars
    max_span = MAX_CANDLES * GRAN[g]
    if end_ms - start_ms > max_span:
        if verbose:
            print(f"  ⚠️ HL returns at most ~{MAX_CANDLES} {g} candles; truncating start to fit")
        start_ms = end_ms - max_span

    path_cache = os.path.join(CACHE, f"hl_{network}_{market}_{coin}_{g}.csv")
    if use_cache and os.path.exists(path_cache):
        cached = pd.read_csv(path_cache)
        if len(cached):
            lo, hi = int(cached.ts_ms.min()), int(cached.ts_ms.max())
            if start_ms >= lo and end_ms <= hi + GRAN[g]:
                out = cached[(cached.ts_ms >= start_ms) & (cached.ts_ms < end_ms)]
                return _finish(out)

    base = TESTNET if network == "testnet" else MAINNET
    info = _info(base)
    raw = info.candles_snapshot(coin, g, start_ms, end_ms)
    if verbose:
        print(f"  {coin} {market} {g}: {len(raw)} bars from HL {network}", flush=True)
    if not raw:
        return _finish(pd.DataFrame(columns=["ts_ms", "open", "high", "low", "close", "volume", "quote_volume"]))

    rows = []
    for c in raw:
        o, h, l, cl, v = float(c["o"]), float(c["h"]), float(c["l"]), float(c["c"]), float(c["v"])
        rows.append({"ts_ms": int(c["t"]), "open": o, "high": h, "low": l, "close": cl,
                     "volume": v, "quote_volume": v * cl})
    df = pd.DataFrame(rows).drop_duplicates("ts_ms").sort_values("ts_ms")
    if use_cache:
        os.makedirs(CACHE, exist_ok=True)
        df.to_csv(path_cache, index=False)
    return _finish(df[(df.ts_ms >= start_ms) & (df.ts_ms < end_ms)])

def _finish(df):
    df = df.copy()
    if df.empty:
        df["ts"] = pd.to_datetime([], utc=True)
        return df.set_index("ts")
    df["ts"] = pd.to_datetime(df.ts_ms, unit="ms", utc=True)
    return df.set_index("ts")

def fetch_many(symbols, market="futures", granularity="1h", start=None, end=None, field="close"):
    return pd.DataFrame({s: fetch_candles(s, market, granularity, start, end)[field] for s in symbols})

def funding_history(symbol, use_cache=True, network="mainnet", lookback_days=100):
    """Perp funding rate series indexed by settlement time (UTC)."""
    coin = _norm_symbol(symbol)
    p = os.path.join(CACHE, f"hl_funding_{network}_{coin}.csv")
    if use_cache and os.path.exists(p):
        s = pd.read_csv(p)
        if len(s):
            return pd.Series(s.fundingRate.values, index=pd.to_datetime(s.time, unit="ms", utc=True), name="funding")
    base = TESTNET if network == "testnet" else MAINNET
    info = _info(base)
    end = int(time.time() * 1000)
    start = end - lookback_days * 86_400_000
    rows, cur = [], start
    while cur < end:
        batch = info.funding_history(coin, startTime=cur)
        if not batch:
            break
        rows.extend(batch)
        last_t = max(int(r["time"]) for r in batch)
        if last_t <= cur:
            break
        cur = last_t + 1
        if len(batch) < 500:
            break
        time.sleep(0.05)
    if not rows:
        return pd.Series(dtype=float, name="funding")
    df = pd.DataFrame(rows).drop_duplicates("time")
    if use_cache:
        os.makedirs(CACHE, exist_ok=True)
        df.to_csv(p, index=False)
    return pd.Series(df.fundingRate.astype(float).values,
                     index=pd.to_datetime(df.time.astype("int64"), unit="ms", utc=True), name="funding")

def list_symbols(market="futures", network="mainnet"):
    info = _info(TESTNET if network == "testnet" else MAINNET)
    if market == "spot":
        meta = info.spot_meta()
        return [u.get("name") for u in meta.get("universe", [])]
    return [u["name"] for u in info.meta().get("universe", [])]

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["candles", "funding", "symbols"])
    ap.add_argument("symbol", nargs="?", default="ETH")
    ap.add_argument("--market", default="futures", choices=["spot", "futures"])
    ap.add_argument("--granularity", default="1h")
    ap.add_argument("--start"); ap.add_argument("--end")
    ap.add_argument("--network", default="mainnet", choices=["mainnet", "testnet"])
    a = ap.parse_args()
    if a.cmd == "symbols":
        print("\n".join(list_symbols(a.market, a.network)[:80]))
    elif a.cmd == "funding":
        s = funding_history(a.symbol, network=a.network)
        print(s.tail(10)); print("n=", len(s))
    else:
        df = fetch_candles(a.symbol, a.market, a.granularity, a.start, a.end, network=a.network)
        print(df.tail(3)); print("rows", len(df), "from", df.index.min(), "to", df.index.max())

if __name__ == "__main__":
    main()
