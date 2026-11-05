#!/usr/bin/env python3
"""Exchange API Key interactive terminal wizard (TUI).
Never print secrets to the screen or logs; write ~/.bitget/env (Demo) or ~/.bitget/env.live (Live), chmod 600.
Usage: python scripts/setup_keys.py
"""
from __future__ import annotations
import getpass, os, shutil, subprocess, sys

HOME = os.path.expanduser("~")
DIR = os.path.join(HOME, ".bitget")
DEMO_ENV = os.path.join(DIR, "env")
LIVE_ENV = os.path.join(DIR, "env.live")

def say(msg=""):
    print(msg)

def ask(prompt, default=None):
    suf = f" [{default}]" if default is not None else ""
    s = input(f"{prompt}{suf}: ").strip()
    return s if s else default

def ask_choice(prompt, choices):
    """choices: list of (key, label). Returns key."""
    say(f"\n{prompt}")
    for k, label in choices:
        say(f"  {k}) {label}")
    while True:
        c = input("Enter option number: ").strip()
        if any(c == k for k, _ in choices):
            return c
        say("Invalid option, try again.")

def write_env(path, key, secret, passphrase):
    os.makedirs(DIR, exist_ok=True)
    # Do not write secrets to any other temp file; write the target file directly
    body = (
        f"export BITGET_API_KEY={key}\n"
        f"export BITGET_SECRET_KEY={secret}\n"
        f"export BITGET_PASSPHRASE={passphrase}\n"
    )
    with open(path, "w", encoding="utf-8") as f:
        f.write(body)
    os.chmod(path, 0o600)
    say(f"✅ Saved to {path} (mode 600). Secrets are not shown in the output above.")

def collect_keys():
    say("\nPaste in this terminal (Secret / Passphrase input is hidden):")
    say("⚠️ Do not paste Keys into chat or share them with anyone.")
    key = input("API Key: ").strip()
    secret = getpass.getpass("Secret: ").strip()
    passphrase = getpass.getpass("Passphrase: ").strip()
    if not key or not secret or not passphrase:
        say("❌ Key / Secret / Passphrase cannot be empty.")
        return None
    return key, secret, passphrase

def guide_create(demo=True):
    kind = "Demo (paper)" if demo else "Live"
    say("\n" + "=" * 56)
    say(f"[No Key yet] Follow these steps to create a {kind} API Key")
    say("=" * 56)
    steps = [
        "1. Open https://www.bitget.com in a browser and log into the course account.",
        "2. Go to: Profile → API Management (or Account → API).",
    ]
    if demo:
        steps += [
            "3. Switch to the Demo Trading page first (button labels follow the live UI).",
            "4. Create an API Key while in the Demo environment.",
            "5. Permissions: check Read + Trade only; ⚠️ never check Withdraw.",
            "6. For futures, also enable futures read/write; spot-only can skip futures.",
            "7. Copy Key / Secret / Passphrase carefully (Secret is shown only once).",
            "8. If Demo balance is 0: claim/activate demo funds on the Demo Trading page.",
        ]
    else:
        steps += [
            "3. Confirm you are in the Live environment (not still on Demo Trading).",
            "4. Create an API Key; permissions Read + Trade only; ⚠️ never Withdraw.",
            "5. Bind an IP allowlist (public IP: curl ifconfig.me).",
            "6. For futures, enable futures read/write.",
            "7. Copy Key / Secret / Passphrase carefully.",
            "8. Classroom live trading uses the TA-funded group sub-account — do not touch large main-account balances.",
        ]
    for s in steps:
        say(s)
    say("\nWhen finished, return to this terminal.")
    input("Press Enter to continue to paste & save…")

def verify(path, paper=True):
    say("\n[Verify] About to run a read-only query (no orders).")
    if not shutil.which("bgc"):
        say("⚠️ bgc not found on PATH. Finish Stage 1 (install Agent Hub) first.")
        say("After install, verify manually:")
        if paper:
            say(f"  source {path} && bgc --paper-trading account_overview")
        else:
            say(f"  source {path} && bgc --read-only account_overview")
        return False
    # source via bash so secrets are not placed on argv
    if paper:
        cmd = f'source "{path}" && bgc --paper-trading account_overview'
    else:
        cmd = f'source "{path}" && bgc --read-only account_overview'
    say(f"$ {cmd.replace(os.path.expanduser('~'), '~')}")
    try:
        r = subprocess.run(["bash", "-lc", cmd], capture_output=True, text=True, timeout=60)
    except Exception as e:
        say(f"⚠️ Verify call failed: {e}")
        return False
    out = (r.stdout or "") + (r.stderr or "")
    # Do not print full env; show a bgc output preview only
    preview = out.strip()
    if len(preview) > 1200:
        preview = preview[:1200] + "\n…(truncated)"
    say(preview or "(no output)")
    ok = r.returncode == 0 and ("accountEquity" in out or "available" in out or "USDT" in out or '"code"' in out)
    if r.returncode != 0:
        say(f"⚠️ bgc exit code {r.returncode}. See SKILL.md troubleshooting (balance 0 / invalid Key / Demo-Live mix-up).")
        return False
    if ok:
        say("✅ Read-only verify looks successful.")
    else:
        say("⚠️ Command ran, but output does not look like an account overview. Please check manually.")
    return ok

def next_steps():
    say("\n" + "=" * 56)
    say("Next steps (from Stage 3)")
    say("=" * 56)
    say("1. Risk: python scripts/risk.py 100")
    say("2. Fetch data / backtest: see SKILL.md Stage 4")
    say("3. After backtest, result page: python scripts/backtest.py ... --html report.html")
    say("4. Before paper trading: source ~/.bitget/env && bgc --paper-trading account_overview")
    say("Good luck with the Lab!\n")

def main():
    say("=" * 56)
    say(" MAFS6010G Crypto Quant Lab · API Key setup wizard")
    say("=" * 56)
    say("This wizard only reads/writes ~/.bitget/ on this machine. Secrets are not sent to the network (except verify: bgc calling the exchange API).")

    choice = ask_choice(
        "Where are you now?",
        [
            ("1", "I already have an API Key — save it locally"),
            ("2", "I don't have a Key — guide me to create one (Demo paper)"),
            ("3", "I don't have a Key — guide me to create one (Live)"),
            ("4", "Demo paper Key only (save existing or create into ~/.bitget/env)"),
            ("5", "Exit"),
        ],
    )
    if choice == "5":
        say("Exited."); return 0

    paper = True
    path = DEMO_ENV
    if choice == "1":
        which = ask_choice(
            "Which kind of Key is this?",
            [("1", "Demo paper → save to ~/.bitget/env"),
             ("2", "Live → save to ~/.bitget/env.live")],
        )
        paper = which == "1"
        path = DEMO_ENV if paper else LIVE_ENV
    elif choice == "2":
        guide_create(demo=True)
        paper, path = True, DEMO_ENV
    elif choice == "3":
        guide_create(demo=False)
        paper, path = False, LIVE_ENV
    elif choice == "4":
        has = ask_choice(
            "Is the Demo Key already created?",
            [("1", "Yes — paste and save now"),
             ("2", "Not yet — show create guide first")],
        )
        if has == "2":
            guide_create(demo=True)
        paper, path = True, DEMO_ENV

    if os.path.exists(path):
        ov = ask_choice(
            f"{path} already exists. Overwrite?",
            [("1", "Overwrite"), ("2", "Cancel — leave existing file")],
        )
        if ov == "2":
            say("Cancelled."); return 0

    keys = collect_keys()
    if not keys:
        return 1
    key, secret, passphrase = keys
    write_env(path, key, secret, passphrase)
    # Drop local references ASAP (best effort)
    del key, secret, passphrase, keys

    do_v = ask_choice("Run read-only verify now?", [("1", "Yes"), ("2", "Later")])
    if do_v == "1":
        verify(path, paper=paper)
    else:
        if paper:
            say(f"Later run: source {path} && bgc --paper-trading account_overview")
        else:
            say(f"Later run: source {path} && bgc --read-only account_overview")

    next_steps()
    return 0

if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        say("\nInterrupted."); sys.exit(130)
