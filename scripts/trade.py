"""Risk gate then place: spot orders via bgc CLI (paper by default).
Usage:
  python trade.py signal  --symbol BTCUSDT --strategy ma_cross --params '{"fast":10,"slow":30}'          # current MA signal + suggested size (public data, no Key)
  python trade.py buy     --usdt 10 [--live] [--send]  # default --paper-trading + --dry-run; add --send to actually send
  python trade.py sell    --qty 0.0001 [--live] [--send]
  python trade.py status  [--live]                     # account / open orders
  python trade.py detail --order-id <id> | fills | history | cancel [--order-id <id>]
  python trade.py loop    --interval 3600 [--send]     # simple paper loop; create KILL_SWITCH to stop anytime
Note: spot market buy qty is USDT (quote); sell qty is BTC (base) — from bgc discover."""
import argparse, json, subprocess, time, os, re

def load_env_file(path=os.path.expanduser("~/.bitget/env")):
    """If env vars unset, load ~/.bitget/env (export KEY=VALUE). Never print secrets."""
    if os.environ.get("BITGET_API_KEY") or not os.path.exists(path): return
    for line in open(path):
        m = re.match(r"\s*(?:export\s+)?(BITGET_[A-Z_]+)=(.*)", line.strip())
        if m: os.environ.setdefault(m.group(1), m.group(2).strip().strip('"').strip("'"))
load_env_file()
from risk import RiskManager, RiskConfig
from data import fetch_candles
from strategies import STRATEGIES
import pandas as pd

def latest_signal(a):
    """Latest target position from the same strategy function used in backtest."""
    start = str(pd.Timestamp.utcnow() - pd.Timedelta(days=a.lookback_days))[:10]
    d = fetch_candles(a.symbol, "spot", a.granularity, start, use_cache=False, verbose=False)
    tgt = STRATEGIES[a.strategy]({a.symbol: d}, json.loads(a.params))
    return float(d.close.iloc[-1]), float(tgt[a.symbol].iloc[-1])

def bgc(args, live=False, send=False, confirm=False):
    cmd = ["bgc"] + ([] if live else ["--paper-trading"]) + args
    if not send and args[0] == "order": cmd.append("--dry-run")
    if confirm: cmd.append("--confirm")
    print("$", " ".join(cmd))
    r = subprocess.run(cmd, capture_output=True, text=True)
    print(r.stdout or r.stderr)
    try: return json.loads(r.stdout)
    except Exception: return None

def usdt_equity(live):
    """Available USDT = data.assets.data.assets[coin=USDT].available (structure verified 2026-11-03)."""
    d = bgc(["--read-only", "account_overview"], live=live) if live else bgc(["account_overview"], live=False)
    try:
        for a in d["data"]["assets"]["data"]["assets"]:
            if a.get("coin") == "USDT": return float(a["available"])
    except Exception: pass
    print("⚠️ Could not read USDT available; using configured capital")
    return RiskConfig().capital_usdt

def main():
    p = argparse.ArgumentParser()
    p.add_argument("cmd", choices=["signal", "buy", "sell", "status", "detail", "fills", "history", "cancel", "loop"])
    p.add_argument("--symbol", default="BTCUSDT"); p.add_argument("--usdt", type=float)
    p.add_argument("--qty", type=str); p.add_argument("--live", action="store_true")
    p.add_argument("--send", action="store_true"); p.add_argument("--interval", type=int, default=3600)
    p.add_argument("--strategy", default="ma_cross"); p.add_argument("--params", default="{}")
    p.add_argument("--lookback-days", type=int, default=30); p.add_argument("--order-id")
    p.add_argument("--granularity", default="1h")
    a = p.parse_args(); rm = RiskManager()
    if a.send and a.cmd in ("buy", "sell", "loop"):
        tag = "⚠️ LIVE real order" if a.live else "Paper order"
        if input(f"{tag}! Type YES to confirm send: ") != "YES": print("Cancelled"); return
    if a.cmd == "signal":
        price, sig = latest_signal(a)
        print(json.dumps({"price": price, "target_position": sig,
                          "suggested_size_usdt": round(rm.position_size_usdt(rm.cfg.capital_usdt) * abs(sig), 2)}, ensure_ascii=False))
    elif a.cmd == "buy":
        eq = usdt_equity(a.live); ok, why = rm.check_order(min(eq, rm.cfg.capital_usdt), a.usdt)
        print("Risk:", ok, why)
        if ok: bgc(["order", "--action", "place", "--category", "SPOT", "--symbol", a.symbol,
                    "--side", "buy", "--orderType", "market", "--qty", str(a.usdt)], a.live, a.send)
    elif a.cmd == "sell":
        if rm.kill_switch_on(): print("KILL_SWITCH is on, but flat/sell is still allowed")
        bgc(["order", "--action", "place", "--category", "SPOT", "--symbol", a.symbol,
             "--side", "sell", "--orderType", "market", "--qty", a.qty], a.live, a.send)
    elif a.cmd == "status":
        print("USDT available:", usdt_equity(a.live))
        bgc(["order", "--action", "open", "--category", "SPOT"], a.live, send=True)
    elif a.cmd == "detail":   # orderStatus / cumExecQty / avgPrice / fee
        bgc(["order", "--action", "detail", "--category", "SPOT", "--orderId", a.order_id], a.live, send=True)
    elif a.cmd == "fills":
        bgc(["order", "--action", "fills", "--category", "SPOT"] + (["--orderId", a.order_id] if a.order_id else []), a.live, send=True)
    elif a.cmd == "history":
        bgc(["order", "--action", "history", "--category", "SPOT", "--symbol", a.symbol], a.live, send=True)
    elif a.cmd == "cancel":
        if a.order_id: bgc(["order", "--action", "cancel", "--category", "SPOT", "--orderId", a.order_id], a.live, send=True)
        else: bgc(["order", "--action", "cancelAll", "--category", "SPOT", "--symbol", a.symbol], a.live, send=True, confirm=True)
    elif a.cmd == "loop":
        holding = False
        while not rm.kill_switch_on():
            price, sig = latest_signal(a)
            print(time.strftime("%H:%M:%S"), "price", price, "target", sig, "holding", holding)
            if sig > 0 and not holding:
                n = round(rm.position_size_usdt(rm.cfg.capital_usdt) * sig, 2)
                ok, why = rm.check_order(rm.cfg.capital_usdt, n); print("Risk:", ok, why)
                if ok: bgc(["order", "--action", "place", "--category", "SPOT", "--symbol", a.symbol,
                            "--side", "buy", "--orderType", "market", "--qty", str(n)], a.live, a.send); holding = True
            elif sig <= 0 and holding:
                print("Signal went flat: check fills for size, then sell --qty <size> (auto-flat not implemented yet)"); holding = False
            time.sleep(a.interval)
        print("KILL_SWITCH triggered; loop exiting")

if __name__ == "__main__": main()
