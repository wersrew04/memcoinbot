"""
Pozitsiya monitori — TP, SL, Trailing Stop.
Paper rejim: narx simulyatsiya.
Live rejim : Jupiter sell → blockchain.
"""
from __future__ import annotations
import asyncio
import aiohttp
from typing import Dict, Optional
from utils.logger import logger
from utils.helpers import safe_float, pnl_percent, pnl_usd, net_pnl_usd, net_pnl_percent, roundtrip_fee_usd, utc_now
from utils.history import history
from config.settings import settings


class PositionMonitor:
    def __init__(self, risk_manager, tg_notifier=None):
        self.risk = risk_manager
        self.tg = tg_notifier
        self._session: Optional[aiohttp.ClientSession] = None

    def set_session(self, session: aiohttp.ClientSession):
        self._session = session

    # ─────────────── NARX OLISH ───────────────

    async def get_current_price(self, token: str) -> float:
        """DexScreener dan joriy narxni olish."""
        if not self._session:
            return 0.0
        try:
            url = "https://api.dexscreener.com/latest/dex/tokens/{}".format(token)
            async with self._session.get(
                url, timeout=aiohttp.ClientTimeout(total=8)
            ) as r:
                if r.status != 200:
                    return 0.0
                data = await r.json()
                pairs = data.get("pairs") or []
                if not pairs:
                    return 0.0
                # Eng ko'p likvidlikka ega juftlikni olish
                best = sorted(
                    pairs,
                    key=lambda p: safe_float((p.get("liquidity") or {}).get("usd")),
                    reverse=True
                )
                return safe_float(best[0].get("priceUsd"))
        except Exception:
            return 0.0

    # ─────────────── ASOSIY TSIKL ───────────────

    async def check_positions(self):
        """Barcha ochiq pozitsiyalarni tekshirish."""
        positions = await self.risk.get_open_positions()
        if not positions:
            return
        tasks = [self._check_one(token, pos) for token, pos in positions.items()]
        await asyncio.gather(*tasks, return_exceptions=True)

    async def _check_one(self, token: str, pos: Dict):
        price = await self.get_current_price(token)
        if price <= 0:
            return

        await self.risk.update_position(token, {"current_price": price})

        entry = safe_float(pos.get("entry_price"))
        if entry <= 0:
            return

        amount_usd = safe_float(pos.get("amount_usd"))
        symbol = pos.get("symbol", token[:8])
        # Sof % (komissiya ayirilgan) — TP/SL shu asosda
        pnl_pct = net_pnl_percent(amount_usd, entry, price)

        # Trailing high yangilash
        high_price = safe_float(pos.get("high_price", entry))
        if price > high_price:
            high_price = price
            await self.risk.update_position(token, {"high_price": price})

        # Qisman TP (partial take profit)
        if settings.PARTIAL_TP_ENABLED and not pos.get("partial_tp_done"):
            if pnl_pct >= settings.PARTIAL_TP_TRIGGER_PCT * 100:
                await self._partial_tp(token, pos, price)
                await self.risk.update_position(token, {"partial_tp_done": True})

        # Take Profit
        if pnl_pct >= settings.TAKE_PROFIT_PCT * 100:
            await self.close_position(token, pos, "take_profit", price)
            return

        # Trailing Stop Loss
        if settings.TRAILING_STOP_PCT > 0:
            trail_trigger = high_price * (1 - settings.TRAILING_STOP_PCT)
            if price <= trail_trigger and high_price > entry * 1.02:
                await self.close_position(token, pos, "trailing_stop", price)
                return

        # Stop Loss
        if settings.STOP_LOSS_PCT > 0 and pnl_pct <= -settings.STOP_LOSS_PCT * 100:
            await self.close_position(token, pos, "stop_loss", price)
            return

    # ─────────────── YOPISH ───────────────

    async def close_position(
        self, token: str, pos: Dict, reason: str, price: float
    ):
        """Pozitsiyani yopish — paper yoki live."""
        symbol = pos.get("symbol", token[:8])
        entry = safe_float(pos.get("entry_price"))
        amount_usd = safe_float(pos.get("amount_usd"))
        is_paper = pos.get("paper", True)

        # Taxminiy PnL (bozor narxi). Live da keyinroq haqiqiy SOL bilan qayta hisoblanadi.
        fee = roundtrip_fee_usd(amount_usd)
        gross_usd = pnl_usd(amount_usd, entry, price)
        pnl_usd_val = gross_usd - fee
        pnl_pct_val = (pnl_usd_val / amount_usd * 100.0) if amount_usd > 0 else 0.0

        sell_ok = True
        tx_hash = "PAPER"
        sol_received = 0.0

        # Live sotish
        if not is_paper and not settings.PAPER_TRADING:
            sell_ok, tx_hash, sol_received = await self._live_sell(token, pos, symbol)
            if not sell_ok:
                logger.error("[SELL FAIL] {} — qayta uriniladi keyingi siklda".format(symbol))
                return  # Pozitsiyani ochiq qoldirish, keyingi siklda qayta urinish
            # Haqiqiy PnL: olingan SOL * narx - sarflangan USD
            try:
                from wallet.keypair import get_sol_price_usd
                sol_px = await get_sol_price_usd(self._session) if self._session else 0.0
                if sol_px <= 0:
                    sol_px = 150.0
                sol_spent = safe_float(pos.get("sol_spent"))
                if sol_spent <= 0 and amount_usd > 0 and sol_px > 0:
                    sol_spent = amount_usd / sol_px
                if sol_received > 0:
                    received_usd = sol_received * sol_px
                    spent_usd = sol_spent * sol_px if sol_spent > 0 else amount_usd
                    pnl_usd_val = received_usd - spent_usd
                    pnl_pct_val = (pnl_usd_val / spent_usd * 100.0) if spent_usd > 0 else 0.0
                    # Chiqish narxini ham yangilash
                    ui = safe_float(pos.get("tokens_ui"))
                    if ui <= 0 and safe_float(pos.get("tokens_amount")) > 0:
                        dec = int(pos.get("token_decimals") or 6)
                        ui = safe_float(pos.get("tokens_amount")) / (10 ** dec)
                    if ui > 0 and received_usd > 0:
                        price = received_usd / ui
            except Exception as e:
                logger.debug("live PnL qayta hisoblash: %s", e)

        # Pozitsiyani bazadan o'chirish
        closed_pos = await self.risk.close_position(token, pnl_usd_val)
        if closed_pos is None:
            return

        # Tarix
        history.add_trade(
            symbol=symbol, token=token,
            pnl_usd=pnl_usd_val, pnl_pct=pnl_pct_val,
            reason=reason,
            ai_score=pos.get("ai_score"),
            ai_breakdown=pos.get("ai_breakdown"),
            paper=is_paper,
        )

        # Learner ni yangilash
        try:
            from ai_engine.learner import TradeLearner
            pass  # main.py da learner.record_trade chaqiriladi
        except Exception:
            pass

        # Bildirishnoma
        emoji = "✅" if pnl_usd_val >= 0 else "❌"
        reason_labels = {
            "take_profit": "Take Profit 🎯",
            "trailing_stop": "Trailing Stop 📉",
            "stop_loss": "Stop Loss 🛑",
            "admin_force": "Admin yopdi 👤",
            "partial_tp": "Qisman TP",
        }
        reason_text = reason_labels.get(reason, reason)

        tx_line = ""
        if tx_hash and not tx_hash.startswith("PAPER"):
            tx_line = "\n🔗 TX: <code>{}</code>".format(tx_hash[:20] + "...")

        msg = (
            "{} <b>Pozitsiya yopildi</b>\n\n"
            "🪙 <b>{}</b>\n"
            "📋 Sabab: <b>{}</b>\n"
            "💵 PnL: <b>${:+.2f} ({:+.1f}%)</b>\n"
            "💰 Kapital: ${:.2f}\n"
            "📈 Kirish: ${:.10f}\n"
            "📉 Chiqish: ${:.10f}{}\n"
            "{}"
        ).format(
            emoji, symbol, reason_text,
            pnl_usd_val, pnl_pct_val,
            amount_usd,
            entry, price, tx_line,
            "PAPER" if is_paper else "LIVE"
        )

        logger.info("[SELL] {} {} PnL=${:+.2f} ({:+.1f}%)".format(
            symbol, reason, pnl_usd_val, pnl_pct_val
        ))

        if self.tg and settings.NOTIFY_TELEGRAM and settings.NOTIFY_ON_SELL:
            try:
                await self.tg.send_message(msg)
            except Exception:
                pass

    async def _live_sell(
        self, token: str, pos: Dict, symbol: str
    ):
        """Live rejim: token raw miqdorini olib, Jupiter orqali sotish."""
        from sell.jupiter_sell import execute_sell, get_token_raw_amount
        from wallet.keypair import get_pubkey

        owner = get_pubkey()
        raw_amount = pos.get("tokens_amount", 0)

        # Agar raw_amount saqlangan bo'lsa — to'g'ridan-to'g'ri ishlatamiz
        # Aks holda blockchain dan o'qiymiz
        if not raw_amount or raw_amount < 1:
            raw_amount = await get_token_raw_amount(self._session, token, owner)

        if not raw_amount:
            logger.warning("[LIVE SELL] {} uchun token topilmadi".format(symbol))
            return False, "", 0.0

        ok, sig, sol = await execute_sell(
            self._session, token, symbol, int(raw_amount)
        )
        return ok, sig, sol

    async def _partial_tp(self, token: str, pos: Dict, price: float):
        """Qisman TP — pozitsiyaning 50% ni yopish."""
        symbol = pos.get("symbol", token[:8])
        amount_usd = safe_float(pos.get("amount_usd"))
        entry = safe_float(pos.get("entry_price"))
        is_paper = pos.get("paper", True)

        sell_amount = amount_usd * settings.PARTIAL_TP_PCT
        pnl_pct_val = pnl_percent(entry, price)
        pnl_usd_val = pnl_usd(sell_amount, entry, price)

        if not is_paper and not settings.PAPER_TRADING:
            raw = int((pos.get("tokens_amount") or 0) * settings.PARTIAL_TP_PCT)
            if raw > 0:
                await self._live_sell_partial(token, symbol, raw)

        # Pozitsiya miqdorini kamaytirish
        new_amount = amount_usd * (1 - settings.PARTIAL_TP_PCT)
        new_tokens_amount = (pos.get("tokens_amount") or 0) * (1 - settings.PARTIAL_TP_PCT)
        await self.risk.update_position(token, {
            "amount_usd": new_amount,
            "tokens_amount": new_tokens_amount
        })

        logger.info("[PARTIAL TP] {} ${:+.2f} ({:+.1f}%)".format(
            symbol, pnl_usd_val, pnl_pct_val
        ))

        if self.tg and settings.NOTIFY_TELEGRAM:
            await self.tg.send_message(
                "🎯 <b>Qisman TP: {}</b>\n"
                "Miqdorning {:.0f}% sotildi\n"
                "PnL: ${:+.2f} ({:+.1f}%)".format(
                    symbol, settings.PARTIAL_TP_PCT * 100,
                    pnl_usd_val, pnl_pct_val
                )
            )

    async def _live_sell_partial(self, token: str, symbol: str, raw_amount: int):
        from sell.jupiter_sell import execute_sell
        await execute_sell(self._session, token, symbol, raw_amount)

    async def force_sell_mint(
        self,
        token: str,
        reason: str = "admin_force",
        symbol: str = "",
        amount_usd: float = 0.0,
        entry_price: float = 0.0,
        current_price: float = 0.0,
        tokens_amount: int = 0,
        paper: bool = False,
    ):
        """
        Bot kuzatayotgan yoki wallet-only tokenni majburan sotish.
        Risk managerda pozitsiya bo'lmasa ham on-chain dan sotadi.
        """
        positions = await self.risk.get_open_positions()
        if token in positions:
            pos = positions[token]
            price = current_price or await self.get_current_price(token) or float(pos.get("current_price") or pos.get("entry_price") or 0)
            await self.close_position(token, pos, reason, price)
            return True, "Bot pozitsiyasi yopildi"

        # Wallet-only: on-chain sotish
        symbol = symbol or token[:8]
        price = current_price or await self.get_current_price(token) or 0.0
        is_paper = paper or settings.PAPER_TRADING

        if is_paper:
            # Paper: faqat risk dan o'chirish (yo'q bo'lsa hech narsa)
            history.add_trade(
                symbol=symbol, token=token,
                pnl_usd=0.0, pnl_pct=0.0,
                reason=reason, paper=True,
            )
            if self.tg and settings.NOTIFY_TELEGRAM:
                try:
                    await self.tg.send_message(
                        "👤 <b>Wallet token yopildi (PAPER)</b>\n\n🪙 <b>{}</b>\n<code>{}</code>".format(
                            symbol, token[:20] + "..."
                        )
                    )
                except Exception:
                    pass
            return True, "PAPER — wallet token belgilandi"

        from sell.jupiter_sell import execute_sell, get_token_raw_amount
        from wallet.keypair import get_pubkey

        owner = get_pubkey()
        raw = tokens_amount or 0
        if not raw or raw < 1:
            raw = await get_token_raw_amount(self._session, token, owner)
        if not raw:
            return False, "Hamyonda token topilmadi (balans 0)"

        ok, sig, sol = await execute_sell(self._session, token, symbol, int(raw))
        if not ok:
            return False, "Jupiter sell muvaffaqiyatsiz"

        # Agar risk da bor edi — o'chirish
        try:
            await self.risk.close_position(token, 0.0)
        except Exception:
            pass

        history.add_trade(
            symbol=symbol, token=token,
            pnl_usd=0.0, pnl_pct=0.0,
            reason=reason, paper=False,
        )
        if self.tg and settings.NOTIFY_TELEGRAM:
            try:
                await self.tg.send_message(
                    "✅ <b>Wallet token sotildi</b>\n\n"
                    "🪙 <b>{}</b>\n"
                    "💎 ~{:.6f} SOL\n"
                    "🔗 TX: <code>{}</code>".format(
                        symbol, sol or 0.0, (sig or "")[:24] + "..."
                    )
                )
            except Exception:
                pass
        logger.info("[FORCE SELL] {} tx={}...".format(symbol, (sig or "")[:20]))
        return True, "Sotildi: {}".format((sig or "")[:20])

