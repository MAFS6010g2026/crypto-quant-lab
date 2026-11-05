"""Strategy templates: students only need to write functions here.
Interface: def my_strategy(data: dict[str, DataFrame], params: dict) -> DataFrame
  - data[symbol] is a candle DataFrame (index=UTC time, cols open/high/low/close/volume/quote_volume;
    in futures mode an extra funding column = funding settled in that bar, else 0)
  - Return a target-position wide table: same index as candles, columns=symbol, values -1..1
    (1=full long, -1=full short, 0=flat)
  - Row t takes effect on bar t+1 (engine auto-shifts; no look-ahead)
  - Actual equity fraction = position × risk.max_position_pct, also capped by leverage, SL/TP, daily loss (see risk.py)
Register in STRATEGIES, then call with --strategy <name>.
STRATEGY_META feeds the result page: logic text + tunable param schema (browser local recalc)."""
import pandas as pd, numpy as np

def ma_cross(data, p):
    f, s = p.get("fast", 10), p.get("slow", 30)
    return pd.DataFrame({k: (d.close.rolling(f).mean() > d.close.rolling(s).mean()).astype(float) for k, d in data.items()})

def rsi_reversion(data, p):
    n, lo, hi = p.get("n", 14), p.get("lo", 30), p.get("hi", 70)
    out = {}
    for k, d in data.items():
        diff = d.close.diff(); up = diff.clip(lower=0).rolling(n).mean(); dn = (-diff.clip(upper=0)).rolling(n).mean()
        rsi = 100 - 100 / (1 + up / dn.replace(0, np.nan))
        pos = pd.Series(np.nan, index=d.index); pos[rsi < lo] = 1; pos[rsi > hi] = 0
        out[k] = pos.ffill().fillna(0)
    return pd.DataFrame(out)

def momentum_rotation(data, p):
    """Multi-asset: each bar hold the top symbols by lookback return (equal weight)."""
    lb, top = p.get("lookback", 24 * 7), p.get("top", 1)
    close = pd.DataFrame({k: d.close for k, d in data.items()})
    rank = close.pct_change(lb).rank(axis=1, ascending=False)
    return (rank <= top).astype(float) / top

def funding_contrarian(data, p):
    """Futures example: when recent funding mean is positive (long crowded) go short; if negative go long."""
    out = {}
    for k, d in data.items():
        fr = d["funding"].replace(0, np.nan).ffill().rolling(p.get("n", 3) * 1).mean().fillna(0)
        out[k] = np.sign(-fr) * (fr.abs() > p.get("th", 0.0001))
    return pd.DataFrame(out)

STRATEGIES = {"ma_cross": ma_cross, "rsi": rsi_reversion, "momentum": momentum_rotation, "funding": funding_contrarian}

# Result page: one-line logic + tunable params (min/max/step/default). browser_recalc=True => HTML can recalc live.
STRATEGY_META = {
    "ma_cross": {
        "title": "MA crossover",
        "logic": "Go long when the fast MA is above the slow MA; otherwise flat. Signal takes effect on the next bar to avoid look-ahead.",
        "browser_recalc": True,
        "params": [
            {"key": "fast", "label": "Fast MA period", "min": 2, "max": 60, "step": 1, "default": 10},
            {"key": "slow", "label": "Slow MA period", "min": 5, "max": 200, "step": 1, "default": 30},
        ],
    },
    "rsi": {
        "title": "RSI mean reversion",
        "logic": "Buy and hold when RSI crosses below the oversold line; flatten when RSI crosses above the overbought line. Position adjusts on the next bar after the signal changes.",
        "browser_recalc": True,
        "params": [
            {"key": "n", "label": "RSI period", "min": 5, "max": 40, "step": 1, "default": 14},
            {"key": "lo", "label": "Oversold", "min": 5, "max": 45, "step": 1, "default": 30},
            {"key": "hi", "label": "Overbought", "min": 55, "max": 95, "step": 1, "default": 70},
        ],
    },
    "momentum": {
        "title": "Momentum rotation",
        "logic": "Among several symbols, each bar hold the top names by lookback return (equal weight). Good for multi-coin comparison.",
        "browser_recalc": True,
        "params": [
            {"key": "lookback", "label": "Lookback", "min": 6, "max": 500, "step": 1, "default": 168},
            {"key": "top", "label": "Hold count", "min": 1, "max": 5, "step": 1, "default": 1},
        ],
    },
    "funding": {
        "title": "Funding contrarian",
        "logic": "When the mean of the last n funding rates is too high (long crowded) go short; when too low go long. Futures only; needs embedded funding series.",
        "browser_recalc": True,
        "params": [
            {"key": "n", "label": "Funding mean window", "min": 1, "max": 12, "step": 1, "default": 3},
            {"key": "th", "label": "Trigger threshold", "min": 0.00001, "max": 0.002, "step": 0.00001, "default": 0.0001},
        ],
    },
}
