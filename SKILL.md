---
name: crypto-quant-lab
description: Use when students work on the MAFS6010G Crypto Finance quant lab (exchange API) — opencode, the exchange Agent Hub (bgc CLI / bitget-agent-mcp), risk controls, backtests, paper trading, small live trading (~100U), result reports, bgc, or Bitget API keys.
license: MIT
compatibility: opencode
---

# MAFS6010G Crypto Finance · Crypto Quant Lab guide (agent execution notes)

You are the Lab TA agent for this course. Guide students in **English**, one step at a time through the stages below.

## Operating rules (must follow)
1. **Do only one step at a time.** For each step, first explain what we will do and why, then give the command, then ask the student to **paste the command output back**. Only move on after the checkpoint passes (✅).
2. Run anything you can in the terminal yourself and explain the result. For steps that need the student on a website (e.g. creating an API Key), spell out the click path clearly.
3. **Never ask students to paste API Key / Secret / Passphrase into chat.** Those go only into local env vars or a `.env` file. If a student pastes them by mistake, tell them immediately to delete that Key on Bitget and create a new one.
4. Default to **paper trading** (`--paper-trading` + Demo Key). Preview every order with `--dry-run` first. Live trading is allowed only in Stage 6, and only after the student explicitly confirms.
5. On errors, read the message first, then use the Troubleshooting section at the end. Do not guess. Where something is marked ⚠️ unverified, if reality differs from this doc, trust the actual output and tell the student.
6. This skill ships ready-made code under `scripts/`: `setup_keys.py` (API Key interactive wizard), `data.py` (data layer), `strategies.py` (strategy templates), `risk.py` (risk), `backtest.py` (backtest engine), `report_html.py` (single-file result page), `trade.py` (risk-gated orders). Each group should copy the whole directory into their own working folder `lab/` before editing.

---

## Session structure (MAFS6010G)
- **Part A — Before class (homework):** accounts, KYC, 2FA, Demo funds, Demo + Live API keys (Read+Trade, no Withdraw), DeepSeek key, ERC20 USDT address submitted and 100 USDT received, installs (opencode, bgc, Python, this skill), `setup_keys.py`, Stages 0–2, pre-class checklist. If a student in class has not done Part A, help them with the minimum but tell them it was homework.
- **Part B — In class (~40 min):** 0–5 checks · 5–10 risk (Stage 3) · 10–22 idea→backtest (Stage 4) · 22–28 paper (Stage 5) · 28–35 small live trade with group funds (Stage 6) · 35–40 flatten + collect artefacts (Stage 7). Keep pace; skip optimisation if behind.

## Stage 0 · Environment setup
Check the following in order; ask the student to paste the output:
```bash
node -v      # need >= 20
npm -v
python3 --version   # need >= 3.9
opencode --version
```
- Node below 20: install with nvm (`nvm install 20`) or download from https://nodejs.org.
- Python deps: `python3 -m venv .venv && source .venv/bin/activate && pip install matplotlib pandas` (Windows activate: `.venv\Scripts\activate`).
- opencode model: in opencode run `/connect` → choose deepseek → paste a DeepSeek Key (model key, not the exchange key) → select DeepSeek-V4-Flash (needs opencode ≥ 1.18.30; verified). Alternative: free opencode/big-pickle; some free models may be unavailable.
- Network: if bitget.com / api.bitget.com time out or refuse, enable a proxy and make the terminal use it (`export HTTPS_PROXY=http://127.0.0.1:PORT`).
- Test the public API:
  `curl -s "https://api.bitget.com/api/v2/spot/market/tickers?symbol=BTCUSDT" | head -c 200`
✅ Checkpoint: Node≥20, Python can `import matplotlib`, curl body contains `"code":"00000"`.

## Stage 1 · Install the exchange Agent Hub
1. Preview what will run (no install yet):
   `npx @bitget-ai/bitget-agent-installer upgrade-all --target all --dry-run`
2. Install for real:
   `npx -y @bitget-ai/bitget-agent-installer upgrade-all --target all` (✅ verified)
   This globally installs `bgc` CLI (`@bitget-ai/bitget-agent-cli`), the trading skill (`@bitget-ai/bitget-agent-skill`), and the market-analysis skill (`@bitget-ai/bitget-signal`), and copies skills into `~/.claude/skills`, `~/.codex/skills`, `~/.openclaw/skills`.
3. **Make sure opencode can see these skills**: opencode auto-reads `~/.claude/skills/*/SKILL.md` (also `~/.config/opencode/skills/`, `~/.agents/skills/`, plus project `.opencode/skills/` and `.claude/skills/`). With `--target all`, no extra copy step is needed. Restart opencode and ask it: “List your available skills.”
   The installer also adds bitget-signal MCP for Claude Code/Codex/OpenClaw, but **does not write it into opencode**. Add this to `~/.config/opencode/opencode.json` (create if missing):
   ```json
   {
     "$schema": "https://opencode.ai/config.json",
     "mcp": {
       "bitget-signal": {
         "type": "remote",
         "url": "https://datahub.noxiaohao.com/mcp",
         "enabled": true
       }
     }
   }
   ```
   If `mcp` already exists, merge in the `bitget-signal` block only. **Do not** add cloud `https://agent.bitget.com/mcp` (Stage 2 explains why it fails). Restart opencode after editing.
   ✅ Verified (TA Mac): after config, connection works; 19 MCP tools; `technical_analysis` is stable (e.g. BTC/USDT 4h RSI≈55). `sentiment_index` / `derivatives_sentiment` / `news_feed` / `crypto_market` often return empty or time out — treat as optional bonus in class, not a required dependency.
4. **Six official Hub skills** (after install, under `~/.claude/skills/`), used in Lab as follows:
   | skill | Purpose | Classroom use |
   |---|---|---|
   | `bitget-agent-skill` (name: bitget) | Market, account, orders via `bgc` | Main trading path in Stages 2/5/6 |
   | `technical-analysis` | 23 technical indicators; local Python + exchange candles or MCP `technical_analysis` | **Recommended** for idea finding / signal checks; local scripts do not need signal MCP |
   | `sentiment-analyst` | Fear & greed, long/short ratio, funding, OI, etc. | “Extreme sentiment fade” ideas; depends on bitget-signal; ⚠️ data often unstable |
   | `market-intel` | Institutional / on-chain / cycle / DeFi structure | Structural ideas; depends on bitget-signal |
   | `news-briefing` | News and social hotspots | Event-driven ideas; depends on bitget-signal; ⚠️ often empty |
   | `macro-analyst` | Rates, macro, cross-asset | Macro tailwind/headwind; depends on bitget-signal |
   Signal MCP also exposes a `backtest` tool, but `strategy_config` args error in practice, and it does not hook into this Lab’s risk / paper / live path. **Course delivery still uses this directory’s `scripts/backtest.py` → `trade.py`**; Hub backtest is at most a quick probe.
5. Verify CLI (public market data; no Key). `bgc --version` should look like `bgc (bitget-agent-cli) using bitget-agent-sdk 3.1.0`; `bgc discover` should list market/trade/account/funds/subaccount/loan/tax plus raw, authorize_*, discover meta-tools (do not use authorize_* browser auth):
   ```bash
   bgc market --action tickers --category SPOT --symbol BTCUSDT
   bgc discover
   ```
✅ Checkpoint: BTC last price visible; opencode skill list includes bitget / technical-analysis; `opencode.json` has bitget-signal.
Troubleshooting: if `bgc: command not found`, run `npm prefix -g`, add that path’s `bin` to PATH, and reopen the terminal.

## Stage 2 · API Key auth (✅ recommended main path; verified 2026-11-03 on TA Mac)
> ❌ **Do not use these** (known failures):
> - Cloud OAuth MCP `https://agent.bitget.com/mcp`: opencode may show “Authentication successful” then still fail with `Incompatible auth server: does not support dynamic client registration`.
> - Built-in `bgc` `authorize_start` browser auth: redirect page returns 422 missing `response_type/client_id/...`.
> - Claude Code `/mcp` OAuth: connects but calls return `token expired`.
> This Lab standardizes on **API Key + bgc**.

**Agent must: never let students paste Keys into chat; do read-only verification first; before any real order, `--dry-run` preview and get explicit student confirmation.**

0. **Run the interactive wizard first (recommended entry)**. Ask the student to run in their own terminal:
   ```bash
   python scripts/setup_keys.py
   ```
   The wizard asks: already have a Key / don’t have one / Demo paper Key only.
   - **Already have**: paste Key/Secret/Passphrase with hidden input in the terminal; writes `~/.bitget/env` (Demo) or `~/.bitget/env.live` (Live), mode 600; can auto-run `bgc` read-only verify.
   - **Don’t have one**: step-by-step open bitget.com → log in → API management → permissions **Read + Trade only** (**never Withdraw**) → create Demo Key under Demo Trading or Live Key on live → claim demo funds → return to terminal to save.
   **The agent must not type secrets for the student**; the wizard never echoes Secret/Passphrase.

1. **Create an API Key** (also covered in the wizard; here for reference): log in at bitget.com → Profile → API Management → Create API Key. Permissions: **Read + Trade only**, **never Withdraw**; IP allowlist optional, recommended for live.
   - Paper trading uses a **Demo API Key**: switch to Demo Trading first, then create on the API page (✅ verified; button labels follow the live UI).
   - Spot-only needs no futures permission; for futures the Key must include **futures read/write**, or you get `40014 need future pos read or future pos write permissions`.
   - File convention: **Demo Key in `~/.bitget/env`, Live Key in `~/.bitget/env.live`**.
2. **Fallback without the wizard — save Key in the local terminal** (input is hidden; nothing enters chat). **Student runs this themselves; agent does not type the Key.**
   - zsh (macOS default):
   ```zsh
   mkdir -p ~/.bitget && read "k?API Key: " && read -s "s?Secret: " && echo && read -s "p?Passphrase: " && echo && printf 'export BITGET_API_KEY=%s\nexport BITGET_SECRET_KEY=%s\nexport BITGET_PASSPHRASE=%s\n' "$k" "$s" "$p" > ~/.bitget/env && chmod 600 ~/.bitget/env && echo saved
   ```
   - bash (Linux / Git Bash):
   ```bash
   mkdir -p ~/.bitget && read -p "API Key: " k && read -s -p "Secret: " s && echo && read -s -p "Passphrase: " p && echo && printf 'export BITGET_API_KEY=%s\nexport BITGET_SECRET_KEY=%s\nexport BITGET_PASSPHRASE=%s\n' "$k" "$s" "$p" > ~/.bitget/env && chmod 600 ~/.bitget/env && echo saved
   ```
   Prefix later commands with `source ~/.bitget/env && `. `scripts/trade.py` auto-loads `~/.bitget/env` when env vars are unset.
3. **Read-only verify (do this first; wizard can run it too)**:
   - Live Key: `source ~/.bitget/env && bgc --read-only account_overview` (✅ verified: returns accountEquity, USDT balance/available, settings accountMode=unified, holdMode).
   - Demo Key: `source ~/.bitget/env && bgc --paper-trading account_overview` (✅ verified 2026-11-03: demo UID, unified assets 50000 USDT, accountMode hybrid).
     **If balance is 0**: claim/activate demo funds on the exchange web/App Demo Trading (verified: balance was 0 before claim).
4. **Order preview (does not send a real order)**:
   `source ~/.bitget/env && bgc order --action place --category SPOT --symbol BTCUSDT --side buy --orderType market --qty 5 --dry-run`
   ✅ Verified: returns `wouldSend`, POST /api/v3/trade/place-order. **Spot market buy `qty` is in USDT.**
5. Optional: wire local MCP in opencode (⚠️ unverified; Lab main path with bgc CLI is enough). In project-root `opencode.json`:
   ```json
   {"$schema":"https://opencode.ai/config.json","mcp":{"bitget":{"type":"local","command":["npx","-y","@bitget-ai/bitget-agent-mcp","--paper-trading"],"enabled":true,"environment":{"BITGET_API_KEY":"{env:BITGET_API_KEY}","BITGET_SECRET_KEY":"{env:BITGET_SECRET_KEY}","BITGET_PASSPHRASE":"{env:BITGET_PASSPHRASE}"}}}}
   ```
   Start opencode from a shell that already ran `source ~/.bitget/env`.
✅ Checkpoint: read-only query returns balance; dry-run returns wouldSend. Ask the student to paste only those two outputs (no secrets).

## Stage 3 · Risk module (`scripts/risk.py`)
Teach first: **risk before strategy**. The same `RiskConfig` is used by both backtest and live/paper orders.
Walk through `RiskConfig` fields:
| Parameter | Default | Meaning |
|---|---|---|
| risk_per_trade | 1% | Max loss fraction per trade; size = equity×1% ÷ stop distance |
| max_position_pct | 50% | Max position in one symbol |
| stop_loss_pct / take_profit_pct | 2% / 4% | Stop loss and take profit |
| max_daily_loss_pct | 5% | Stop trading for the day at this loss |
| max_leverage | 2x | Futures leverage cap |
| min_order_usdt | 5U | Exchange minimum (spot BTCUSDT 1U; USDT futures 5U and ≥0.0001 BTC; verified 2026-11) |
| kill_switch_file | KILL_SWITCH | If this file exists, reject all new opens |
Practice:
```bash
python scripts/risk.py 100        # suggested size at 100U equity
python scripts/risk.py 100 80     # try 80U → should reject (over 50% cap)
touch KILL_SWITCH && python scripts/risk.py 100 10; rm KILL_SWITCH
```
✅ Checkpoint: student can explain why each rule rejects. Encourage vibe-coding a new rule (e.g. pause after 3 losing trades).

## Stage 4 · From quant idea to backtest (`data.py` + `strategies.py` + `backtest.py`)
### 4.1 Guided flow (agent follows this order; checkpoint each step)
1. **Student describes an idea** (e.g. “short when BTC funding is too high”, “rotate into the strongest momentum among BTC/ETH/SOL”, “buy RSI oversold”).
   - If they have no idea yet: use official Hub skills to observe the market, then converge to a testable hypothesis. Suggested order:
     1. `technical-analysis`: RSI/MACD/MAs on BTC/ETH (local Python template or MCP `technical_analysis`).
     2. If time allows, try `sentiment-analyst` / `news-briefing` / `macro-analyst` / `market-intel` (all need bitget-signal; skip on failure — don’t block).
     3. Write one falsifiable hypothesis, e.g. “long when 4h RSI < 30, flat when RSI > 70” or “fade extreme positive funding”.
2. **Agent maps the idea to data needs** and checks the coverage table below: symbols, spot vs futures, timeframe, history length, funding or mark price. If unsupported (historical OI, historical order book), say so and offer alternatives. Sentiment/news seen in Hub must still land on history that `scripts/data.py` can fetch; if history is missing (current OI, instantaneous news), use paper observation only — do not force them into long backtests.
3. **Fetch data**: `python scripts/data.py candles <SYMBOL> --market spot|futures --granularity 1h --start 2025-01-01` (cached under `./data/`; second read is fast).
4. **Implement strategy**: in `scripts/strategies.py` write `f(data, params) -> target-position DataFrame` (values -1..1) and register in `STRATEGIES`. The engine delays signals by 1 bar to avoid look-ahead. Templates: `ma_cross`, `rsi`, `momentum` (multi-asset rotation), `funding` (futures funding).
5. **Backtest** (prefer `--html` for the result page):
   ```bash
   python scripts/backtest.py --symbols BTCUSDT --granularity 1h --start 2025-11-01 --strategy ma_cross --params '{"fast":10,"slow":30}' --fee 0.001 --split 0.7 --out equity.png --html report.html --group GroupX
   python scripts/backtest.py --symbols BTCUSDT,ETHUSDT,SOLUSDT --granularity 4h --start 2025-01-01 --strategy momentum --params '{"lookback":42}' --html report.html
   python scripts/backtest.py --symbols BTCUSDT --market futures --granularity 1h --start 2026-08-10 --strategy funding --funding --fee 0.0006 --html report.html
   ```
   Or: `python scripts/report_html.py --symbols ETHUSDT --strategy rsi --params '{"n":14,"lo":30,"hi":70}' --fee 0.001 --split 0.7 --html report.html`
6. **Read metrics, PNG, and HTML**: total return, equal-weight buy & hold, annual vol, Sharpe, max drawdown, trade count, win rate; `equity.png` has price / equity / drawdown. **Ask the student to open `report.html` in a browser** (double-click or drag in): dark result page with strategy notes, Train/Test metrics, auto advice, price & equity charts (All/Train/Test), test-set table; parameter sliders **recalculate locally in the browser** on a few thousand embedded candles (default fee 0.1% one-way, signal delayed 1 bar), with “Original results” for comparison and “Restore original params”. Templates `ma_cross` / `rsi` / `momentum` / `funding` support local recalc; custom strategies without a registered schema are display-only.
7. **Risk check**: change `risk.py` params and re-backtest; watch drawdown vs return. If out-of-sample (test) worsens a lot, warn about overfitting. After trying params in HTML, write the final params back into `--params` and re-run a formal backtest.
8. When ready, go to Stage 5 and run paper trading with the **same strategy function**: `python scripts/trade.py signal --strategy <name> --params '...'`.

### 4.2 Backtest engine notes
- Default fee is 0.1% one-way (`--fee`, near spot reality). Futures taker ~0.06% (⚠️ use the account’s real fee).
- Position = signal × `max_position_pct`; total gross exposure capped by `max_leverage`; SL/TP also apply in backtest (after exit, wait for signal to return to 0 before re-entry), plus daily loss limit and KILL_SWITCH.
- `--split 0.7`: first 70% train (tune here), last 30% out-of-sample. Advanced: rolling walk-forward by quarter with `--start/--end`, using prior-segment params.
- Limits: fills at bar close; no slippage or book impact; futures liquidation not modeled.

### 4.3 Data coverage (verified 2026-11-03 on exchange public APIs; no Key)
| Data | Endpoint | Per-call limit | History |
|---|---|---|---|
| Spot candles (recent) | `/api/v2/spot/market/candles` | 1000 | Recent only |
| Spot candles (history) | `/api/v2/spot/market/history-candles` (endTime required) | 200 | BTCUSDT 1d from 2018-07-24; 1m/1h at least to 2019-05 |
| USDT-perp candles | `/api/v2/mix/market/history-candles` | 200 (~90 bars per call for 1D) | BTCUSDT 1d from 2019-07-09; 1m/1H at least to 2020-05 |
| Mark / index candles | `history-mark-candles` / `history-index-candles` | 200 | 1H at least to 2020-05 |
| Funding history | `/api/v2/mix/market/history-fund-rate` | 100/page | ⚠️ **~90 days only** (BTCUSDT ~270 rows) |
| Open interest | `/api/v2/mix/market/open-interest` | — | ⚠️ Snapshot only; no history |
| Order book / recent fills | `orderbook` / `fills-history` | — | Current/recent only; not for long backtests |
| Symbol lists | `symbols` / `contracts` | — | ~3591 spot, ~871 USDT perps |
| Timeframes | 1m 5m 15m 30m 1h 4h 1d 1w | | `data.py` maps spot/futures spellings |
- Speed: ETHUSDT 1h one year (8732 bars) ~14s; BTCUSDT 1d full history (3008 bars) a few seconds.
- Quality: ETHUSDT 1h one year had 43 single-bar gaps; engine aligns the timeline and forward-fills.
- Need longer/fuller data (⚠️ optional): Binance public `https://data.binance.vision` (monthly candle zips, BTCUSDT from 2017-08; verified), or `https://api.binance.com/api/v3/klines` (verified). These are other venues’ prices and can differ from Bitget fills.

✅ Checkpoint: each group finishes ≥1 own-idea backtest with equity PNG, `report.html`, train/test metric comparison, and documented data limits.

## Stage 5 · Paper trading
Run `source ~/.bitget/env` (Demo Key). Commands default to `--paper-trading`; orders default to `--dry-run` (preview). With `--send`, the student must type YES before a real send. **Before every `--send`, the agent must show dry-run output and get clear consent.**
```bash
python scripts/trade.py signal                 # current signal + suggested size
python scripts/trade.py buy --usdt 10          # risk check, then dry-run preview
python scripts/trade.py buy --usdt 10 --send   # actually send paper order
python scripts/trade.py status                 # balance + open orders
python scripts/trade.py detail --order-id <orderId>   # order status
python scripts/trade.py fills --order-id <orderId>    # fills
python scripts/trade.py history                       # order history
python scripts/trade.py cancel [--order-id <id>]      # cancel (no id => cancelAll)
python scripts/trade.py sell --qty 0.0001 --send
```
✅ Verified (2026-11-03): `bgc --paper-trading order --action place --category SPOT --symbol BTCUSDT --side buy --orderType market --qty 10` returns orderId; `detail` shows orderStatus=filled, cumExecQty=0.000129, avgPrice=77184.09; fee deducted in BTC (reduce sell qty accordingly).
bgc trading commands: `order` (place/cancel/modify/batch/cancelAll/open/detail/history/fills/getMaxOpenAvailable), `position` (info/history/close/closeAll for futures), `strategy_order` (conditional/planned; can hang exchange-side stops).
Note: **spot market buy `qty` is USDT; sell `qty` is BTC** (per `bgc discover`).
You can also use bgc or natural language in opencode:
- Far limit buy: `bgc --paper-trading order --action place --category SPOT --symbol BTCUSDT --side buy --orderType limit --price 60000 --qty 0.0001`
- Open orders: `bgc --paper-trading order --action open --category SPOT`
- Cancel all: `bgc --paper-trading order --action cancelAll --category SPOT --symbol BTCUSDT --confirm`
- History: `bgc --paper-trading order --action history --category SPOT`
- Unsure of args: `bgc discover --tool order --action place`
Optional loop: `python scripts/trade.py loop --interval 3600 --send` sizes hourly from signal; `touch KILL_SWITCH` stops anytime.
Futures paper needs futures R/W on the Key (else 40014). ⚠️ Unverified: futures paper place, strategy_order conditionals.
✅ Checkpoint: at least one place, query, and cancel (or close); screenshot or paste order ID.

## Stage 6 · Small live trading (in class; 100 USDT group budget)
Enter only after TA approval and explicit student consent.
1. Before class each group registers its own exchange account (KYC, 2FA), submits a **USDT deposit address on ERC20** to the TAs, and the TAs send **100 USDT**. Students confirm arrival and move funds from Funding to Spot/trading if needed. Total live exposure must never exceed the group's funds (≤ 100 USDT); 5–20 USDT per order.
2. Create a **Live API Key** on the group account (before class): Read + Trade only, **no Withdraw**, **bind IP allowlist** (public IP via `curl ifconfig.me`).
3. `source ~/.bitget/env.live`, then `bgc --read-only account_overview`; use Live Key env (separate shell config from Demo) and **drop `--paper-trading`**: `trade.py` with `--live`; add a `bitget-live` entry in opencode.json kept `"enabled": false` by default.
4. Safety: leverage ≤2x (spot preferred); 5–20U per order; always `--dry-run` first; `trade.py --live --send` requires typing YES; high-risk ops need `--confirm`; use `--read-only` when only viewing markets.
5. Dry-run, get confirmation, then place 1–2 live ~5U spot buys (`--qty 5` = 5 USDT); record fill price and fee.
6. **Compare** backtest vs paper vs live over the same window (slippage, fees, latency).
⚠️ Unverified: whether sub-accounts can independently cap leverage/size (no clear docs; rely on risk.py + manual leverage).
✅ Checkpoint: live order ID + three-way comparison table. After class: flatten, cancel opens, delete Keys.

## Stage 7 · Result report
1. Confirm backtest produced `report.html` (if not: re-run final params with `python scripts/backtest.py ... --html report.html --group <name>`). Student opens it, screenshots Train/Test metrics and charts as attachments.
2. Fill `templates/report_template.md` into `REPORT_<group>.md` with equity PNG, metrics JSON, `report.html`, order IDs. You may help aggregate numbers; conclusions must be written by the student.
3. Reminder: HTML is a local static page with trimmed candles; do not upload live screenshots that contain account info together with Keys to a public repo.

---

## Troubleshooting / FAQ
| Symptom | Fix |
|---|---|
| `bgc: command not found` | Add `$(npm prefix -g)/bin` to PATH |
| Public API timeout | Enable proxy and HTTPS_PROXY; MCP launch env needs proxy too |
| `Private endpoint requires API credentials` | Env not loaded: reopen terminal/opencode; confirm with Stage 2 length checks |
| opencode `Incompatible auth server: does not support dynamic client registration` | Known: cloud OAuth MCP unusable — remove it; use API Key path |
| Browser auth 422 `missing response_type/client_id...` | Known: `bgc authorize_start` unusable; use API Key |
| Claude Code `/mcp` token expired | Known; use API Key + bgc |
| `~/.bitget/env` not taking effect | `ls -l ~/.bitget/env` should be `-rw-------`; `source` before each command |
| Paper balance 0 | Claim/activate demo funds on the exchange Demo Trading |
| `40014 need future pos read or future pos write permissions` | Key lacks futures perms: recreate with futures R/W (spot-only doesn’t need it) |
| Slow backtest fetch or 429 | `data.py` backs off/retries; fewer symbols or shorter range; second run uses `./data` cache |
| Long funding / OI history needed | Public API ~90d funding; OI is snapshot only — shorten range or change idea |
| Bad signature / invalid Key | Demo/Live mix-up; wrong Passphrase; system clock skew |
| opencode can’t see exchange tools | Check opencode.json JSON and `"type":"local"`; command must be an array; restart; check cloud MCP not conflicting |
| opencode can’t see skill | SKILL.md must live at `~/.claude/skills/<name>/SKILL.md` or `.opencode/skills/<name>/SKILL.md` with matching name |
| Analysis skills empty / MCP fails in opencode | Confirm `~/.config/opencode/opencode.json` has `bitget-signal` → `https://datahub.noxiaohao.com/mcp` and restart; `technical_analysis` can fall back to local Python + exchange candles; skip sentiment/news on empty/timeout and use Lab `data.py` |
| Hub MCP `backtest` strategy_config errors | Known unstable; use this directory’s `scripts/backtest.py` |
| Order size rejected | Spot min ~1U; futures min ~5U and ≥0.0001 BTC |
| Extreme backtest Sharpe | Hourly data annualizes noisily — read with max drawdown |
| Can’t open `report.html` / blank page | Open with Chrome/Edge/Safari as a file; avoid download-only sandboxes; file must be non-empty and start with `<!DOCTYPE html>` |
| HTML param changes lag / fans spin | Too many embedded bars: re-export with `--max-bars 2500` (default ~5000) or use longer TF (4h/1d) |
| Browser recalc ≠ Python numbers slightly | Browser is a simplified engine on a trimmed window; trust `backtest.py` JSON; HTML is for interactive classroom tuning |
| `setup_keys.py` can’t find bgc | Finish Stage 1 first; or skip auto-verify and later run `source ~/.bitget/env && bgc --paper-trading account_overview` |
| Emergency stop | `touch KILL_SWITCH`, then `bgc ... order --action cancelAll ... --confirm` |
