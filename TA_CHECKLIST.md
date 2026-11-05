# TA pre-class checklist
Verified (2026-11-03, macOS/zsh/Node 24/opencode 1.19.5): installer, bgc read-only account_overview, order dry-run, DeepSeek-V4-Flash in opencode, skills loaded from ~/.claude/skills; Demo Key + `bgc --paper-trading` balance (50000 USDT) and spot market order (filled).
Known failures — do not use: cloud OAuth MCP (dynamic client registration error), bgc authorize_start (422), Claude Code /mcp OAuth (token expired).
- [ ] Tell students in advance to prepare a DeepSeek API Key (or use free big-pickle)
- [ ] Confirm everyone knows Keys must be written via `read` into ~/.bitget/env — never pasted into chat
- [ ] Remind: Demo funds must be claimed on the Demo Trading page (else balance is 0); futures Keys must include futures R/W (else 40014)
- [ ] Optional: warm data cache before class: `python scripts/data.py candles BTCUSDT --granularity 1h --start 2025-11-01`, distribute ./data to reduce classroom network load
- [ ] Run one paper place / query / cancel: `python scripts/trade.py buy --usdt 10 --send` / `status`; confirm account_overview fields (and trade.py detail/fills/cancel)
- [ ] Configure bitget MCP in opencode.json; confirm tools list (and `{env:VAR}` substitution)
- [ ] Confirm opencode reads skills from ~/.claude/skills and can see this skill
- [ ] Classroom network can reach api.bitget.com (have a proxy plan ready)
- [ ] Python env and matplotlib installed
- [ ] Live: collect one ERC20 USDT deposit address per group (form + deadline), send 100 USDT each on ERC20, confirm arrival; groups' Live Keys Read+Trade only (no Withdraw) with IP bind; record each group's UID
- [ ] Announce Part A (before class) homework + pre-class checklist; in class ~40 min agenda
- [ ] Decide whether to allow futures (spot-only recommended)
- [ ] After class: groups flatten, cancel opens, delete Keys; follow course policy for remaining funds
- [ ] Distribution: copy `crypto-quant-lab/` into `~/.claude/skills/` or project `.opencode/skills/` (directory name must be crypto-quant-lab)
