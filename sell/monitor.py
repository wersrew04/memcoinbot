"""Ochiq pozitsiyalarni monitoring – TP / SL / trailing stop."""
from __future__ import annotations

import asyncio
from typing import Any, Dict, Optional
from utils.logger import logger
from utils.helpers import utc_now, safe_float, percent_change
from config.settings import settings
from risk.manager import RiskManager
from buy.jupiter import JupiterSwap
from wallet.keypair import load_keypair
from wallet.rpc import SolanaRPC
from scanner.birdeye import BirdeyeClient
from scanner.dexscreener import DexScreenerClient
from utils.history import history


class PositionMonitor:
    def __init__(
        self,
        risk: RiskManager,
        jupiter: Optional[JupiterSwap] = None,
        rpc: Optional[SolanaRPC] = None,
        telegram=None,
        advanced_risk=None,
        learner=None,
        notifications=None,
    ):
        self.risk = risk
        self.rpc = rpc or SolanaRPC()
        self.jupiter = jupiter or JupiterSwap(self.rpc)
        self.telegram = telegram
        self.advanced_risk = advanced_risk
        self.learner = learner
        self.notifications = notifications
        self.birdeye = BirdeyeClient()
        self.dex = DexScreenerClient()
        self.keypair = load_keypair()
        self.running = False

    async def get_current_price(self, token: str) -> float:
        """Narx – avval Birdeye, keyin DexScreener."""
        try:
            p = await self.birdeye.get_price(token)
            if p and p > 0:
                return p
        except Exception:
            pass
        try:
            pairs = await self.dex.get_token_pairs(token)
            if pairs:
                best = max(pairs, key=lambda x: safe_float((x.get("liquidity") or {}).get("usd")))
                return safe_float(best.get("priceUsd"))
        except Exception:
            pass
        return 0.0

    def _should_exit(
        self, pos: Dict[str, Any], current_price: float
    ) -> tuple[bool, str]:
        entry = safe_float(pos.get("entry_price"))
        if entry <= 0 or current_price <= 0:
            return False, ""

        # Update highest for trailing
        highest = max(safe_float(pos.get("highest_price")), current_price)
        pos["highest_price"] = highest

        pnl_pct = percent_change(entry, current_price)

        # Hard stop loss — faqat STOP_LOSS_PCT > 0 bo'lsa ishlaydi
        sl = safe_float(pos.get("stop_loss"))
        if settings.STOP_LOSS_PCT > 0 and sl > 0 and current_price <= sl:
            return True, "stop_loss"

        # Take profit — faqat TAKE_PROFIT_PCT > 0 bo'lsa
        tp = safe_float(pos.get("take_profit"))
        if settings.TAKE_PROFIT_PCT > 0 and tp > 0 and current_price >= tp:
            return True, "take_profit"

        # Trailing stop (from highest)
        trail_pct = safe_float(pos.get("trailing_stop_pct"))
        if trail_pct <= 0:
            trail_pct = settings.TRAILING_STOP_PCT
        if highest > entry and trail_pct > 0:
            trail_price = highest * (1 - trail_pct)
            if current_price <= trail_price:
                return True, "trailing_stop"

        return False, ""

    async def close_position(
        self, token: str, pos: Dict[str, Any], reason: str, current_price: float
    ) -> bool:
        symbol = pos.get("symbol", token[:8])
        entry = safe_float(pos.get("entry_price"))
        amount_usd = safe_float(pos.get("amount_usd"))
        tokens_raw = int(pos.get("tokens_raw") or 0)
        decimals = int(pos.get("decimals") or 6)

        if tokens_raw <= 0 and pos.get("tokens"):
            tokens_raw = int(float(pos["tokens"]) * (10 ** decimals))

        kp = load_keypair()
        if not kp:
            if settings.PAPER_TRADING:
                from solders.keypair import Keypair
                kp = Keypair()
            else:
                logger.error(f"SELL FAILED {symbol}: Keypair yo'q va PAPER_TRADING=False")
                history.add_event("error", f"Sell failed {symbol}: Keypair yo'q va PAPER_TRADING=False")
                return False

        # Live rejimda walletdagi haqiqiy balansni tekshiramiz (farqlarni tuzatish uchun)
        if not settings.PAPER_TRADING:
            try:
                real_balance = await self.rpc.get_token_balance(str(kp.pubkey()), token)
                if real_balance > 0:
                    tokens_raw = int(real_balance * (10 ** decimals))
                    logger.info(f"Haqiqiy hamyon balansi {symbol} uchun: {real_balance} ({tokens_raw} raw)")
            except Exception as e:
                logger.warning(f"Hamyon balansini olishda xato {symbol}: {e}")

        expected_usd = amount_usd * (current_price / entry) if entry > 0 else amount_usd

        max_attempts = max(1, int(getattr(settings, "SELL_RETRY_ATTEMPTS", 3)))
        success, result = False, {}
        for attempt in range(1, max_attempts + 1):
            success, result = await self.jupiter.sell_token(
                token_mint=token,
                token_amount_raw=tokens_raw or 1,
                keypair=kp,
                token_decimals=decimals,
                expected_usd=expected_usd,
            )
            if success:
                break
            err = str(result.get("error") or "")
            logger.warning(f"SELL attempt {attempt}/{max_attempts} {symbol}: {err}")
            if attempt < max_attempts:
                await asyncio.sleep(1.5 * attempt)

        # Live rejimda sell muvaffaqiyatsiz bo'lsa pozitsiyani o'chirmaymiz
        if not success and not settings.PAPER_TRADING:
            logger.error(
                f"SELL FAILED {symbol}: {result.get('error')} – pozitsiya saqlanadi"
            )
            history.add_event("error", f"Sell failed {symbol}: {result.get('error')}")
            return False

        pnl_usd = 0.0
        pnl_pct = 0.0
        if entry > 0 and current_price > 0:
            pnl_pct = percent_change(entry, current_price) * 100
            pnl_usd = amount_usd * (current_price / entry - 1.0)
        elif result.get("usd_received"):
            pnl_usd = safe_float(result["usd_received"]) - amount_usd
            pnl_pct = (pnl_usd / amount_usd * 100) if amount_usd else 0

        # Risk update
        await self.risk.add_realized_pnl(pnl_usd)
        await self.risk.remove_position(token)
        await self.risk.set_cooldown(token)

        # Advanced risk (consecutive losses / daily trades)
        if self.advanced_risk:
            self.advanced_risk.record_trade_result(pnl_usd)

        # AI learner – closed trade outcome
        if self.learner:
            try:
                factors = pos.get("ai_factors") or {}
                score = safe_float(pos.get("ai_score"))
                self.learner.record_trade(
                    token=token,
                    factors=factors,
                    score=score,
                    pnl_usd=pnl_usd,
                    pnl_pct=pnl_pct,
                    reason=reason,
                )
            except Exception as e:
                logger.debug(f"Learner record failed: {e}")

        history.add_trade({
            "token": token,
            "symbol": symbol,
            "pnl_usd": pnl_usd,
            "pnl_pct": pnl_pct,
            "reason": reason,
            "entry_price": entry,
            "exit_price": current_price,
            "amount_usd": amount_usd,
            "ai_score": safe_float(pos.get("ai_score")),
            "tx": result.get("tx") or "",
            "paper": settings.PAPER_TRADING,
        })
        history.add_event("trade", f"SELL {symbol} {pnl_pct:+.1f}% ({reason})")

        logger.info(
            f"{'🟢' if pnl_usd >= 0 else '🔴'} SELL {symbol} | {reason} | "
            f"PnL ${pnl_usd:+.2f} ({pnl_pct:+.1f}%) | "
            f"{'PAPER' if settings.PAPER_TRADING else result.get('tx')}"
        )

        if self.telegram:
            await self.telegram.notify_trade_close(
                symbol=symbol,
                token=token,
                pnl_usd=pnl_usd,
                pnl_pct=pnl_pct,
                reason=reason,
                tx=result.get("tx") or "",
            )
        if self.notifications:
            await self.notifications.notify_sell(
                symbol=symbol,
                pnl_usd=pnl_usd,
                pnl_pct=pnl_pct,
                reason=reason,
                tx=result.get("tx") or "",
            )

        # Daily limit check
        if await self.risk.is_daily_loss_limit_reached():
            if self.telegram:
                await self.telegram.notify_daily_limit()

        return success

    async def check_once(self):
        positions = await self.risk.get_open_positions()
        if not positions:
            return

        # Live: har ~20 tsiklda ghost pozitsiyalarni (0 balans) tozalash
        if not settings.PAPER_TRADING and not getattr(self, "_reconcile_counter", 0) % 20:
            try:
                from utils.cleanup import cleaner
                if cleaner.risk is None:
                    cleaner.attach(risk=self.risk, rpc=self.rpc)
                await cleaner.reconcile_positions(
                    remove_zero_balance=True, sync_balances=True
                )
            except Exception as e:
                logger.debug(f"Monitor reconcile: {e}")
        self._reconcile_counter = getattr(self, "_reconcile_counter", 0) + 1

        for token, pos in list(positions.items()):
            try:
                price = await self.get_current_price(token)
                if price <= 0:
                    continue

                # Store current price
                await self.risk.update_position(token, {"current_price": price})

                # highest yangilash risk da
                if price > safe_float(pos.get("highest_price")):
                    await self.risk.update_position(token, {"highest_price": price})

                should, reason = self._should_exit(pos, price)
                if should:
                    await self.close_position(token, pos, reason, price)
                else:
                    entry = safe_float(pos.get("entry_price"))
                    pnl = percent_change(entry, price) * 100 if entry else 0
                    logger.debug(
                        f"Hold {pos.get('symbol', token[:6])} @ ${price:.8f} ({pnl:+.1f}%)"
                    )
            except Exception as e:
                logger.error(f"Monitor {token}: {e}")

            await asyncio.sleep(0.2)

    async def run_loop(self, interval_sec: Optional[int] = None):
        interval = interval_sec or settings.POSITION_MONITOR_INTERVAL_SEC
        self.running = True
        logger.info(f"PositionMonitor ishga tushdi (har {interval}s)")
        while self.running:
            try:
                if await self.risk.is_bot_running():
                    await self.check_once()
            except Exception as e:
                logger.exception(f"Monitor loop xato: {e}")
            await asyncio.sleep(interval)

    def stop(self):
        self.running = False
