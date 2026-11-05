# crypto-quant-lab — MAFS6010G Crypto Finance Quant Lab

An [opencode](https://opencode.ai) skill that acts as your lab TA for the **MAFS6010G Crypto Finance** Quant Lab. It guides each group step by step through:

**idea → strategy → risk controls → backtest → paper trading → small live trade (group budget) → result report**

The lab trades through the Bitget exchange API (via the `bgc` CLI). Use a DeepSeek model in opencode.

## Quick install

```bash
# 1. Install the skill (opencode reads ~/.claude/skills/<name>/SKILL.md)
git clone https://github.com/MAFS6010g2026/crypto-quant-lab.git ~/.claude/skills/crypto-quant-lab
# update later
cd ~/.claude/skills/crypto-quant-lab && git pull

# 2. Lab working folder + Python deps (Python >= 3.9)
mkdir -p ~/lab && cp -R ~/.claude/skills/crypto-quant-lab/{scripts,templates} ~/lab/ && cd ~/lab
python3 -m venv .venv && source .venv/bin/activate
pip install pandas matplotlib

# 3. Store your API key locally (hidden input, never printed)
python scripts/setup_keys.py
```

Then start `opencode` in `~/lab` and say: *"Use the crypto-quant-lab skill and guide our group through the lab from Stage 0."*

## Contents

| Path | Purpose |
|---|---|
| `SKILL.md` | Stage-by-stage instructions the agent follows |
| `TA_CHECKLIST.md` | TA preparation checklist |
| `scripts/setup_keys.py` | API key wizard (writes `~/.bitget/env` / `env.live`, mode 600) |
| `scripts/data.py`, `strategies.py`, `backtest.py` | Data layer, strategy templates, backtest engine (fee 0.1%) |
| `scripts/risk.py` | Risk rules (sizing, caps, kill switch) |
| `scripts/trade.py` | Risk-gated paper/live orders (dry-run by default) |
| `scripts/report_html.py` | Single-file HTML result page |
| `templates/` | Report template and example output |

## Tutorial

Full step-by-step guide (before-class setup, ERC20 deposit address, 40-minute in-class plan): **MAFS6010G_Crypto_Quant_Lab_Tutorial.pdf**, available in the course Canvas *Files → Lab* folder.

## Safety

- API keys: **Read + Trade only — never enable Withdraw.** Use an IP allowlist for live keys.
- **Never commit or paste keys** (API key, secret, passphrase) into git, chat, or opencode. Keys live only in `~/.bitget/env*` (outside this repo).
- Paper trading and `--dry-run` by default; live orders need explicit confirmation and must stay within the group budget.
- Educational material only — not investment advice.

## Contacts (TAs)

- Henry — tamafs6010g@ust.hk
- WeiTao — mafsta3@ust.hk
