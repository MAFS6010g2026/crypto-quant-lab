---
name: crypto-quant-lab-hl
description: Use when students work on the MAFS6010G Crypto Finance quant lab Option B (Hyperliquid TESTNET) — opencode, agent wallets, risk, backtests on public HL candles, testnet paper trading with mock USDC, result reports.
license: MIT
compatibility: opencode
---

# MAFS6010G Crypto Finance · Option B (Hyperliquid testnet)

Guide students in **English**, one step at a time. This skill is the **Hyperliquid TESTNET** path (no KYC, mock USDC). The Bitget/CEX path lives on branch `main` — do not mix them.

## Operating rules
1. **One step at a time.** Explain → command → student pastes output → ✅ before next step.
2. **Never ask for seed phrases or master private keys.** Only the **API/agent** key goes into `~/.hyperliquid/env` via `setup_keys.py` in the student's own terminal. If a secret is pasted in chat, tell them to revoke that agent and create a new one.
3. Default network is **testnet**. `trade.py` defaults to **dry-run**; `--send` still requires typing `YES`. Mainnet only with `--mainnet` + typed `YES`, and only if the course allows it.
4. Hard caps: per-order notional (default 25 USDC), `KILL_SWITCH` file freezes sends.
5. Ready-made code is in `scripts/`. Copy into `~/lab-hl/` before editing.

## Session structure
- **One Hyperliquid wallet per group** (Group Leader or designee). Other members share that laptop or use read-only public data.
- **Part A (before class):** opencode + DeepSeek; install this skill from branch `hyperliquid`; create wallet; submit address; after TA funds (~150 mock USDC) create API/agent wallet; `setup_keys.py`; Stages 0–2.
- **Part B (~40 min in class):** checks → risk → idea→backtest → testnet trades → report.

## Stage 0 · Environment
```bash
python3 --version   # >= 3.9
opencode --version
node -v             # >= 20 if using opencode via npm
```
Python deps: `pip install hyperliquid-python-sdk eth-account numpy pandas matplotlib`  
Public candle check:
```bash
cd ~/lab-hl && source .venv/bin/activate
python scripts/data.py candles ETH --granularity 1h --start 2026-09-01
```
✅ Rows print; no keys needed.

## Stage 1 · Install skill
Prefer the README install prompt in opencode. Manual:
```bash
git clone -b hyperliquid https://github.com/MAFS6010g2026/crypto-quant-lab.git ~/.claude/skills/crypto-quant-lab-hl
mkdir -p ~/lab-hl && cp -R ~/.claude/skills/crypto-quant-lab-hl/{scripts,templates} ~/lab-hl/
```
Restart opencode; skill name `crypto-quant-lab-hl` should appear.

## Stage 2 · Keys (agent wallet)
Student runs locally: `python scripts/setup_keys.py`  
Writes `~/.hyperliquid/env` (mode 600):
- `HL_ACCOUNT_ADDRESS` = master address (holds funds)
- `HL_AGENT_KEY` = agent private key (trade only, **cannot withdraw**)
- `HL_NETWORK=testnet`

How to create the agent (UI labels may change): open https://app.hyperliquid-testnet.xyz → connect wallet → API / agent wallet page → create named agent (e.g. `lab-bot`) → copy agent key once.

Verify: `source ~/.hyperliquid/env && python scripts/trade.py balance`  
✅ `accountValue` ≈ 150 (after TA funding).

## Stage 3 · Risk
Walk through `risk.py` / `RiskConfig`: capital, max position %, daily loss, kill switch. Show three rejection cases conceptually (oversize, daily loss, KILL_SWITCH).

## Stage 4 · Idea → backtest
Data comes from **Hyperliquid mainnet public candles** (realistic prices; ≤5000 bars per interval). Example RSI:
```bash
python scripts/backtest.py --symbols ETH --granularity 1h --start 2026-04-01 \
  --strategy rsi --params '{"n":14,"lo":30,"hi":70}' \
  --fee 0.00035 --split 0.7 --html report.html --out equity.png --group "Group N"
```
Fee default ~HL taker 0.035%. Open `report.html` in a browser.  
✅ Train/test metrics + HTML saved.

## Stage 5 · Testnet trades
```bash
source ~/.hyperliquid/env
python scripts/trade.py balance
python scripts/trade.py limit --coin ETH --side buy --size 0.01 --price 1000          # dry-run
python scripts/trade.py limit --coin ETH --side buy --size 0.01 --price 1000 --send  # type YES
python scripts/trade.py orders
python scripts/trade.py cancel --coin ETH --oid <OID> --send
python scripts/trade.py market --coin ETH --side buy --notional 15 --send
python scripts/trade.py positions
python scripts/trade.py close --coin ETH --send
python scripts/trade.py fills
```
✅ Order ids, cancel success, fill records. Stay on testnet.

## Stage 6 · Optional mainnet (course approval only)
Not part of the default lab. Requires real USDC, `--mainnet`, and typed YES. Prefer agent keys. Skip unless instructor approves.

## Stage 7 · Report
Collect: backtest JSON/PNG/HTML, testnet order/fill snippets, short write-up from `templates/report_template.md`. Flatten positions and cancel opens before leaving.

## Troubleshooting
| Symptom | Likely fix |
|---|---|
| `Missing HL_ACCOUNT_ADDRESS` | Run `setup_keys.py`; `source ~/.hyperliquid/env` |
| `User or API Wallet … does not exist` | Wait for TA `usd_transfer`; confirm testnet URL |
| `Usd transfer is smaller than fee` | TA must send ≥2 USDC (fee ≈1) |
| Candle history short | HL cap ~5000 bars; use 4h/1d for longer windows |
| Agent cannot trade | Re-approve agent on testnet UI; check `extraAgents` |
| Want to freeze | `python scripts/trade.py kill` or `touch KILL_SWITCH` |

## Contacts
Henry (tamafs6010g@ust.hk) · WeiTao (mafsta3@ust.hk)
