"""Exchange public data layer (no API Key): candles / funding / symbol lists, with paging, rate-limit retries, and local CSV cache (./data).

CLI examples:
  python data.py candles BTCUSDT --market spot --granularity 1d --start 2018-01-01
  python data.py candles ETHUSDT --granularity 1h --start 2025-11-01 --end 2026-11-01
  python data.py candles BTCUSDT --market futures --granularity 1h --start 2026-01-01 --kind mark   # kind: trade|mark|index
  python data.py funding BTCUSDT
  python data.py symbols --market futures
Python:
  from data import fetch_candles, fetch_many, funding_history
  df = fetch_candles("BTCUSDT", "spot", "1h", "2025-01-01")   # DataFrame: ts(UTC), open, high, low, close, volume, quote_volume
"""
import argparse, json, os, time, urllib.request, urllib.error
import pandas as pd

BASE = "https://api.bitget.com"
CACHE = os.environ.get("BITGET_DATA_DIR", "data")
# Unified granularity -> (spot spelling, futures spelling, ms)
GRAN = {"1m": ("1min", "1m", 60_000), "5m": ("5min", "5m", 300_000), "15m": ("15min", "15m", 900_000),
        "30m": ("30min", "30m", 1_800_000), "1h": ("1h", "1H", 3_600_000), "4h": ("4h", "4H", 14_400_000),
        "1d": ("1day", "1D", 86_400_000), "1w": ("1week", "1W", 604_800_000)}
ALIAS = {"1min": "1m", "5min": "5m", "15min": "15m", "30min": "30m", "1H": "1h", "4H": "4h", "1day": "1d", "1D": "1d", "1week": "1w"}

def _get(path, params, retries=6):
    url = BASE + path + "?" + "&".join(f"{k}={v}" for k, v in params.items() if v is not None)
    for i in range(retries):
        try:
            d = json.load(urllib.request.urlopen(url, timeout=20))
            if d.get("code") == "00000": return d["data"]
            raise RuntimeError(d)
        except urllib.error.HTTPError as e:
            body = e.read().decode()[:200]
            if e.code == 429 or "429" in body or "too many" in body.lower():
                time.sleep(1.5 * (i + 1)); continue
            raise RuntimeError(f"HTTP {e.code} {url}: {body}")
        except (urllib.error.URLError, TimeoutError) as e:
            time.sleep(2 * (i + 1))
    raise RuntimeError(f"Request failed (check network/proxy): {url}")

def _ms(x):
    if x is None: return None
    if isinstance(x, (int, float)): return int(x)
    return int(pd.Timestamp(x, tz="UTC").timestamp() * 1000)

def _norm(g): return ALIAS.get(g, g)

def fetch_candles(symbol, market="spot", granularity="1h", start=None, end=None, kind="trade", use_cache=True, verbose=True):
    """Page [start, end) candles. market: spot|futures (USDT-perp); kind: trade|mark|index (last two futures only).
    If start is empty, pull as far back as possible. Returns ascending, de-duplicated DataFrame."""
    g = _norm(granularity); sg, fg, step = GRAN[g]
    end_ms = _ms(end) or int(time.time() * 1000); start_ms = _ms(start) or 0
    path_cache = os.path.join(CACHE, f"{market}_{kind}_{symbol}_{g}.csv")
    cached = pd.read_csv(path_cache) if use_cache and os.path.exists(path_cache) else None
    if cached is not None and len(cached):
        lo, hi = int(cached.ts_ms.min()), int(cached.ts_ms.max())
        need_old = start_ms < lo - step and not cached.attrs.get("complete")
        if start_ms >= lo and end_ms <= hi + step:
            out = cached[(cached.ts_ms >= start_ms) & (cached.ts_ms < end_ms)]
            return _finish(out)
    rows, cur = [], end_ms
    if market == "spot":
        path, params = "/api/v2/spot/market/history-candles", {"symbol": symbol, "granularity": sg, "limit": 200}
    else:
        path = {"trade": "/api/v2/mix/market/history-candles", "mark": "/api/v2/mix/market/history-mark-candles",
                "index": "/api/v2/mix/market/history-index-candles"}[kind]
        params = {"symbol": symbol, "productType": "USDT-FUTURES", "granularity": fg, "limit": 200}
    empty = 0
    while cur > start_ms:
        data = _get(path, {**params, "endTime": cur})
        if not data:
            empty += 1
            # Futures endpoint has a time-window limit; on empty pages jump back one window, retry up to 3 times
            if empty > 3: break
            cur -= step * 200; continue
        empty = 0
        rows += data
        first = min(int(r[0]) for r in data)
        if first >= cur: break
        cur = first - 1
        if verbose and len(rows) % 2000 < 200:
            print(f"  {symbol} {market} {g}: {len(rows)} bars, reached {pd.Timestamp(first, unit='ms')}", flush=True)
        time.sleep(0.06)  # ~15 req/s, under public rate limits
    df = pd.DataFrame([r[:7] for r in rows], columns=["ts_ms", "open", "high", "low", "close", "volume", "quote_volume"])
    if cached is not None: df = pd.concat([cached[df.columns], df])
    df = df.astype(float).astype({"ts_ms": "int64"}).drop_duplicates("ts_ms").sort_values("ts_ms")
    if use_cache:
        os.makedirs(CACHE, exist_ok=True); df.to_csv(path_cache, index=False)
    return _finish(df[(df.ts_ms >= start_ms) & (df.ts_ms < end_ms)])

def _finish(df):
    df = df.copy(); df["ts"] = pd.to_datetime(df.ts_ms, unit="ms", utc=True)
    return df.set_index("ts")

def fetch_many(symbols, market="spot", granularity="1h", start=None, end=None, field="close"):
    """Multi-symbol wide DataFrame (columns = symbols), time-aligned."""
    return pd.DataFrame({s: fetch_candles(s, market, granularity, start, end)[field] for s in symbols})

def funding_history(symbol, use_cache=True):
    """USDT-perp funding history (100/page, paginate to end). Series of fundingRate indexed by settlement time."""
    p = os.path.join(CACHE, f"funding_{symbol}.csv"); rows, page = [], 1
    while True:
        d = _get("/api/v2/mix/market/history-fund-rate", {"symbol": symbol, "productType": "USDT-FUTURES", "pageSize": 100, "pageNo": page})
        if not d: break
        rows += d; page += 1; time.sleep(0.06)
    df = pd.DataFrame(rows); df["ts"] = pd.to_datetime(df.fundingTime.astype("int64"), unit="ms", utc=True)
    s = df.set_index("ts").fundingRate.astype(float).sort_index()
    if use_cache: os.makedirs(CACHE, exist_ok=True); s.to_csv(p)
    return s

def symbols(market="spot"):
    if market == "spot": return [d["symbol"] for d in _get("/api/v2/spot/public/symbols", {}) if d.get("status") == "online"]
    return [d["symbol"] for d in _get("/api/v2/mix/market/contracts", {"productType": "USDT-FUTURES"})]

def open_interest(symbol):  # current snapshot only; no history
    return _get("/api/v2/mix/market/open-interest", {"symbol": symbol, "productType": "USDT-FUTURES"})

def orderbook(symbol, limit=50):  # current snapshot only
    return _get("/api/v2/spot/market/orderbook", {"symbol": symbol, "limit": limit})

if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("cmd", choices=["candles", "funding", "symbols"])
    ap.add_argument("symbol", nargs="?", default="BTCUSDT"); ap.add_argument("--market", default="spot")
    ap.add_argument("--granularity", default="1h"); ap.add_argument("--start"); ap.add_argument("--end")
    ap.add_argument("--kind", default="trade"); a = ap.parse_args()
    if a.cmd == "candles":
        df = fetch_candles(a.symbol, a.market, a.granularity, a.start, a.end, a.kind)
        print(df.tail(3)); print(f"{len(df)} bars  {df.index.min()} → {df.index.max()}")
    elif a.cmd == "funding":
        s = funding_history(a.symbol); print(s.tail(3)); print(f"{len(s)} rows  {s.index.min()} → {s.index.max()}  mean {s.mean():.6f}")
    else:
        ss = symbols(a.market); print(len(ss), ss[:20])
