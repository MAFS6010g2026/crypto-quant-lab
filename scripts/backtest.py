"""Generic backtest engine: multi-symbol, spot/futures (optional funding), fees, risk, train/test split, equity PNG, optional HTML report.
Examples:
  python backtest.py --symbols ETH --granularity 1h --start 2026-04-01 --strategy rsi --params '{"n":14,"lo":30,"hi":70}' --split 0.7 --html report.html
  python backtest.py --symbols BTC,ETH --granularity 4h --start 2025-11-01 --strategy ma_cross --params '{"fast":10,"slow":30}'
  python backtest.py --symbols ETH --funding --strategy funding --split 0.7
Data: Hyperliquid mainnet public candles via data.py (≤5000 bars/interval)."""
import argparse, json, math
import numpy as np, pandas as pd
from data import fetch_candles, funding_history
from risk import RiskConfig, RiskManager
from strategies import STRATEGIES

BARS_PER_YEAR = {"1m": 525600, "5m": 105120, "15m": 35040, "30m": 17520, "1h": 8760, "4h": 2190, "1d": 365, "1w": 52}

def load(symbols, market, gran, start, end, with_funding):
    data = {}
    for s in symbols:
        d = fetch_candles(s, market, gran, start, end)
        if market == "futures":
            d["funding"] = 0.0
            if with_funding:
                fr = funding_history(s)
                idx = d.index.searchsorted(fr.index, side="right") - 1   # attribute funding to the bar that contains settlement
                for i, v in zip(idx, fr.values):
                    if 0 <= i < len(d): d.iloc[i, d.columns.get_loc("funding")] += v
                if fr.index.min() > d.index.min():
                    print(f"⚠️ {s} funding history only starts at {fr.index.min()} (exchange public API ~90 days); earlier bars use 0 funding")
        data[s] = d
    idx = sorted(set().union(*[d.index for d in data.values()]))
    return {s: d.reindex(idx).ffill() for s, d in data.items()}   # align timeline; forward-fill missing bars

def simulate(data, target, cfg, fee, use_funding):
    rm = RiskManager(cfg)
    close = pd.DataFrame({k: d.close for k, d in data.items()})
    fund = pd.DataFrame({k: d.get("funding", pd.Series(0.0, index=d.index)) for k, d in data.items()}).fillna(0)
    tgt = target.reindex(close.index).fillna(0).clip(-1, 1).shift(1).fillna(0) * cfg.max_position_pct  # effective at t+1
    gross = tgt.abs().sum(axis=1); scale = (cfg.max_leverage / gross).clip(upper=1).fillna(1)
    tgt = tgt.mul(scale, axis=0)
    syms = list(close.columns); w = np.zeros(len(syms)); entry = np.full(len(syms), np.nan); blocked = np.zeros(len(syms), bool)
    eq, curve, trades, ts = cfg.capital_usdt, [], [], close.index
    px, T, F = close.values, tgt.values, fund.values
    for t in range(len(ts)):
        if t > 0:
            r = px[t] / px[t - 1] - 1
            eq *= 1 + np.nansum(w * r) - (np.nansum(w * F[t]) if use_funding else 0)
        rm.new_bar(int(ts[t].timestamp() * 1000), eq)
        want = T[t].copy()
        for j in range(len(syms)):
            if w[j] != 0 and not np.isnan(entry[j]):
                ex = rm.exit_signal(entry[j], px[t, j], "long" if w[j] > 0 else "short")
                if ex: want[j] = 0; blocked[j] = True     # after SL/TP, no re-entry until signal returns to 0
            if T[t, j] == 0: blocked[j] = False
            if blocked[j]: want[j] = 0
        if rm.daily_loss_hit(eq) or rm.kill_switch_on(): want[:] = 0
        turn = np.abs(want - w)
        if turn.sum() > 1e-9:
            eq *= 1 - fee * turn.sum()
            for j in range(len(syms)):
                if w[j] != 0 and (want[j] == 0 or np.sign(want[j]) != np.sign(w[j])):
                    trades.append(((px[t, j] / entry[j] - 1) * np.sign(w[j])) - 2 * fee)
                if want[j] != 0 and (w[j] == 0 or np.sign(want[j]) != np.sign(w[j])): entry[j] = px[t, j]
                if want[j] == 0: entry[j] = np.nan
            w = want
        curve.append(eq)
    return pd.Series(curve, index=ts), trades

def metrics(curve, trades, bpy, bench):
    r = curve.pct_change().dropna(); sd = r.std() or 1e-12
    return {"start": str(curve.index[0])[:16], "end": str(curve.index[-1])[:16], "bars": len(curve),
            "total_return_pct": round((curve.iloc[-1] / curve.iloc[0] - 1) * 100, 2),
            "benchmark_return_pct": round((bench.iloc[-1] / bench.iloc[0] - 1) * 100, 2),
            "annual_vol_pct": round(sd * math.sqrt(bpy) * 100, 2),
            "sharpe": round(r.mean() / sd * math.sqrt(bpy), 2),
            "max_drawdown_pct": round((curve / curve.cummax() - 1).min() * 100, 2),
            "trades": len(trades), "win_rate_pct": round(100 * np.mean([t > 0 for t in trades]), 1) if trades else None}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbols", default="ETH"); ap.add_argument("--market", default="futures", choices=["spot", "futures"])
    ap.add_argument("--granularity", default="1h"); ap.add_argument("--start", default=None); ap.add_argument("--end")
    ap.add_argument("--strategy", default="ma_cross"); ap.add_argument("--params", default="{}")
    ap.add_argument("--fee", type=float, default=0.00035, help="one-way fee; HL base taker ~0.035%% (override as needed)")
    ap.add_argument("--funding", action="store_true", help="include funding for futures")
    ap.add_argument("--split", type=float, default=None, help="train fraction, e.g. 0.7")
    ap.add_argument("--capital", type=float, default=100.0); ap.add_argument("--out", default="equity.png")
    ap.add_argument("--html", default=None, help="path for single-file HTML result page, e.g. report.html")
    ap.add_argument("--group", default="Demo", help="group name on the result page")
    ap.add_argument("--max-bars", type=int, default=5000, help="max candles embedded in HTML")
    a = ap.parse_args()
    if a.start is None: a.start = str(pd.Timestamp.utcnow().normalize() - pd.Timedelta(days=365))[:10]
    syms = a.symbols.split(","); gran = a.granularity.replace("min", "m").replace("day", "d").replace("H", "h")
    data = load(syms, a.market, gran, a.start, a.end, a.funding)
    target = STRATEGIES[a.strategy](data, json.loads(a.params))
    cfg = RiskConfig(capital_usdt=a.capital)
    curve, trades = simulate(data, target, cfg, a.fee, a.funding)
    close = pd.DataFrame({k: d.close for k, d in data.items()})
    bench = a.capital * (close / close.iloc[0]).mean(axis=1)  # equal-weight buy & hold
    bpy = BARS_PER_YEAR.get(gran, 8760)
    res = {"strategy": a.strategy, "params": json.loads(a.params), "symbols": syms, "market": a.market,
           "granularity": gran, "fee": a.fee, "funding": a.funding, "full": metrics(curve, trades, bpy, bench)}
    cut = None
    if a.split:
        cut = curve.index[int(len(curve) * a.split)]
        for name, sl in [("train", slice(None, cut)), ("test", slice(cut, None))]:
            c = curve[sl]; res[name] = metrics(c / c.iloc[0] * a.capital, [], bpy, bench[sl] / bench[sl].iloc[0] * a.capital)
            res[name]["trades"] = res[name]["win_rate_pct"] = None
    print(json.dumps(res, ensure_ascii=False, indent=2))
    json.dump(res, open(a.out.rsplit(".", 1)[0] + ".json", "w"), ensure_ascii=False, indent=2)
    try:
        import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
        fig, ax = plt.subplots(3, 1, figsize=(11, 8), sharex=True, gridspec_kw={"height_ratios": [2, 2, 1]})
        for s in syms: ax[0].plot(close.index, close[s] / close[s].iloc[0], lw=.8, label=s)
        ax[0].set_title("normalized price"); ax[0].legend(fontsize=8)
        m = res["full"]; ax[1].plot(curve.index, curve, lw=1, label="strategy"); ax[1].plot(bench.index, bench, lw=.8, alpha=.6, label="buy & hold (EW)")
        if a.split: ax[1].axvline(cut, color="r", ls="--", lw=.8, label="train | test")
        ax[1].set_title(f"{a.strategy} {a.market} {gran}  ret {m['total_return_pct']}%  sharpe {m['sharpe']}  mdd {m['max_drawdown_pct']}%"); ax[1].legend(fontsize=8)
        dd = curve / curve.cummax() - 1; ax[2].fill_between(dd.index, dd * 100, 0, color="tab:red", alpha=.4); ax[2].set_title("drawdown %")
        fig.tight_layout(); fig.savefig(a.out, dpi=110); print("chart saved:", a.out)
    except ImportError:
        print("⚠️ matplotlib not installed; skipped PNG. pip install matplotlib or use --html only")

    if a.html:
        from report_html import build_payload, write_html
        payload = build_payload(
            data, target, cfg, a.fee, a.funding, a.strategy, json.loads(a.params),
            syms, a.market, gran, a.split, group=a.group, max_bars=a.max_bars,
        )
        write_html(payload, a.html)
        print("html saved:", a.html)

if __name__ == "__main__": main()
