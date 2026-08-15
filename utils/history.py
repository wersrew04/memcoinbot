"""In-memory + file ring buffers: filter rejections, closed trades, recent events."""
from __future__ import annotations

import json
from collections import deque
from pathlib import Path
from typing import Any, Deque, Dict, List, Optional
from utils.helpers import utc_now, safe_float

DATA_DIR = Path("data")
DATA_DIR.mkdir(parents=True, exist_ok=True)
TRADES_FILE = DATA_DIR / "closed_trades.jsonl"
EVENTS_FILE = DATA_DIR / "events.jsonl"


class HistoryStore:
    def __init__(self, max_rejections: int = 200, max_trades: int = 500, max_events: int = 300):
        self.rejections: Deque[Dict[str, Any]] = deque(maxlen=max_rejections)
        self.trades: Deque[Dict[str, Any]] = deque(maxlen=max_trades)
        self.events: Deque[Dict[str, Any]] = deque(maxlen=max_events)
        self._load_trades()

    def _load_trades(self):
        if not TRADES_FILE.exists():
            return
        try:
            lines = TRADES_FILE.read_text(encoding="utf-8").strip().splitlines()
            for line in lines[-500:]:
                self.trades.append(json.loads(line))
        except Exception:
            pass

    def add_rejection(
        self,
        token: str,
        symbol: str = "",
        reasons: Optional[List[str]] = None,
        stage: str = "filter",
    ):
        entry = {
            "ts": utc_now().isoformat(),
            "token": token,
            "symbol": symbol or token[:8],
            "reasons": reasons or [],
            "stage": stage,
            "last_reason": (reasons or ["unknown"])[-1] if reasons else "unknown",
        }
        self.rejections.appendleft(entry)

    def add_trade(self, trade: Dict[str, Any]):
        trade = dict(trade)
        trade.setdefault("ts", utc_now().isoformat())
        self.trades.appendleft(trade)
        try:
            with TRADES_FILE.open("a", encoding="utf-8") as f:
                f.write(json.dumps(trade, default=str) + "\n")
        except Exception:
            pass

    def add_event(self, level: str, message: str):
        self.events.appendleft({
            "ts": utc_now().isoformat(),
            "level": level,
            "message": message,
        })

    def list_rejections(self, limit: int = 50) -> List[Dict[str, Any]]:
        return list(self.rejections)[:limit]

    def list_trades(self, limit: int = 50) -> List[Dict[str, Any]]:
        return list(self.trades)[:limit]

    def list_events(self, limit: int = 50) -> List[Dict[str, Any]]:
        return list(self.events)[:limit]

    def pnl_summary(self) -> Dict[str, Any]:
        trades = list(self.trades)
        if not trades:
            return {
                "total_trades": 0,
                "wins": 0,
                "losses": 0,
                "win_rate": 0.0,
                "net_pnl": 0.0,
                "profit": 0.0,
                "loss": 0.0,
                "avg_pnl": 0.0,
                "best": 0.0,
                "worst": 0.0,
            }
        pnls = [safe_float(t.get("pnl_usd")) for t in trades]
        wins = [p for p in pnls if p > 0]
        losses = [p for p in pnls if p < 0]
        net = sum(pnls)
        n = len(pnls)
        return {
            "total_trades": n,
            "wins": len(wins),
            "losses": len(losses),
            "win_rate": round(len(wins) / n * 100, 1) if n else 0.0,
            "net_pnl": round(net, 2),
            "profit": round(sum(wins), 2),
            "loss": round(abs(sum(losses)), 2),
            "avg_pnl": round(net / n, 2) if n else 0.0,
            "best": round(max(pnls), 2),
            "worst": round(min(pnls), 2),
        }


# Singleton – bot va admin bir xil store ishlatadi
history = HistoryStore()
