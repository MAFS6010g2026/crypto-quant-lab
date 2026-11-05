# MAFS6010G Crypto Quant Lab — Option B (Hyperliquid testnet)

English-only course skill for **MAFS6010G Crypto Finance**.  
This branch (`hyperliquid`) uses **Hyperliquid TESTNET**: no KYC for students, mock USDC, API/agent wallets.

> Bitget / CEX path remains on branch `main`. Do not mix the two.

**Repo:** https://github.com/MAFS6010g2026/crypto-quant-lab/tree/hyperliquid

## Install with opencode (recommended)

After `opencode` works with DeepSeek, paste this whole prompt:

```
You are installing the MAFS6010G Crypto Quant Lab skill (Option B / Hyperliquid testnet).

Do the following, then print a checklist table (OK / FAIL):
1) Ensure git and python3 (>=3.9) exist.
2) Clone or update the skill on the hyperliquid branch:
   mkdir -p ~/.claude/skills
   if [ -d ~/.claude/skills/crypto-quant-lab-hl/.git ]; then
     git -C ~/.claude/skills/crypto-quant-lab-hl fetch origin && git -C ~/.claude/skills/crypto-quant-lab-hl checkout hyperliquid && git -C ~/.claude/skills/crypto-quant-lab-hl pull
   else
     git clone -b hyperliquid https://github.com/MAFS6010g2026/crypto-quant-lab.git ~/.claude/skills/crypto-quant-lab-hl
   fi
3) mkdir -p ~/lab-hl && cp -R ~/.claude/skills/crypto-quant-lab-hl/{scripts,templates} ~/lab-hl/
4) python3 -m venv ~/lab-hl/.venv && source ~/lab-hl/.venv/bin/activate
   pip install -U pip
   pip install hyperliquid-python-sdk eth-account numpy pandas matplotlib
5) Quick checks (public data only — no keys):
   cd ~/lab-hl && source .venv/bin/activate
   python scripts/data.py candles ETH --granularity 1h --start 2026-09-01 | tail -5
6) NEVER ask for seed phrases, master private keys, or agent keys. Tell the student to run
   `python scripts/setup_keys.py` themselves in their own terminal after the TAs fund the group.

Print versions and pass/fail for each step. Stop after the checklist.
```

Manual fallback:

```bash
git clone -b hyperliquid https://github.com/MAFS6010g2026/crypto-quant-lab.git ~/.claude/skills/crypto-quant-lab-hl
mkdir -p ~/lab-hl && cp -R ~/.claude/skills/crypto-quant-lab-hl/{scripts,templates} ~/lab-hl/
cd ~/lab-hl && python3 -m venv .venv && source .venv/bin/activate
pip install hyperliquid-python-sdk eth-account numpy pandas matplotlib
```

## Safety

- **Never** give your seed phrase or master private key to an AI / chat / email.
- Store only the **API/agent** key in `~/.hyperliquid/env` (mode 600). Agents can trade, **cannot withdraw**.
- Default network is **testnet**. Mainnet needs `--mainnet` and typed `YES`.
- `trade.py` defaults to dry-run; `--send` still requires typing `YES`.
- Per-order notional hard cap (default 25 USDC). Create `KILL_SWITCH` to freeze sends.

## Scripts

| Script | Role |
|---|---|
| `setup_keys.py` | Save master address + agent key |
| `data.py` | Mainnet public candles / funding (≤5000 bars) |
| `strategies.py` | Strategy templates |
| `risk.py` | Risk config |
| `backtest.py` | Backtest + equity PNG + HTML report |
| `report_html.py` | Single-file result page |
| `trade.py` | Testnet orders via agent wallet |

## Contacts

- Henry: tamafs6010g@ust.hk
- WeiTao: mafsta3@ust.hk
