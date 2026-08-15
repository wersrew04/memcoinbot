"""Backtesting Engine – historical strategy simulation (scaffold).

Full implementation requires historical OHLCV + trade logs from Birdeye/Helius.
This module provides the interface, metrics computation, and a simple synthetic runner.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from utils.logger import logger
from utils.helpers import safe_float
from config.settings import settings


@dataclass
class BacktestResult:
    period_days: int
    total_trades: int = 0
    win_rate: float = 0.0
    roi_pct: float = 0.0
    profit_usd: float = 0.0
    loss_usd: float = 0.0
    net_pnl: float = 0.0
    max_drawdown_pct: float = 0.0
    sharpe_ratio: float = 0.0
    profit_factor: float = 0.0
    avg_trade_usd: float = 0.0
    best_trade_usd: float = 0.0
    worst_trade_usd: float = 0.0
    equity_curve: List[float] = field(default_factory=list)
    notes: str = ""


class BacktestEngine:
    SUPPORTED_DAYS = (7, 30, 90, 180, 365)

    def __init__(self):
        pass

    def compute_metrics(self, trades: List[Dict[str, Any]], initial_capital: float = 1000.0) -> BacktestResult:
        """Compute standard metrics from a list of closed trades (pnl_usd each)."""
        if not trades:
            return BacktestResult(period_days=0, notes="No trades")

        pnls = [safe_float(t.get("pnl_usd")) for t in trades]
        wins = [p for p in pnls if p > 0]
        losses = [p for p in pnls if p < 0]
        net = sum(pnls)
        profit = sum(wins)
        loss = abs(sum(losses))
        n = len(pnls)
        wr = len(wins) / n if n else 0.0
        roi = (net / initial_capital) * 100 if initial_capital else 0.0
        pf = (profit / loss) if loss > 0 else (float("inf") if profit > 0 else 0.0)

        # equity curve + max DD
        equity = [initial_capital]
        peak = initial_capital
        max_dd = 0.0
        for p in pnls:
            eq = equity[-1] + p
            equity.append(eq)
            peak = max(peak, eq)
            dd = (peak - eq) / peak if peak > 0 else 0
            max_dd = max(max_dd, dd)

        # simple sharpe (assume daily, risk-free 0)
        import statistics
        if len(pnls) > 1:
            mean = statistics.mean(pnls)
            std = statistics.stdev(pnls) or 1e-9
            sharpe = (mean / std) * (n ** 0.5)  # rough
        else:
            sharpe = 0.0

        return BacktestResult(
            period_days=0,
            total_trades=n,
            win_rate=round(wr * 100, 2),
            roi_pct=round(roi, 2),
            profit_usd=round(profit, 2),
            loss_usd=round(loss, 2),
            net_pnl=round(net, 2),
            max_drawdown_pct=round(max_dd * 100, 2),
            sharpe_ratio=round(sharpe, 3),
            profit_factor=round(pf, 3) if pf != float("inf") else 999.0,
            avg_trade_usd=round(net / n, 2),
            best_trade_usd=round(max(pnls), 2),
            worst_trade_usd=round(min(pnls), 2),
            equity_curve=[round(e, 2) for e in equity],
        )

    async def run(
        self,
        days: int = 30,
        strategy: str = "default",
        initial_capital: float = 1000.0,
        trades: Optional[List[Dict[str, Any]]] = None,
    ) -> BacktestResult:
        if days not in self.SUPPORTED_DAYS:
            days = settings.BACKTEST_DEFAULT_DAYS
        logger.info(f"Backtest start: {days}d strategy={strategy}")

        if trades is None:
            # No historical feed wired yet – return empty with note
            return BacktestResult(
                period_days=days,
                notes=(
                    "Historical OHLCV/trade feed not connected. "
                    "Pass trades=[] of {pnl_usd} or integrate Birdeye OHLCV loader."
                ),
            )

        result = self.compute_metrics(trades, initial_capital)
        result.period_days = days
        result.notes = f"strategy={strategy}"
        return result
