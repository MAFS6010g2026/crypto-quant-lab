"""Hyperliquid testnet trading via API/agent wallet (risk-gated).

Env file ~/.hyperliquid/env (mode 600), loaded automatically:
  HL_ACCOUNT_ADDRESS=0x...   # master wallet (holds funds)
  HL_AGENT_KEY=0x...         # API/agent private key (can trade, cannot withdraw)
  HL_NETWORK=testnet         # default; mainnet only with --mainnet + YES

Commands:
  python trade.py balance
  python trade.py positions
  python trade.py orders
  python trade.py limit  --coin ETH --side buy --size 0.01 --price 1000
  python trade.py limit  ... --send          # still asks typed YES
  python trade.py market --coin ETH --side buy --notional 15 --send
  python trade.py close  --coin ETH --send
  python trade.py cancel --coin ETH --oid 123 --send
  python trade.py fills
  python trade.py kill                       # create KILL_SWITCH file
"""
from __future__ import annotations
import argparse, json, os, re, sys, time
from eth_account import Account
from hyperliquid.exchange import Exchange
from hyperliquid.info import Info
from hyperliquid.utils import constants

ENV_PATH = os.path.expanduser("~/.hyperliquid/env")
KILL = "KILL_SWITCH"
DEFAULT_MAX_NOTIONAL = float(os.environ.get("HL_MAX_NOTIONAL", "25"))  # USDC per order hard cap

def load_env(path=ENV_PATH):
    if not os.path.exists(path):
        return
    for line in open(path):
        m = re.match(r"\s*(?:export\s+)?(HL_[A-Z0-9_]+)=(.*)", line.strip())
        if m:
            os.environ.setdefault(m.group(1), m.group(2).strip().strip('"').strip("'"))

load_env()

def _confirm_send(label: str):
    print(f"About to SEND: {label}")
    ans = input("Type YES to confirm: ").strip()
    if ans != "YES":
        print("Aborted (need exactly YES).")
        sys.exit(1)

def _clients(mainnet: bool):
    addr = os.environ.get("HL_ACCOUNT_ADDRESS", "").strip()
    key = os.environ.get("HL_AGENT_KEY", "").strip()
    if not addr or not key:
        raise SystemExit(f"Missing HL_ACCOUNT_ADDRESS / HL_AGENT_KEY. Run setup_keys.py or create {ENV_PATH}")
    if not key.startswith("0x"):
        key = "0x" + key
    base = constants.MAINNET_API_URL if mainnet else constants.TESTNET_API_URL
    if mainnet and os.environ.get("HL_NETWORK", "testnet").lower() != "mainnet":
        # still allow --mainnet flag, but require double confirmation later
        pass
    wallet = Account.from_key(key)
    info = Info(base, skip_ws=True)
    # Agent signs; HL maps agent → master. Pass account_address=master for clarity on info queries.
    ex = Exchange(wallet, base, account_address=addr)
    return info, ex, addr, base

def cmd_balance(info, addr):
    st = info.user_state(addr)
    ms = st.get("marginSummary") or {}
    print(json.dumps({
        "account": addr,
        "accountValue": ms.get("accountValue"),
        "totalMarginUsed": ms.get("totalMarginUsed"),
        "withdrawable": st.get("withdrawable"),
        "network_hint": "testnet" if "testnet" in str(info.base_url) else "mainnet",
    }, indent=2))

def cmd_positions(info, addr):
    st = info.user_state(addr)
    rows = []
    for p in st.get("assetPositions") or []:
        pos = p.get("position") or {}
        if float(pos.get("szi") or 0) == 0:
            continue
        rows.append({k: pos.get(k) for k in ("coin", "szi", "entryPx", "positionValue", "unrealizedPnl", "leverage")})
    print(json.dumps(rows, indent=2))

def cmd_orders(info, addr):
    print(json.dumps(info.open_orders(addr), indent=2))

def cmd_fills(info, addr, n=20):
    fills = info.user_fills(addr)[:n]
    print(json.dumps(fills, indent=2))

def mid(info, coin):
    return float(info.all_mids()[coin])

def size_from_notional(info, coin, notional):
    m = mid(info, coin)
    # szDecimals from meta
    meta = info.meta()
    dec = 4
    for u in meta.get("universe", []):
        if u.get("name") == coin:
            dec = int(u.get("szDecimals", 4)); break
    sz = round(notional / m, dec)
    return sz, m

def place_limit(ex, info, coin, is_buy, size, price, send, mainnet, max_notional):
    notional = abs(size) * float(price)
    if notional > max_notional:
        raise SystemExit(f"Rejected: notional {notional:.2f} > hard cap {max_notional} USDC")
    if os.path.exists(KILL):
        raise SystemExit("KILL_SWITCH present — refuse to trade. Delete the file to resume.")
    label = f"{'BUY' if is_buy else 'SELL'} {size} {coin} @ {price} (notional≈{notional:.2f})"
    if mainnet:
        print("⚠️ MAINNET mode")
        _confirm_send("MAINNET " + label)
    action = {"limit": {"tif": "Gtc"}}
    if not send:
        print("[dry-run]", label)
        print(json.dumps({"coin": coin, "is_buy": is_buy, "sz": size, "limitPx": price, "order_type": action}, indent=2))
        return
    _confirm_send(label)
    resp = ex.order(coin, is_buy, size, price, action)
    print(json.dumps(resp, indent=2))

def place_market(ex, info, coin, is_buy, notional, send, mainnet, max_notional):
    if notional > max_notional:
        raise SystemExit(f"Rejected: notional {notional:.2f} > hard cap {max_notional} USDC")
    if os.path.exists(KILL):
        raise SystemExit("KILL_SWITCH present — refuse to trade.")
    sz, m = size_from_notional(info, coin, notional)
    if sz * m < 10:
        raise SystemExit(f"Notional too small ({sz*m:.2f}); HL min ~$10")
    label = f"MARKET {'BUY' if is_buy else 'SELL'} {sz} {coin} (~{notional} USDC, mid={m})"
    if mainnet:
        print("⚠️ MAINNET mode")
        _confirm_send("MAINNET " + label)
    if not send:
        print("[dry-run]", label)
        return
    _confirm_send(label)
    resp = ex.market_open(coin, is_buy, sz, None, 0.01)
    print(json.dumps(resp, indent=2))

def close_pos(ex, info, addr, coin, send, mainnet):
    if os.path.exists(KILL):
        raise SystemExit("KILL_SWITCH present — refuse to trade.")
    label = f"MARKET CLOSE {coin}"
    if mainnet:
        _confirm_send("MAINNET " + label)
    if not send:
        print("[dry-run]", label)
        cmd_positions(info, addr)
        return
    _confirm_send(label)
    print(json.dumps(ex.market_close(coin), indent=2))

def cancel(ex, coin, oid, send, mainnet):
    label = f"CANCEL {coin} oid={oid}"
    if mainnet:
        _confirm_send("MAINNET " + label)
    if not send:
        print("[dry-run]", label)
        return
    _confirm_send(label)
    print(json.dumps(ex.cancel(coin, int(oid)), indent=2))

def main():
    p = argparse.ArgumentParser(description="Hyperliquid testnet trading (agent wallet)")
    p.add_argument("cmd", choices=["balance", "positions", "orders", "limit", "market", "close", "cancel", "fills", "kill", "signal"])
    p.add_argument("--coin", default="ETH")
    p.add_argument("--side", choices=["buy", "sell"], default="buy")
    p.add_argument("--size", type=float)
    p.add_argument("--price", type=float)
    p.add_argument("--notional", type=float, default=15.0)
    p.add_argument("--oid", type=int)
    p.add_argument("--send", action="store_true", help="actually send (still requires typing YES)")
    p.add_argument("--mainnet", action="store_true", help="use mainnet (DANGEROUS; needs YES)")
    p.add_argument("--max-notional", type=float, default=DEFAULT_MAX_NOTIONAL)
    p.add_argument("--strategy", default="rsi")
    p.add_argument("--params", default='{"n":14,"lo":30,"hi":70}')
    p.add_argument("--granularity", default="1h")
    a = p.parse_args()

    if a.cmd == "kill":
        open(KILL, "w").write("1\n")
        print(f"Created ./{KILL} — all send commands will refuse until you delete it.")
        return

    # signal uses public data only
    if a.cmd == "signal":
        from data import fetch_candles
        from strategies import STRATEGIES
        import pandas as pd
        start = str(pd.Timestamp.utcnow() - pd.Timedelta(days=40))[:10]
        d = fetch_candles(a.coin, "futures", a.granularity, start, use_cache=True, verbose=False)
        tgt = STRATEGIES[a.strategy]({a.coin: d}, json.loads(a.params))
        print(json.dumps({"coin": a.coin, "last": float(d.close.iloc[-1]),
                          "target": float(tgt[a.coin].iloc[-1])}, indent=2))
        return

    info, ex, addr, base = _clients(a.mainnet)
    if a.mainnet:
        print("Using MAINNET", base)
    else:
        print("Using TESTNET", base)

    if a.cmd == "balance": cmd_balance(info, addr)
    elif a.cmd == "positions": cmd_positions(info, addr)
    elif a.cmd == "orders": cmd_orders(info, addr)
    elif a.cmd == "fills": cmd_fills(info, addr)
    elif a.cmd == "limit":
        if a.size is None or a.price is None:
            raise SystemExit("--size and --price required for limit")
        place_limit(ex, info, a.coin.upper(), a.side == "buy", a.size, a.price, a.send, a.mainnet, a.max_notional)
    elif a.cmd == "market":
        place_market(ex, info, a.coin.upper(), a.side == "buy", a.notional, a.send, a.mainnet, a.max_notional)
    elif a.cmd == "close":
        close_pos(ex, info, addr, a.coin.upper(), a.send, a.mainnet)
    elif a.cmd == "cancel":
        if a.oid is None:
            raise SystemExit("--oid required")
        cancel(ex, a.coin.upper(), a.oid, a.send, a.mainnet)

if __name__ == "__main__":
    main()
