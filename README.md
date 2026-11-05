# crypto-quant-lab — MAFS6010G Crypto Finance Quant Lab

An [opencode](https://opencode.ai) skill that acts as your lab TA for the **MAFS6010G Crypto Finance** Quant Lab. It guides each group step by step through:

**idea → strategy → risk controls → backtest → paper trading → small live trade (group budget) → result report**

The lab trades through the Bitget exchange API (via the `bgc` CLI). Use a DeepSeek model in opencode.

## Install with opencode (recommended)

1. Install [opencode](https://opencode.ai/docs/) and connect a DeepSeek model (`/connect` → DeepSeek).
2. Start `opencode` in your home folder and paste the prompt below. The agent installs everything; **you** then run the key wizard yourself.

```text
Please install the MAFS6010G Crypto Quant Lab for me. Work step by step, show each command before running it, and stop to ask me if anything fails.

SAFETY RULES (follow strictly):
- Never ask me for, read, print, or handle any API key, secret, or passphrase. Do not open ~/.bitget/ files.
- Do not use sudo or install system packages without asking me first.
- Do not place any orders or run trading commands.

STEPS:
1. Check tools: run `git --version`, `python3 --version` (need >= 3.9; on Windows try `python`), `node -v` (need >= 20), `npm -v`. If one is missing, tell me how to install it and wait.
2. Get the skill: if ~/.claude/skills/crypto-quant-lab already exists and is a git repo, run `git -C ~/.claude/skills/crypto-quant-lab pull`; otherwise run
   `mkdir -p ~/.claude/skills && git clone https://github.com/MAFS6010g2026/crypto-quant-lab.git ~/.claude/skills/crypto-quant-lab`
   (On Windows use WSL, or the same path under %USERPROFILE%\.claude\skills\crypto-quant-lab.)
   If the network times out, ask me whether to set a proxy (e.g. export https_proxy=http://127.0.0.1:<port>).
3. Lab folder: `mkdir -p ~/lab && cp -R ~/.claude/skills/crypto-quant-lab/scripts ~/.claude/skills/crypto-quant-lab/templates ~/lab/` (do not overwrite files I have edited in ~/lab without asking).
4. Python env: `cd ~/lab && python3 -m venv .venv`, then install with the venv's pip: `.venv/bin/pip install numpy pandas matplotlib` (Windows: `.venv\Scripts\pip`).
5. Exchange CLI: `npx -y @bitget-ai/bitget-agent-installer upgrade-all --target all`, then `bgc --version` (if not found, add `$(npm prefix -g)/bin` to PATH for this session).
6. Verify: `cd ~/lab && .venv/bin/python scripts/backtest.py --help` and `.venv/bin/python scripts/risk.py 100`. Confirm ~/.claude/skills/crypto-quant-lab/SKILL.md exists.
7. Finish with a short summary table (tool, version, OK/FAIL), then tell me:
   (a) to run the key wizard MYSELF in a normal terminal (not in this chat): `cd ~/lab && source .venv/bin/activate && python scripts/setup_keys.py`
   (b) to quit and restart opencode so the crypto-quant-lab skill is loaded.
```

After it finishes: run `python scripts/setup_keys.py` in your own terminal (never paste keys into opencode), then restart opencode.

## Manual install (fallback)

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
