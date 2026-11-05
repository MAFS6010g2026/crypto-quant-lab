#!/usr/bin/env python3
"""Hyperliquid key wizard: store master address + API/agent private key.
Writes ~/.hyperliquid/env (mode 600). Never prints the agent key.
"""
from __future__ import annotations
import getpass, os, re, sys

HOME = os.path.expanduser("~")
DIR = os.path.join(HOME, ".hyperliquid")
ENV = os.path.join(DIR, "env")

def say(msg=""): print(msg)

def ask(prompt, default=None):
    suf = f" [{default}]" if default is not None else ""
    s = input(f"{prompt}{suf}: ").strip()
    return s if s else default

def valid_addr(a: str) -> bool:
    return bool(re.fullmatch(r"0x[0-9a-fA-F]{40}", a or ""))

def write_env(address: str, agent_key: str, network: str = "testnet"):
    if not agent_key.startswith("0x"):
        agent_key = "0x" + agent_key
    os.makedirs(DIR, exist_ok=True)
    body = (
        f"export HL_ACCOUNT_ADDRESS={address}\n"
        f"export HL_AGENT_KEY={agent_key}\n"
        f"export HL_NETWORK={network}\n"
    )
    with open(ENV, "w", encoding="utf-8") as f:
        f.write(body)
    os.chmod(ENV, 0o600)
    say(f"✅ Saved to {ENV} (mode 600). Agent key is not shown above.")

def guide():
    say("\n" + "=" * 60)
    say("Create an API / agent wallet on Hyperliquid TESTNET")
    say("=" * 60)
    say("""
1. Open https://app.hyperliquid-testnet.xyz and connect the group wallet
   (MetaMask / Rabby). Use TESTNET — the URL must contain 'testnet'.
2. Confirm the group has mock USDC (TAs fund ~150 per group).
3. Open the API / agent wallet page (often linked from the account menu
   as "API" — exact label can change; look for "API wallet" / "Agent").
4. Create a named API wallet (e.g. lab-bot). Copy:
     - Your MASTER address (the connected wallet)
     - The AGENT private key shown once (this key can TRADE but NOT withdraw)
5. Never paste the seed phrase or master private key into chat or into
   opencode. Only the agent key goes into this wizard.
""")

def verify_readonly(address: str, agent_key: str, network: str):
    try:
        from eth_account import Account
        from hyperliquid.info import Info
        from hyperliquid.utils import constants
        if not agent_key.startswith("0x"):
            agent_key = "0x" + agent_key
        agent = Account.from_key(agent_key)
        base = constants.TESTNET_API_URL if network != "mainnet" else constants.MAINNET_API_URL
        info = Info(base, skip_ws=True)
        st = info.user_state(address)
        av = (st.get("marginSummary") or {}).get("accountValue")
        say(f"Read-only check: network={network} master={address}")
        say(f"  agent_address={agent.address}")
        say(f"  accountValue={av}")
        say("✅ Keys parse and account is reachable (trading not tested here).")
    except Exception as e:
        say(f"⚠️ Verify failed: {type(e).__name__}: {e}")
        say("Keys were still saved; fix network / funding and retry trade.py balance.")

def main():
    say("MAFS6010G · Hyperliquid key setup (Option B / testnet)")
    say("Agent keys can trade but cannot withdraw. Never share seed phrases.")
    c = ask("Choose: 1=I have master address + agent key  2=Show create guide first  3=Quit", "1")
    if c == "3":
        return
    if c == "2":
        guide()
        input("Press Enter when ready to paste keys…")
    network = ask("Network (testnet/mainnet)", "testnet").lower()
    if network not in ("testnet", "mainnet"):
        say("Invalid network"); return
    if network == "mainnet":
        say("⚠️ Mainnet is optional and subject to course approval.")
    address = ask("Master wallet address (0x…)")
    if not valid_addr(address):
        say("❌ Address must be 0x + 40 hex chars"); return
    say("Paste agent private key (hidden):")
    agent_key = getpass.getpass("HL_AGENT_KEY: ").strip()
    if len(agent_key) < 64:
        say("❌ Agent key looks too short"); return
    write_env(address, agent_key, network)
    if ask("Run read-only verify now? (y/n)", "y").lower().startswith("y"):
        verify_readonly(address, agent_key, network)
    say("\nNext: source ~/.hyperliquid/env && python trade.py balance")
    say("Restart opencode after setup so it can use the env file path (not the secret).")

if __name__ == "__main__":
    main()
