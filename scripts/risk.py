"""Risk module: the same rules for backtest and paper/live. Edit RiskConfig to tune."""
from dataclasses import dataclass
import json, os, time

@dataclass
class RiskConfig:
    capital_usdt: float = 100.0      # group capital
    risk_per_trade: float = 0.01     # max 1% equity loss per trade (size from stop distance)
    max_position_pct: float = 0.5    # max single-symbol fraction of equity
    stop_loss_pct: float = 0.02      # stop loss 2%
    take_profit_pct: float = 0.04    # take profit 4%
    max_daily_loss_pct: float = 0.05 # stop trading after 5% daily loss
    max_leverage: float = 2.0        # futures leverage cap
    min_order_usdt: float = 5.0      # exchange min notional (spot 1U, USDT futures 5U)
    kill_switch_file: str = "KILL_SWITCH"  # if this file exists => refuse all new orders

class RiskManager:
    def __init__(self, cfg: RiskConfig = RiskConfig()):
        self.cfg = cfg
        self.day = None
        self.day_start_equity = cfg.capital_usdt

    def kill_switch_on(self) -> bool:
        return os.path.exists(self.cfg.kill_switch_file)

    def new_bar(self, ts_ms: int, equity: float):
        d = time.strftime("%Y-%m-%d", time.gmtime(ts_ms / 1000))
        if d != self.day:
            self.day, self.day_start_equity = d, equity

    def daily_loss_hit(self, equity: float) -> bool:
        return equity <= self.day_start_equity * (1 - self.cfg.max_daily_loss_pct)

    def position_size_usdt(self, equity: float, leverage: float = 1.0) -> float:
        """Notional from risk-per-trade / stop distance, then capped by max position and leverage."""
        lev = min(leverage, self.cfg.max_leverage)
        by_risk = equity * self.cfg.risk_per_trade / self.cfg.stop_loss_pct
        cap = equity * self.cfg.max_position_pct * lev
        return max(0.0, min(by_risk, cap))

    def check_order(self, equity: float, notional_usdt: float, leverage: float = 1.0):
        """Pre-trade check → (allowed, reason). Must call before paper/live orders."""
        if self.kill_switch_on():
            return False, "KILL_SWITCH file present; trading halted"
        if self.daily_loss_hit(equity):
            return False, "Daily max loss hit"
        if leverage > self.cfg.max_leverage:
            return False, f"Leverage {leverage} exceeds cap {self.cfg.max_leverage}"
        if notional_usdt < self.cfg.min_order_usdt:
            return False, f"Notional {notional_usdt:.2f}U below min order {self.cfg.min_order_usdt}U"
        if notional_usdt > equity * self.cfg.max_position_pct * leverage + 1e-9:
            return False, "Exceeds single-symbol max position"
        return True, "OK"

    def exit_signal(self, entry: float, price: float, side: str = "long"):
        r = (price / entry - 1) * (1 if side == "long" else -1)
        if r <= -self.cfg.stop_loss_pct: return "stop_loss"
        if r >= self.cfg.take_profit_pct: return "take_profit"
        return None

if __name__ == "__main__":
    import sys
    rm = RiskManager()
    eq = float(sys.argv[1]) if len(sys.argv) > 1 else 100
    n = float(sys.argv[2]) if len(sys.argv) > 2 else rm.position_size_usdt(eq)
    print(json.dumps({"suggested_size_usdt": round(rm.position_size_usdt(eq), 2),
                      "check": rm.check_order(eq, n)}, ensure_ascii=False))
