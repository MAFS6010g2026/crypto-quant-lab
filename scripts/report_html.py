#!/usr/bin/env python3
"""Build a single-file self-contained HTML result page from a backtest (dark finance UI, browser-local recalc).

Usage (prefer via backtest.py):
  python backtest.py --symbols ETHUSDT --granularity 1h --start 2025-01-01 \\
      --strategy rsi --params '{"n":14,"lo":30,"hi":70}' --fee 0.001 --split 0.7 \\
      --html report.html

Or this script directly (args aligned with backtest):
  python report_html.py --symbols ETHUSDT --strategy rsi --split 0.7 --html report.html
"""
from __future__ import annotations
import argparse, json, math, os, sys
from datetime import datetime, timezone

import numpy as np
import pandas as pd

# same-directory imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from data import fetch_candles, funding_history
from risk import RiskConfig
from strategies import STRATEGIES, STRATEGY_META
from backtest import load, simulate, metrics, BARS_PER_YEAR

MAX_EMBED_BARS = 5000  # keep a few thousand bars so the page stays snappy


def _advice(train: dict | None, test: dict | None, full: dict) -> list[str]:
    tips = []
    if train and test:
        tr = train.get("total_return_pct")
        te = test.get("total_return_pct")
        if tr is not None and te is not None:
            if tr > 10 and te < tr - 15:
                tips.append("Train return is much higher than Test — overfitting risk: fewer param searches, or a longer out-of-sample window.")
            if te is not None and tr is not None and te > tr + 15:
                tips.append("Test clearly beats Train: may be a regime shift; do not size up live on this window alone.")
            if te is not None and te < -10:
                tips.append("Test loss is large: check fees and trade count first, then consider looser signals or smaller size.")
        ts = train.get("sharpe")
        es = test.get("sharpe")
        if ts is not None and es is not None and ts > 1.0 and es < 0.2:
            tips.append("Train Sharpe is OK but Test Sharpe is weak — params may only fit one historical regime.")
    mdd = (test or full).get("max_drawdown_pct")
    if mdd is not None and mdd < -25:
        tips.append(f"Max drawdown about {mdd}% — large: tighten stops, lower max_position_pct, or trade less often.")
    ntr = (test or full).get("trades")
    if ntr == 0 or ntr is None:
        # full trades still useful
        ntr = full.get("trades")
    if isinstance(ntr, int):
        if ntr < 5:
            tips.append("Too few trades for statistical meaning: shorter TF, looser entries, or a longer backtest range.")
        elif ntr > 400:
            tips.append("Trading too often — fees will eat returns: filter signals harder (MA gap, RSI thresholds).")
    wr = (test or full).get("win_rate_pct")
    if wr is not None and wr < 35 and (full.get("total_return_pct") or 0) < 0:
        tips.append("Low win rate and negative total return: check if you are fighting the trend, or compare vs buy & hold.")
    bench = (test or full).get("benchmark_return_pct")
    ret = (test or full).get("total_return_pct")
    if bench is not None and ret is not None and ret < bench - 5:
        tips.append("Strategy underperforms equal-weight buy & hold: prove a stable edge before going live.")
    if not tips:
        tips.append("Train/Test gap is small and drawdown is controlled: take the same params to paper and watch slippage/fills.")
        tips.append("When changing params, also check the Original results column — avoid optimizing only the test set.")
    return tips[:4]


def _segment_metrics(curve, trades_flags, bench, capital, bpy, sl):
    """Recompute metrics on a time slice; trade stats are approximate (full per-bar PnL attribution is hard here)."""
    c = curve[sl]
    if len(c) < 2:
        return None
    b = bench[sl]
    # normalize to capital start
    c0 = c / c.iloc[0] * capital
    b0 = b / b.iloc[0] * capital
    # trade counts are better from position changes outside; here return metrics only
    return metrics(c0, [], bpy, b0)


def _trim_series(idx, arrays: dict, cut_pos: int | None, max_bars=MAX_EMBED_BARS):
    """Keep a contiguous window; prefer the recent test segment; include train tail for indicator warm-up when possible."""
    n = len(idx)
    if n <= max_bars:
        return 0, n, cut_pos
    if cut_pos is None:
        return n - max_bars, n, None
    end = n
    start = n - max_bars
    # if start is still in train, window = train tail + recent test
    new_cut = cut_pos - start
    if new_cut < 0:
        # whole window is test: still prefer recent data; see Original results for Train
        new_cut = 0
    return start, end, new_cut


def build_payload(
    data: dict,
    target,
    cfg: RiskConfig,
    fee: float,
    use_funding: bool,
    strategy: str,
    params: dict,
    symbols: list,
    market: str,
    gran: str,
    split: float | None,
    group: str = "Demo",
    max_bars: int = MAX_EMBED_BARS,
):
    curve, trades = simulate(data, target, cfg, fee, use_funding)
    close = pd.DataFrame({k: d.close for k, d in data.items()})
    bench = cfg.capital_usdt * (close / close.iloc[0]).mean(axis=1)
    bpy = BARS_PER_YEAR.get(gran, 8760)
    full_m = metrics(curve, trades, bpy, bench)

    cut = None
    cut_pos = None
    train_m = test_m = None
    if split:
        cut_pos = int(len(curve) * split)
        cut_pos = min(max(cut_pos, 1), len(curve) - 1)
        cut = curve.index[cut_pos]
        # segment metrics (simplified: slice curve; full trades stay on full only)
        train_m = metrics(
            curve.iloc[:cut_pos] / curve.iloc[0] * cfg.capital_usdt,
            [],
            bpy,
            bench.iloc[:cut_pos] / bench.iloc[0] * cfg.capital_usdt,
        )
        test_m = metrics(
            curve.iloc[cut_pos:] / curve.iloc[cut_pos] * cfg.capital_usdt,
            [],
            bpy,
            bench.iloc[cut_pos:] / bench.iloc[cut_pos] * cfg.capital_usdt,
        )
        # rough segment trade counts from target-position changes
        tgt = target.reindex(close.index).fillna(0).clip(-1, 1)
        ch = tgt.diff().abs().sum(axis=1)
        train_m["trades"] = int((ch.iloc[1:cut_pos] > 1e-9).sum())
        test_m["trades"] = int((ch.iloc[cut_pos:] > 1e-9).sum())
        train_m["win_rate_pct"] = None
        test_m["win_rate_pct"] = None

    meta = STRATEGY_META.get(strategy, {
        "title": strategy,
        "logic": "Custom strategy (browser recalc only for registered templates).",
        "browser_recalc": False,
        "params": [{"key": k, "label": k, "min": 0, "max": 100, "step": 1, "default": v}
                   for k, v in params.items() if isinstance(v, (int, float))],
    })
    # override schema defaults with actual params
    schema = []
    for p in meta.get("params", []):
        item = dict(p)
        if item["key"] in params:
            item["default"] = params[item["key"]]
        schema.append(item)

    # embed series
    idx = close.index
    start, end, rel_cut = _trim_series(idx, {}, cut_pos, max_bars)
    idx_s = idx[start:end]
    # per-symbol OHLCV (+ funding)
    series_syms = {}
    for s in symbols:
        d = data[s].reindex(idx).ffill().iloc[start:end]
        series_syms[s] = {
            "open": [None if pd.isna(x) else round(float(x), 6) for x in d.open],
            "high": [None if pd.isna(x) else round(float(x), 6) for x in d.high],
            "low": [None if pd.isna(x) else round(float(x), 6) for x in d.low],
            "close": [None if pd.isna(x) else round(float(x), 6) for x in d.close],
            "volume": [None if pd.isna(x) else round(float(x), 4) for x in d.volume],
        }
        if "funding" in d.columns:
            series_syms[s]["funding"] = [0.0 if pd.isna(x) else float(x) for x in d.funding]

    # original equity (aligned to embed window)
    eq_embed = [round(float(x), 6) for x in curve.iloc[start:end]]
    bh_embed = [round(float(x), 6) for x in bench.iloc[start:end]]
    # original signal (unshifted target on primary symbol)
    tgt = target.reindex(idx).fillna(0).clip(-1, 1).iloc[start:end]
    primary = symbols[0]
    sig_embed = [round(float(x), 6) for x in tgt[primary]]

    ts_ms = [int(t.timestamp() * 1000) for t in idx_s]

    payload = {
        "group": group,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "strategy": strategy,
        "strategy_title": meta.get("title", strategy),
        "logic": meta.get("logic", ""),
        "browser_recalc": bool(meta.get("browser_recalc", False)) and strategy in ("ma_cross", "rsi", "momentum", "funding"),
        "params": params,
        "param_schema": schema,
        "symbols": symbols,
        "market": market,
        "granularity": gran,
        "fee": fee,
        "funding": use_funding,
        "split": split,
        "capital": cfg.capital_usdt,
        "max_position_pct": cfg.max_position_pct,
        "max_leverage": cfg.max_leverage,
        "stop_loss_pct": cfg.stop_loss_pct,
        "take_profit_pct": cfg.take_profit_pct,
        "cut_index": rel_cut,  # within embedded series; None if no split
        "range": {
            "start": str(idx_s[0])[:19],
            "end": str(idx_s[-1])[:19],
            "bars_embedded": len(idx_s),
            "bars_full": len(idx),
        },
        "metrics_original": {
            "full": full_m,
            "train": train_m,
            "test": test_m,
        },
        "advice": _advice(train_m, test_m, full_m),
        "ts": ts_ms,
        "series": series_syms,
        "equity_original": eq_embed,
        "benchmark_original": bh_embed,
        "signal_original": sig_embed,
        "primary": primary,
    }
    return payload


def render_html(payload: dict) -> str:
    data_json = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    # prevent script break: replace < > even if rare in JSON
    data_json = data_json.replace("<", "\\u003c").replace(">", "\\u003e")
    return HTML_TEMPLATE.replace("__PAYLOAD__", data_json)


def write_html(payload: dict, path: str):
    html = render_html(payload)
    os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)
    return path


def run_from_args(a):
    if a.start is None:
        a.start = str(pd.Timestamp.utcnow().normalize() - pd.Timedelta(days=365))[:10]
    syms = a.symbols.split(",")
    gran = a.granularity.replace("min", "m").replace("day", "d").replace("H", "h")
    params = json.loads(a.params)
    data = load(syms, a.market, gran, a.start, a.end, a.funding)
    if a.strategy not in STRATEGIES:
        raise SystemExit(f"Unknown strategy {a.strategy}; choices: {list(STRATEGIES)}")
    target = STRATEGIES[a.strategy](data, params)
    cfg = RiskConfig(capital_usdt=a.capital)
    payload = build_payload(
        data, target, cfg, a.fee, a.funding, a.strategy, params, syms, a.market, gran, a.split,
        group=a.group, max_bars=a.max_bars,
    )
    write_html(payload, a.html)
    print(json.dumps({
        "html": a.html,
        "strategy": a.strategy,
        "bars_embedded": payload["range"]["bars_embedded"],
        "metrics": payload["metrics_original"],
        "advice": payload["advice"],
    }, ensure_ascii=False, indent=2))


def main():
    ap = argparse.ArgumentParser(description="Generate Quant Lab single-file HTML result page")
    ap.add_argument("--symbols", default="ETHUSDT")
    ap.add_argument("--market", default="spot", choices=["spot", "futures"])
    ap.add_argument("--granularity", default="1h")
    ap.add_argument("--start", default=None)
    ap.add_argument("--end", default=None)
    ap.add_argument("--strategy", default="rsi")
    ap.add_argument("--params", default='{"n":14,"lo":30,"hi":70}')
    ap.add_argument("--fee", type=float, default=0.001)
    ap.add_argument("--funding", action="store_true")
    ap.add_argument("--split", type=float, default=0.7)
    ap.add_argument("--capital", type=float, default=100.0)
    ap.add_argument("--group", default="Demo")
    ap.add_argument("--html", default="report.html")
    ap.add_argument("--max-bars", type=int, default=MAX_EMBED_BARS)
    a = ap.parse_args()
    run_from_args(a)


# ---------------- HTML (inline CSS/JS, no external CDN) ----------------
HTML_TEMPLATE = r'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>MAFS6010G Crypto Finance · Quant Lab results</title>
<style>
:root{
  --bg:#0b1220; --bg2:#111a2e; --card:#151f35; --card2:#1a2540;
  --line:#243252; --text:#e8eefc; --muted:#8b9bb8; --accent:#3b82f6;
  --good:#22c55e; --bad:#ef4444; --warn:#f59e0b; --test:#a78bfa; --train:#38bdf8;
  --radius:14px; --shadow:0 8px 28px rgba(0,0,0,.35);
  font-family: "Segoe UI", system-ui, -apple-system, sans-serif;
}
*{box-sizing:border-box}
body{margin:0;background:radial-gradient(1200px 600px at 10% -10%,#1a2a4a 0%,var(--bg) 55%);color:var(--text);min-height:100vh}
.wrap{max-width:1180px;margin:0 auto;padding:24px 18px 48px}
.header{display:flex;flex-wrap:wrap;gap:14px;justify-content:space-between;align-items:flex-end;margin-bottom:18px}
.header h1{margin:0;font-size:1.45rem;letter-spacing:.02em}
.badge{display:inline-flex;align-items:center;gap:6px;padding:4px 10px;border-radius:999px;background:var(--card2);border:1px solid var(--line);color:var(--muted);font-size:.78rem}
.meta{color:var(--muted);font-size:.85rem;line-height:1.6}
.grid{display:grid;gap:14px}
.grid-2{grid-template-columns:1.2fr .8fr}
.grid-3{grid-template-columns:repeat(3,1fr)}
@media(max-width:900px){.grid-2,.grid-3{grid-template-columns:1fr}}
.card{background:linear-gradient(180deg,var(--card),var(--bg2));border:1px solid var(--line);border-radius:var(--radius);padding:16px 18px;box-shadow:var(--shadow)}
.card h2{margin:0 0 12px;font-size:1rem;font-weight:600;color:#c9d7f2}
.card h3{margin:0 0 8px;font-size:.9rem;color:#c9d7f2}
.logic{color:var(--muted);font-size:.9rem;line-height:1.55;margin:0 0 12px}
.params{display:grid;gap:10px}
.param{display:grid;grid-template-columns:110px 1fr 64px;gap:10px;align-items:center}
.param label{font-size:.82rem;color:var(--muted)}
.param input[type=range]{width:100%;accent-color:var(--accent)}
.param input[type=number]{width:64px;background:var(--bg);border:1px solid var(--line);color:var(--text);border-radius:8px;padding:6px 8px}
.actions{display:flex;flex-wrap:wrap;gap:8px;margin-top:12px}
button{background:var(--accent);color:white;border:0;border-radius:10px;padding:8px 14px;font-weight:600;cursor:pointer}
button.secondary{background:transparent;border:1px solid var(--line);color:var(--text)}
button:disabled{opacity:.5;cursor:not-allowed}
.metrics{display:grid;grid-template-columns:1fr 1fr;gap:12px}
.mcol{background:rgba(0,0,0,.18);border:1px solid var(--line);border-radius:12px;padding:12px}
.mcol .tag{font-size:.72rem;text-transform:uppercase;letter-spacing:.06em;color:var(--muted);margin-bottom:8px}
.mrow{display:flex;justify-content:space-between;gap:8px;padding:5px 0;border-bottom:1px dashed rgba(36,50,82,.8);font-size:.86rem}
.mrow:last-child{border:0}
.mrow .k{color:var(--muted)}
.pos{color:var(--good)}.neg{color:var(--bad)}
.advice{display:grid;gap:8px}
.tip{padding:10px 12px;border-radius:10px;border:1px solid var(--line);background:rgba(59,130,246,.08);font-size:.88rem;line-height:1.45}
.tip.warn{background:rgba(245,158,11,.1);border-color:rgba(245,158,11,.35)}
.tip.bad{background:rgba(239,68,68,.1);border-color:rgba(239,68,68,.35)}
.tip.good{background:rgba(34,197,94,.08);border-color:rgba(34,197,94,.3)}
.chart-tools{display:flex;flex-wrap:wrap;gap:8px;margin-bottom:10px;align-items:center}
.seg{display:inline-flex;border:1px solid var(--line);border-radius:10px;overflow:hidden}
.seg button{border-radius:0;background:transparent;border:0;color:var(--muted);padding:7px 12px}
.seg button.active{background:rgba(59,130,246,.25);color:#fff}
canvas{width:100%;height:280px;background:#0a1020;border-radius:12px;border:1px solid var(--line)}
.legend{display:flex;flex-wrap:wrap;gap:12px;margin-top:8px;color:var(--muted);font-size:.78rem}
.dot{display:inline-block;width:10px;height:10px;border-radius:50%;margin-right:4px}
.table-tools{display:flex;flex-wrap:wrap;gap:8px;margin-bottom:8px}
.table-tools input{background:var(--bg);border:1px solid var(--line);color:var(--text);border-radius:8px;padding:7px 10px}
.table-wrap{overflow:auto;max-height:360px;border:1px solid var(--line);border-radius:12px}
table{width:100%;border-collapse:collapse;font-size:.8rem}
th,td{padding:7px 8px;border-bottom:1px solid rgba(36,50,82,.7);text-align:right;white-space:nowrap}
th{position:sticky;top:0;background:#132038;color:var(--muted);font-weight:600;text-align:right}
td:first-child,th:first-child{text-align:left}
tr.chg{background:rgba(167,139,250,.12)}
.orig{opacity:.95}
.foot{margin-top:18px;color:var(--muted);font-size:.75rem;line-height:1.5}
.note{font-size:.78rem;color:var(--muted);margin-top:6px}
</style>
</head>
<body>
<div class="wrap">
  <div class="header">
    <div>
      <h1 id="title">MAFS6010G Crypto Finance · Quant Lab results</h1>
      <div class="meta" id="subtitle"></div>
    </div>
    <div class="badge" id="badge"></div>
  </div>

  <div class="grid grid-2" style="margin-bottom:14px">
    <div class="card">
      <h2>Strategy</h2>
      <p class="logic" id="logic"></p>
      <div class="params" id="params"></div>
      <div class="actions">
        <button id="btnRecalc" type="button">Recalculate</button>
        <button id="btnReset" class="secondary" type="button">Restore original params</button>
        <label class="note" style="display:flex;align-items:center;gap:6px;margin:0">
          <input type="checkbox" id="autoRecalc" checked/> Auto-recalc on change
        </label>
      </div>
      <p class="note" id="recalcNote"></p>
    </div>
    <div class="card orig">
      <h2>Original results (at export)</h2>
      <div class="metrics" id="metricsOrig"></div>
    </div>
  </div>

  <div class="card" style="margin-bottom:14px">
    <h2>Current results (updates with params)</h2>
    <div class="metrics" id="metricsLive"></div>
  </div>

  <div class="card" style="margin-bottom:14px">
    <h2>Advice</h2>
    <div class="advice" id="advice"></div>
  </div>

  <div class="card" style="margin-bottom:14px">
    <h2>Price & equity</h2>
    <div class="chart-tools">
      <div class="seg" id="viewSeg">
        <button type="button" data-view="all" class="active">All</button>
        <button type="button" data-view="train">Train</button>
        <button type="button" data-view="test">Test</button>
      </div>
    </div>
    <canvas id="chartPrice" height="280"></canvas>
    <canvas id="chartEq" height="280" style="margin-top:10px"></canvas>
    <div class="legend">
      <span><i class="dot" style="background:#38bdf8"></i>Price (normalized)</span>
      <span><i class="dot" style="background:#22c55e"></i>Strategy equity</span>
      <span><i class="dot" style="background:#64748b"></i>Buy & hold</span>
      <span><i class="dot" style="background:#a78bfa"></i>Test region</span>
    </div>
  </div>

  <div class="card">
    <h2>Test-set data (sample)</h2>
    <div class="table-tools">
      <input id="q" placeholder="Search time contains…"/>
      <label class="note">Last N bars <input id="lastN" type="number" min="20" max="2000" value="120" style="width:72px"/></label>
    </div>
    <div class="table-wrap">
      <table>
        <thead><tr><th>Time (UTC)</th><th>Open</th><th>High</th><th>Low</th><th>Close</th><th>Signal</th><th>Position</th></tr></thead>
        <tbody id="tbody"></tbody>
      </table>
    </div>
  </div>

  <div class="foot" id="foot"></div>
</div>

<script id="payload" type="application/json">__PAYLOAD__</script>
<script>
(function(){
  const P = JSON.parse(document.getElementById('payload').textContent);
  const state = {
    params: Object.assign({}, P.params),
    view: 'all',
    live: null,
  };

  function fmtPct(x){
    if(x===null||x===undefined||Number.isNaN(x)) return '—';
    const s = (x>=0?'+':'') + Number(x).toFixed(2) + '%';
    return s;
  }
  function clsPct(x){
    if(x===null||x===undefined||Number.isNaN(x)) return '';
    return x>=0 ? 'pos' : 'neg';
  }
  function fmtNum(x,d){
    if(x===null||x===undefined||Number.isNaN(x)) return '—';
    return Number(x).toFixed(d===undefined?2:d);
  }
  function tsLabel(ms){
    const d = new Date(ms);
    const p = n => String(n).padStart(2,'0');
    return d.getUTCFullYear()+'-'+p(d.getUTCMonth()+1)+'-'+p(d.getUTCDate())+' '+p(d.getUTCHours())+':'+p(d.getUTCMinutes());
  }

  // ---- indicators / signals (browser) ----
  function sma(arr, n){
    const out = new Array(arr.length).fill(null);
    let sum = 0;
    for(let i=0;i<arr.length;i++){
      const v = arr[i];
      if(v==null){ out[i]=null; continue; }
      sum += v;
      if(i>=n) sum -= arr[i-n]==null?0:arr[i-n];
      if(i>=n-1){
        let ok=true;
        for(let k=i-n+1;k<=i;k++) if(arr[k]==null){ok=false;break;}
        out[i] = ok ? sum/n : null;
      }
    }
    return out;
  }
  function rsi(closes, n){
    // Match strategies.py: SMA of gains/losses over n (SMA RSI)
    const out = new Array(closes.length).fill(null);
    const ups = new Array(closes.length).fill(0);
    const dns = new Array(closes.length).fill(0);
    for(let i=1;i<closes.length;i++){
      const d = (closes[i]==null||closes[i-1]==null) ? 0 : closes[i]-closes[i-1];
      ups[i] = d>0?d:0; dns[i] = d<0?-d:0;
    }
    let sumU=0, sumD=0;
    for(let i=1;i<closes.length;i++){
      sumU += ups[i]; sumD += dns[i];
      if(i>n){ sumU -= ups[i-n]; sumD -= dns[i-n]; }
      if(i>=n){
        const up=sumU/n, dn=sumD/n;
        out[i] = dn===0 ? 100 : 100 - 100/(1+up/dn);
      }
    }
    return out;
  }
  function signalsFor(params){
    const syms = P.symbols;
    const n = P.ts.length;
    const tgt = {};
    for(const s of syms) tgt[s] = new Array(n).fill(0);
    if(P.strategy==='ma_cross'){
      let f = Math.max(2, parseInt(params.fast)||10);
      let slow = Math.max(f+1, parseInt(params.slow)||30);
      for(const s of syms){
        const c = P.series[s].close;
        const a = sma(c,f), b = sma(c,slow);
        for(let i=0;i<n;i++){
          if(a[i]==null||b[i]==null) tgt[s][i]=0;
          else tgt[s][i] = a[i]>b[i] ? 1 : 0;
        }
      }
    } else if(P.strategy==='rsi'){
      const rn = Math.max(2, parseInt(params.n)||14);
      const lo = Number(params.lo), hi = Number(params.hi);
      for(const s of syms){
        const c = P.series[s].close;
        const r = rsi(c, rn);
        let pos = 0;
        for(let i=0;i<n;i++){
          if(r[i]==null){ tgt[s][i]=pos; continue; }
          if(r[i]<lo) pos=1;
          if(r[i]>hi) pos=0;
          tgt[s][i]=pos;
        }
      }
    } else if(P.strategy==='momentum'){
      const lb = Math.max(1, parseInt(params.lookback)||168);
      const top = Math.max(1, Math.min(syms.length, parseInt(params.top)||1));
      for(let i=0;i<n;i++){
        const scores = [];
        for(const s of syms){
          const c = P.series[s].close;
          if(i<lb || c[i]==null || c[i-lb]==null || c[i-lb]===0) scores.push({s,v:-1e99});
          else scores.push({s,v: c[i]/c[i-lb]-1});
        }
        scores.sort((a,b)=>b.v-a.v);
        for(let k=0;k<top;k++) if(scores[k] && scores[k].v>-1e98) tgt[scores[k].s][i]=1/top;
      }
    } else if(P.strategy==='funding'){
      const wn = Math.max(1, parseInt(params.n)||3);
      const th = Number(params.th);
      for(const s of syms){
        const fr = P.series[s].funding || new Array(n).fill(0);
        // forward-fill zeros as nan-like then rolling mean of last wn non-filled? match python: replace 0 nan ffill rolling
        const filled = new Array(n).fill(0);
        let last=null;
        for(let i=0;i<n;i++){
          let v = fr[i];
          if(v===0 || v==null) v = last;
          else last = v;
          filled[i]= v==null?0:v;
        }
        for(let i=0;i<n;i++){
          let sum=0,cnt=0;
          for(let k=Math.max(0,i-wn+1);k<=i;k++){ sum+=filled[k]; cnt++; }
          const m = sum/cnt;
          tgt[s][i] = (Math.abs(m)>th) ? (m>0?-1:1) : 0;
        }
      }
    } else {
      // fallback: original signal on primary only
      for(let i=0;i<n;i++) tgt[P.primary][i]=P.signal_original[i]||0;
    }
    return tgt;
  }

  function simulate(tgt){
    const syms = P.symbols;
    const n = P.ts.length;
    const fee = P.fee;
    const maxPos = P.max_position_pct;
    const maxLev = P.max_leverage;
    const sl = P.stop_loss_pct;
    const tp = P.take_profit_pct;
    const capital = P.capital;
    const closes = syms.map(s=>P.series[s].close);
    const funds = syms.map(s=> (P.series[s].funding||null));
    const m = syms.length;
    // shift 1
    const T = Array.from({length:n},()=>new Array(m).fill(0));
    for(let i=1;i<n;i++){
      let gross=0;
      const raw = new Array(m);
      for(let j=0;j<m;j++){
        raw[j] = Math.max(-1, Math.min(1, tgt[syms[j]][i-1]||0)) * maxPos;
        gross += Math.abs(raw[j]);
      }
      const scale = gross>1e-12 ? Math.min(1, maxLev/gross) : 1;
      for(let j=0;j<m;j++) T[i][j]=raw[j]*scale;
    }
    let eq = capital;
    const curve = new Array(n);
    const pos = new Array(n);
    let w = new Array(m).fill(0);
    let entry = new Array(m).fill(NaN);
    let blocked = new Array(m).fill(false);
    const trades = [];
    let day = null, dayStart = capital;
    for(let t=0;t<n;t++){
      if(t>0){
        let pnl=0;
        for(let j=0;j<m;j++){
          const p0=closes[j][t-1], p1=closes[j][t];
          if(p0 && p1) pnl += w[j]*((p1/p0)-1);
          if(P.funding && funds[j]) pnl -= w[j]*(funds[j][t]||0);
        }
        eq *= (1+pnl);
      }
      const d = new Date(P.ts[t]).toISOString().slice(0,10);
      if(d!==day){ day=d; dayStart=eq; }
      let want = T[t].slice();
      for(let j=0;j<m;j++){
        if(w[j]!==0 && !Number.isNaN(entry[j])){
          const side = w[j]>0?1:-1;
          const r = (closes[j][t]/entry[j]-1)*side;
          if(r <= -sl || r >= tp){ want[j]=0; blocked[j]=true; }
        }
        if(Math.abs(T[t][j])<1e-12) blocked[j]=false;
        if(blocked[j]) want[j]=0;
      }
      if(eq <= dayStart*(1-0.05)) want = new Array(m).fill(0);
      let turn=0;
      for(let j=0;j<m;j++) turn += Math.abs(want[j]-w[j]);
      if(turn>1e-9){
        eq *= (1 - fee*turn);
        for(let j=0;j<m;j++){
          if(w[j]!==0 && (want[j]===0 || Math.sign(want[j])!==Math.sign(w[j]))){
            trades.push(((closes[j][t]/entry[j]-1)*Math.sign(w[j])) - 2*fee);
          }
          if(want[j]!==0 && (w[j]===0 || Math.sign(want[j])!==Math.sign(w[j]))) entry[j]=closes[j][t];
          if(want[j]===0) entry[j]=NaN;
        }
        w = want;
      }
      curve[t]=eq;
      pos[t]=w[syms.indexOf(P.primary)]||0;
    }
    // benchmark EW
    const bh = new Array(n);
    const c0 = syms.map(s=>P.series[s].close[0]||1);
    for(let t=0;t<n;t++){
      let s=0,cnt=0;
      for(let j=0;j<m;j++){
        const c=closes[j][t];
        if(c!=null && c0[j]){ s += c/c0[j]; cnt++; }
      }
      bh[t] = capital * (cnt? s/cnt : 1);
    }
    return {curve, bh, pos, trades, tgtPrimary: tgt[P.primary]};
  }

  function metricsOf(curve, bh, trades, i0, i1){
    if(i1-i0<2) return null;
    const c = curve.slice(i0,i1);
    const b = bh.slice(i0,i1);
    const c0 = c[0], b0=b[0];
    const cn = c.map(x=>x/c0*P.capital);
    const bn = b.map(x=>x/b0*P.capital);
    const rets=[];
    for(let i=1;i<cn.length;i++) rets.push(cn[i]/cn[i-1]-1);
    const mean = rets.reduce((a,b)=>a+b,0)/rets.length;
    const varr = rets.reduce((a,b)=>a+(b-mean)*(b-mean),0)/rets.length;
    const sd = Math.sqrt(varr)||1e-12;
    const bpy = ({'1m':525600,'5m':105120,'15m':35040,'30m':17520,'1h':8760,'4h':2190,'1d':365,'1w':52})[P.granularity]||8760;
    let peak=cn[0], mdd=0;
    for(const x of cn){ if(x>peak) peak=x; mdd=Math.min(mdd, x/peak-1); }
    // trades approx in window: count position flips on primary from live sim trades hard; use pos changes
    return {
      total_return_pct: (cn[cn.length-1]/cn[0]-1)*100,
      benchmark_return_pct: (bn[bn.length-1]/bn[0]-1)*100,
      sharpe: mean/sd*Math.sqrt(bpy),
      max_drawdown_pct: mdd*100,
      trades: null,
      win_rate_pct: null,
      bars: cn.length,
    };
  }

  function countTrades(pos, i0, i1){
    let n=0;
    for(let i=Math.max(i0+1,1);i<i1;i++) if(Math.abs((pos[i]||0)-(pos[i-1]||0))>1e-9) n++;
    return n;
  }

  function rangeIdx(){
    const n=P.ts.length;
    const cut = P.cut_index;
    if(state.view==='train' && cut!=null) return [0, cut];
    if(state.view==='test' && cut!=null) return [cut, n];
    return [0,n];
  }

  function renderMetrics(el, train, test, full, pos){
    function col(title, m, color){
      if(!m) return `<div class="mcol"><div class="tag">${title}</div><div class="mrow"><span class="k">No data</span></div></div>`;
      const rows = [
        ['Total return', fmtPct(m.total_return_pct), clsPct(m.total_return_pct)],
        ['Buy & hold', fmtPct(m.benchmark_return_pct), clsPct(m.benchmark_return_pct)],
        ['Sharpe', fmtNum(m.sharpe,2), ''],
        ['Max drawdown', fmtPct(m.max_drawdown_pct), clsPct(m.max_drawdown_pct)],
        ['Trades', m.trades==null?'—':m.trades, ''],
        ['Win rate', m.win_rate_pct==null?'—':(fmtNum(m.win_rate_pct,1)+'%'), ''],
      ];
      return `<div class="mcol"><div class="tag" style="color:${color}">${title}</div>${
        rows.map(([k,v,c])=>`<div class="mrow"><span class="k">${k}</span><span class="${c}">${v}</span></div>`).join('')
      }</div>`;
    }
    const t = train?Object.assign({},train):null;
    const e = test?Object.assign({},test):null;
    if(t && pos && P.cut_index!=null) t.trades = countTrades(pos,0,P.cut_index);
    if(e && pos && P.cut_index!=null) e.trades = countTrades(pos,P.cut_index,P.ts.length);
    el.innerHTML = col('Train', t, 'var(--train)') + col('Test', e, 'var(--test)');
  }

  function adviceFrom(train, test, full){
    const tips=[];
    if(train&&test){
      if(train.total_return_pct>10 && test.total_return_pct < train.total_return_pct-15)
        tips.push({t:'Train far better than Test — watch overfitting: fewer tweaks or longer OOS.',c:'warn'});
      if(test.total_return_pct < -10)
        tips.push({t:'Large Test loss: check fees, signal frequency, and position caps.',c:'bad'});
      if(train.sharpe>1 && test.sharpe<0.2)
        tips.push({t:'Train Sharpe OK but Test weak — params may only fit one past regime.',c:'warn'});
    }
    const mdd=(test||full).max_drawdown_pct;
    if(mdd < -25) tips.push({t:`Max drawdown about ${mdd.toFixed(1)}% — large: tighten stops or cut size.`,c:'bad'});
    const tr = (test&&test.trades!=null)?test.trades:full.trades;
    if(typeof tr==='number'){
      if(tr<5) tips.push({t:'Too few trades for stats: shorter TF or looser entries.',c:'warn'});
      if(tr>400) tips.push({t:'Trading too often — fees may eat returns.',c:'warn'});
    }
    if((test||full).benchmark_return_pct!=null && (test||full).total_return_pct < (test||full).benchmark_return_pct-5)
      tips.push({t:'Strategy weaker than buy & hold: prove stable alpha before live.',c:'warn'});
    if(!tips.length){
      tips.push({t:'Train/Test gap small and DD controlled: take same params to paper and watch slippage.',c:'good'});
      tips.push({t:'When changing params, compare with Original results on the left — avoid test-only optimization.',c:'good'});
    }
    return tips.slice(0,4);
  }

  function drawCharts(){
    const live = state.live;
    if(!live) return;
    const [i0,i1] = rangeIdx();
    drawPrice(document.getElementById('chartPrice'), i0, i1);
    drawEq(document.getElementById('chartEq'), live.curve, live.bh, i0, i1);
  }

  function setupCanvas(cv){
    const dpr = window.devicePixelRatio||1;
    const w = cv.clientWidth, h = cv.clientHeight||280;
    cv.width = Math.max(1, Math.floor(w*dpr));
    cv.height = Math.max(1, Math.floor(h*dpr));
    const ctx = cv.getContext('2d');
    ctx.setTransform(dpr,0,0,dpr,0,0);
    return {ctx,w,h};
  }

  function drawPrice(cv, i0, i1){
    const {ctx,w,h} = setupCanvas(cv);
    ctx.clearRect(0,0,w,h);
    const pad={l:48,r:12,t:16,b:28};
    const cut=P.cut_index;
    if(cut!=null){
      const x0 = pad.l + (Math.max(cut,i0)-i0)/(i1-i0)*(w-pad.l-pad.r);
      const x1 = pad.l + (i1-i0)/(i1-i0)*(w-pad.l-pad.r);
      if(cut<i1 && cut>=i0){
        ctx.fillStyle='rgba(167,139,250,0.10)';
        ctx.fillRect(x0, pad.t, Math.max(0, pad.l+(w-pad.l-pad.r)-x0+pad.l-pad.l), h-pad.t-pad.b);
        // fix width:
      }
      const xTest0 = pad.l + (Math.max(cut,i0)-i0)/Math.max(1,i1-i0-1e-9)*(w-pad.l-pad.r);
      ctx.fillStyle='rgba(167,139,250,0.12)';
      ctx.fillRect(xTest0, pad.t, w-pad.r-xTest0, h-pad.t-pad.b);
    }
    const c = P.series[P.primary].close.slice(i0,i1);
    const base = c.find(x=>x!=null)||1;
    const ys = c.map(x=>x==null?null:x/base);
    let ymin=Infinity,ymax=-Infinity;
    for(const v of ys){ if(v!=null){ ymin=Math.min(ymin,v); ymax=Math.max(ymax,v);} }
    if(!(ymax>ymin)){ ymin=0.9; ymax=1.1; }
    const plot=(arr,color,lw)=>{
      ctx.beginPath(); ctx.strokeStyle=color; ctx.lineWidth=lw; let started=false;
      for(let i=0;i<arr.length;i++){
        if(arr[i]==null){started=false;continue;}
        const x=pad.l+i/Math.max(1,arr.length-1)*(w-pad.l-pad.r);
        const y=pad.t+(1-(arr[i]-ymin)/(ymax-ymin))*(h-pad.t-pad.b);
        if(!started){ctx.moveTo(x,y);started=true;} else ctx.lineTo(x,y);
      }
      ctx.stroke();
    };
    plot(ys,'#38bdf8',1.5);
    // axes labels
    ctx.fillStyle='#8b9bb8'; ctx.font='11px sans-serif';
    ctx.fillText(ymax.toFixed(2), 6, pad.t+8);
    ctx.fillText(ymin.toFixed(2), 6, h-pad.b);
    if(P.ts[i0]) ctx.fillText(tsLabel(P.ts[i0]), pad.l, h-8);
    if(P.ts[i1-1]) {
      const s=tsLabel(P.ts[i1-1]);
      ctx.fillText(s, w-pad.r-ctx.measureText(s).width, h-8);
    }
  }

  function drawEq(cv, curve, bh, i0, i1){
    const {ctx,w,h}=setupCanvas(cv);
    ctx.clearRect(0,0,w,h);
    const pad={l:48,r:12,t:16,b:28};
    const cut=P.cut_index;
    if(cut!=null && cut<i1 && cut>=i0){
      const xTest0 = pad.l + (Math.max(cut,i0)-i0)/Math.max(1,i1-i0-1e-9)*(w-pad.l-pad.r);
      ctx.fillStyle='rgba(167,139,250,0.12)';
      ctx.fillRect(xTest0, pad.t, w-pad.r-xTest0, h-pad.t-pad.b);
    }
    const c=curve.slice(i0,i1), b=bh.slice(i0,i1);
    let ymin=Infinity,ymax=-Infinity;
    for(const arr of [c,b]) for(const v of arr){ if(v!=null){ymin=Math.min(ymin,v); ymax=Math.max(ymax,v);} }
    if(!(ymax>ymin)){ ymin=P.capital*0.9; ymax=P.capital*1.1; }
    const plot=(arr,color,lw)=>{
      ctx.beginPath(); ctx.strokeStyle=color; ctx.lineWidth=lw; let started=false;
      for(let i=0;i<arr.length;i++){
        const x=pad.l+i/Math.max(1,arr.length-1)*(w-pad.l-pad.r);
        const y=pad.t+(1-(arr[i]-ymin)/(ymax-ymin))*(h-pad.t-pad.b);
        if(!started){ctx.moveTo(x,y);started=true;} else ctx.lineTo(x,y);
      }
      ctx.stroke();
    };
    plot(b,'#64748b',1.2);
    plot(c,'#22c55e',1.6);
    ctx.fillStyle='#8b9bb8'; ctx.font='11px sans-serif';
    ctx.fillText(ymax.toFixed(1), 6, pad.t+8);
    ctx.fillText(ymin.toFixed(1), 6, h-pad.b);
  }

  function renderTable(){
    const live=state.live; if(!live) return;
    const q=(document.getElementById('q').value||'').trim();
    const lastN=Math.max(20, Math.min(2000, parseInt(document.getElementById('lastN').value)||120));
    const cut=P.cut_index==null? Math.floor(P.ts.length*0.7): P.cut_index;
    const i0=cut, i1=P.ts.length;
    const rows=[];
    for(let i=i0;i<i1;i++){
      const t=tsLabel(P.ts[i]);
      if(q && t.indexOf(q)<0) continue;
      rows.push(i);
    }
    const slice=rows.slice(-lastN).reverse();
    const tb=document.getElementById('tbody');
    const s=P.series[P.primary];
    tb.innerHTML = slice.map(i=>{
      const sig=live.tgtPrimary[i]||0;
      const pos=live.pos[i]||0;
      const prev=i>0?(live.tgtPrimary[i-1]||0):sig;
      const chg = Math.abs(sig-prev)>1e-9;
      return `<tr class="${chg?'chg':''}"><td>${tsLabel(P.ts[i])}</td><td>${fmtNum(s.open[i],2)}</td><td>${fmtNum(s.high[i],2)}</td><td>${fmtNum(s.low[i],2)}</td><td>${fmtNum(s.close[i],2)}</td><td>${fmtNum(sig,2)}</td><td>${fmtNum(pos,3)}</td></tr>`;
    }).join('');
  }

  function recalc(){
    if(!P.browser_recalc){
      // still allow viewing original equity
      state.live = {
        curve: P.equity_original.slice(),
        bh: P.benchmark_original.slice(),
        pos: P.signal_original.map(x=>x*P.max_position_pct),
        tgtPrimary: P.signal_original.slice(),
        trades: []
      };
    } else {
      const tgt = signalsFor(state.params);
      state.live = simulate(tgt);
    }
    const live=state.live;
    const cut=P.cut_index;
    const full=metricsOf(live.curve, live.bh, live.trades, 0, P.ts.length);
    const train=cut!=null?metricsOf(live.curve, live.bh, live.trades, 0, cut):null;
    const test=cut!=null?metricsOf(live.curve, live.bh, live.trades, cut, P.ts.length):null;
    if(full){ full.trades = countTrades(live.pos,0,P.ts.length); }
    if(train){ train.trades = countTrades(live.pos,0,cut); }
    if(test){ test.trades = countTrades(live.pos,cut,P.ts.length); }
    renderMetrics(document.getElementById('metricsLive'), train, test, full, live.pos);
    const tips = adviceFrom(train||P.metrics_original.train, test||P.metrics_original.test, full||P.metrics_original.full);
    document.getElementById('advice').innerHTML = tips.map(x=>`<div class="tip ${x.c}">${x.t}</div>`).join('');
    drawCharts();
    renderTable();
  }

  function buildParamsUI(){
    const box=document.getElementById('params');
    if(!P.param_schema.length){
      box.innerHTML='<p class="note">No tunable param schema.</p>';
      return;
    }
    box.innerHTML = P.param_schema.map(p=>{
      const v = state.params[p.key]!==undefined?state.params[p.key]:p.default;
      const isFloat = String(p.step).indexOf('.')>=0;
      return `<div class="param"><label>${p.label}</label>
        <input type="range" data-key="${p.key}" min="${p.min}" max="${p.max}" step="${p.step}" value="${v}"/>
        <input type="number" data-key="${p.key}" min="${p.min}" max="${p.max}" step="${p.step}" value="${v}"/></div>`;
    }).join('');
    box.querySelectorAll('input').forEach(inp=>{
      inp.addEventListener('input', ()=>{
        const k=inp.getAttribute('data-key');
        let v=Number(inp.value);
        state.params[k]=v;
        box.querySelectorAll(`input[data-key="${k}"]`).forEach(x=>{ if(x!==inp) x.value=v; });
        if(document.getElementById('autoRecalc').checked) recalc();
      });
    });
  }

  // header
  document.getElementById('title').textContent = `${P.strategy_title} · ${P.group}`;
  document.getElementById('subtitle').innerHTML =
    `Symbols <b>${P.symbols.join(', ')}</b> · TF <b>${P.granularity}</b> · Market <b>${P.market}</b><br/>`+
    `Embedded range ${P.range.start} → ${P.range.end} (${P.range.bars_embedded} bars`+
    (P.range.bars_full>P.range.bars_embedded?`; full ${P.range.bars_full} bars trimmed`:'')+`) · one-way fee ${(P.fee*100).toFixed(2)}%`;
  document.getElementById('badge').textContent = P.browser_recalc ? 'Browser recalc enabled' : 'Original backtest only';
  document.getElementById('logic').textContent = P.logic;
  document.getElementById('recalcNote').textContent = P.browser_recalc
    ? 'Recalc uses embedded candles: signal delayed 1 bar; fee / position cap / SL-TP match a simplified classroom engine; daily loss limit 5%.'
    : 'Browser recalc is off for this strategy; charts show the original export.';
  document.getElementById('foot').textContent =
    `Generated ${P.generated_at} · MAFS6010G Crypto Finance · Crypto Quant Lab · single-file local open; data is not uploaded`;

  renderMetrics(document.getElementById('metricsOrig'), P.metrics_original.train, P.metrics_original.test, P.metrics_original.full, null);
  // fill original trade counts if present
  buildParamsUI();

  document.getElementById('btnRecalc').onclick = recalc;
  document.getElementById('btnReset').onclick = ()=>{
    state.params = Object.assign({}, P.params);
    buildParamsUI();
    recalc();
  };
  document.getElementById('viewSeg').onclick = (e)=>{
    const b=e.target.closest('button[data-view]'); if(!b) return;
    state.view=b.getAttribute('data-view');
    document.querySelectorAll('#viewSeg button').forEach(x=>x.classList.toggle('active', x===b));
    drawCharts();
  };
  document.getElementById('q').oninput = renderTable;
  document.getElementById('lastN').onchange = renderTable;
  window.addEventListener('resize', drawCharts);

  recalc();
})();
</script>
</body>
</html>
'''

if __name__ == "__main__":
    main()
