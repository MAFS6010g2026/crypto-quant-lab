# TA checklist — Hyperliquid testnet Quant Lab

## One-time TA wallet
1. Use a dedicated wallet. Deposit **≥ 5 USDC** on Hyperliquid **mainnet** (Arbitrum USDC → official Bridge2 `0x2Df1c51E09aECF9cacB7bc98cB1742757f163dF7`). Below 5 USDC is lost.
2. On testnet, claim drip: `POST https://api.hyperliquid-testnet.xyz/info` body `{"type":"claimDrip","user":"<TA_ADDRESS>"}` (or the testnet drip UI). Expect ~1000 mock USDC once eligibility is met. Same address cannot re-claim.
3. Keep the TA master key offline. Prefer an **API/agent** key for automated `usd_transfer` scripts.

## Per session / per class
1. Collect wallet addresses (Google Form https://forms.gle/7VGu9s6vZFJgRLRFA). Deadline: Fri 6 Nov 2026, 23:59 HKT.
   - **Required:** one group shared wallet per Group Leader.
   - **Optional:** individual practice wallets from students who want their own sandbox.
2. Fund on **testnet** via `usd_transfer`:
   - Group wallets: **~100** mock USDC received (send ~101; fee ≈1).
   - Individual practice: **~15** received (send ~16), subject to remaining faucet balance and submitter count.
   - Keep a small TA demo reserve (~20).
3. Groups (and individuals) create an API/agent wallet on https://app.hyperliquid-testnet.xyz and run `setup_keys.py` on one laptop.
4. In class (~40 min): risk → backtest (mainnet public candles) → testnet trades → report.

## Verified on TA sandbox (2026-11-05)
- claimDrip API works after mainnet deposit; cannot re-faucet the same address.
- Fresh address can trade after receiving `usd_transfer` (no faucet needed).
- Agent wallet can place/cancel; cannot withdraw.
