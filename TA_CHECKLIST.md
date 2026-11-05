# TA checklist — Option B (Hyperliquid testnet)

## One-time TA wallet
1. Use a dedicated wallet. Deposit **≥ 5 USDC** on Hyperliquid **mainnet** (Arbitrum USDC → official Bridge2 `0x2Df1c51E09aECF9cacB7bc98cB1742757f163dF7`). Below 5 USDC is lost.
2. On testnet, claim drip: `POST https://api.hyperliquid-testnet.xyz/info` body `{"type":"claimDrip","user":"<TA_ADDRESS>"}` (or the testnet drip UI). Expect ~1000 mock USDC once eligibility is met.
3. Keep the TA master key offline. Prefer an **API/agent** key for automated `usd_transfer` scripts.

## Per session / per class
1. Collect group wallet addresses (Google Form). Deadline example: Fri 6 Nov 23:59 HKT.
2. Fund each group with **~150 mock USDC** on **testnet** via `usd_transfer`.
   - Testnet transfer fee is about **1 USDC** → send **≥ 2** so the group receives ≥ 1; for ~150 received, send **~151**.
3. Groups create an API/agent wallet on https://app.hyperliquid-testnet.xyz and run `setup_keys.py` on one laptop.
4. In class (~40 min): risk → backtest (mainnet public candles) → testnet trades → report.
5. Optional mainnet live trading only with course / instructor approval.

## Verified on TA sandbox (2026-11-05)
- claimDrip API works after mainnet deposit.
- Fresh address can trade after receiving `usd_transfer` (no faucet needed).
- Agent wallet can place/cancel; cannot withdraw.
