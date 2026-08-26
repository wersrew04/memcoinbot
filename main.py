"""
MemeBot Pro — asosiy ishga tushirish fayli.
Paper va Live rejim to'liq qo'llab-quvvatlanadi.
"""
from __future__ import annotations
import asyncio
import os
import signal
import sys
from pathlib import Path
from typing import Optional

Path("data").mkdir(exist_ok=True)
Path("logs").mkdir(exist_ok=True)

from utils.logger import logger
from config.settings import settings
from risk.manager import RiskManager
from advanced_risk.manager import AdvancedRiskManager
from blacklist.manager import BlacklistManager
from ai_engine.scorer import AIScorer
from ai_engine.learner import TradeLearner
from scanner.dexscreener import fetch_new_pairs
from filters.pipeline import FilterPipeline
from buy.executor import execute_buy
from sell.monitor import PositionMonitor
from telegram.notifier import TelegramNotifier
from telegram.bot import TelegramBot
from utils.history import history
import aiohttp


class MemeBot:
    def __init__(self):
        self.risk = RiskManager()
        self.advanced_risk = AdvancedRiskManager(self.risk)
        self.blacklist = BlacklistManager()
        self.scorer = AIScorer()
        self.learner = TradeLearner()
        self.filter_pipeline = FilterPipeline(self.blacklist)
        self.monitor = PositionMonitor(self.risk)
        self.notifier = TelegramNotifier()
        self.tg_bot = TelegramBot(bot_ref=self)
        self.monitor.tg = self.notifier
        self._session: Optional[aiohttp.ClientSession] = None
        self._tasks = []
        self._shutdown_event = asyncio.Event()

    # ─────────────── ISHGA TUSHIRISH ───────────────

    async def start(self):
        logger.info("=" * 55)
        logger.info("  MemeBot Pro  |  Solana Memecoin Trader")
        logger.info("=" * 55)
        logger.info("Rejim    : {}".format("PAPER (simulyatsiya)" if settings.PAPER_TRADING else "LIVE ⚠️"))
        logger.info("Trade    : ${:.2f}".format(settings.TRADE_AMOUNT_USD))
        logger.info("TP / SL  : {:.0f}% / {:.0f}%".format(
            settings.TAKE_PROFIT_PCT * 100, settings.STOP_LOSS_PCT * 100
        ))
        logger.info("Trailing : {:.0f}%".format(settings.TRAILING_STOP_PCT * 100))
        logger.info("AI score : {:.0f}+".format(settings.AI_MIN_SCORE))
        logger.info("=" * 55)

        connector = aiohttp.TCPConnector(limit=60, ttl_dns_cache=300, ssl=False)
        timeout = aiohttp.ClientTimeout(total=30, connect=10)
        self._session = aiohttp.ClientSession(connector=connector, timeout=timeout)

        self.monitor.set_session(self._session)
        self.notifier.set_session(self._session)
        self.tg_bot.set_session(self._session)

        settings.BOT_RUNNING = True

        # Diskdan tiklangan pozitsiyalar bo'lsa — darhol joriy narxni yangilaymiz,
        # shunda web panel va /positions to'g'ri ko'rsatadi, monitor esa
        # TP/SL/trailing ni davom ettiradi.
        restored = await self.risk.get_open_positions()
        restored_info = ""
        if restored:
            async def _refresh(tok):
                try:
                    price = await self.monitor.get_current_price(tok)
                    if price > 0:
                        await self.risk.update_position(tok, {"current_price": price})
                except Exception:
                    pass
            await asyncio.gather(*(_refresh(t) for t in restored.keys()))
            names = ", ".join(p.get("symbol", t[:8]) for t, p in restored.items())
            restored_info = "\n\n♻️ <b>Tiklangan pozitsiyalar ({}):</b> {}".format(
                len(restored), names
            )

        # Hamyon ma'lumotlari
        wallet_info = ""
        if not settings.PAPER_TRADING and settings.PRIVATE_KEY:
            from wallet.keypair import get_pubkey, get_sol_balance
            pubkey = get_pubkey()
            if pubkey:
                sol_bal = await get_sol_balance(self._session, pubkey)
                wallet_info = "\n👛 Hamyon: <code>{}</code>\n💎 SOL: {:.4f}".format(
                    pubkey[:20] + "...", sol_bal
                )

        await self.notifier.send_message(
            "🚀 <b>MemeBot Pro ishga tushdi!</b>\n\n"
            "Mode: <b>{}</b>{}\n"
            "Trade: <b>${:.2f}</b>\n"
            "TP: <b>{:.0f}%</b> | SL: <b>{:.0f}%</b> | Trail: <b>{:.0f}%</b>\n"
            "AI min: <b>{:.0f}</b>\n\n"
            "Buyruqlar:\n"
            "/start /stop /positions /status /stats /wallet /sync_wallet /close"
            "{}".format(
                "PAPER" if settings.PAPER_TRADING else "⚠️ LIVE",
                wallet_info,
                settings.TRADE_AMOUNT_USD,
                settings.TAKE_PROFIT_PCT * 100,
                settings.STOP_LOSS_PCT * 100,
                settings.TRAILING_STOP_PCT * 100,
                settings.AI_MIN_SCORE,
                restored_info,
            )
        )

        # Shutdown signal
        loop = asyncio.get_event_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, self._shutdown_event.set)
            except NotImplementedError:
                pass

        # Vazifalar
        self._tasks = [
            asyncio.create_task(self._scanner_loop(), name="scanner"),
            asyncio.create_task(self._monitor_loop(), name="monitor"),
            asyncio.create_task(self.tg_bot.start_polling(), name="tg_bot"),
            asyncio.create_task(self._start_admin(), name="admin"),
            asyncio.create_task(self._daily_reset_loop(), name="daily_reset"),
        ]

        # Shutdown signalini kutish
        await self._shutdown_event.wait()
        await self.stop()

    async def stop(self):
        logger.info("Bot to'xtatilmoqda...")
        settings.BOT_RUNNING = False

        for t in self._tasks:
            if not t.done():
                t.cancel()

        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)

        if self._session and not self._session.closed:
            await self._session.close()

        try:
            await self.notifier.send_message("⏹ <b>MemeBot Pro to'xtatildi</b>")
        except Exception:
            pass

        logger.info("Bot to'xtatildi. Xayr!")

    # ─────────────── SCANNER LOOP ───────────────

    async def _scanner_loop(self):
        logger.info("[SCANNER] Boshlandi — interval: {}s".format(settings.SCANNER_INTERVAL_SEC))
        await asyncio.sleep(5)   # Boshqa modullarga vaqt berish
        while True:
            try:
                if settings.BOT_RUNNING and not settings.EMERGENCY_STOP:
                    await self._scan_once()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("[SCANNER] Xato: {}".format(e))
                history.add_event("ERROR", "Scanner xato: {}".format(e))
            await asyncio.sleep(settings.SCANNER_INTERVAL_SEC)

    async def _scan_once(self):
        """Bir marta skanerlash tsikli."""
        try:
            pairs = await fetch_new_pairs(
                self._session,
                min_liquidity=settings.MIN_LIQUIDITY_USD
            )
        except Exception as e:
            logger.warning("[SCAN] DexScreener xato: {}".format(e))
            return

        if not pairs:
            return

        logger.info("[SCAN] {} ta juftlik topildi".format(len(pairs)))

        n_risk_skip = 0
        n_filter_fail = 0
        n_ai_fail = 0
        n_buy_attempt = 0

        for pair in pairs:
            token = pair.get("token", "")
            if not token:
                continue

            # Risk tekshiruvi
            ok, reason = await self.advanced_risk.pre_trade_check(
                token, settings.TRADE_AMOUNT_USD
            )
            if not ok:
                n_risk_skip += 1
                logger.info("[SKIP] {} — risk: {}".format(pair.get("symbol", "?"), reason))
                continue

            # Filter pipeline
            passed, reason, enriched = await self.filter_pipeline.run(
                pair, self._session
            )
            if not passed:
                n_filter_fail += 1
                continue

            # AI baholash
            ai_result = self.scorer.score(enriched)
            enriched["ai_score"] = ai_result.score
            enriched["ai_rec"] = ai_result.recommendation.value

            logger.info(
                "[AI] {} score={:.1f} rec={} signals={} warns={}".format(
                    enriched.get("symbol", "?"),
                    ai_result.score,
                    ai_result.recommendation.value,
                    len(ai_result.signals),
                    len(ai_result.warnings),
                )
            )

            # Threshold tekshiruvi
            if not self.scorer.passes_threshold(ai_result):
                n_ai_fail += 1
                history.add_rejection(
                    enriched.get("symbol", "?"), token,
                    "ai", "Score past: {:.1f}".format(ai_result.score)
                )
                logger.info(
                    "[AI FAIL] {} score={:.1f} < min={:.0f}".format(
                        enriched.get("symbol", "?"),
                        ai_result.score,
                        settings.AI_MIN_SCORE,
                    )
                )
                continue

            # Yakuniy scam gate (filter+AI o'tgan bo'lsa ham)
            gate_ok, gate_reason = await self.filter_pipeline.final_scam_gate(
                token, enriched.get("symbol", "?"), self._session, enriched
            )
            if not gate_ok:
                n_filter_fail += 1
                history.add_rejection(
                    enriched.get("symbol", "?"), token, "scam_gate", gate_reason
                )
                logger.warning("[SCAM GATE] {} — {}".format(
                    enriched.get("symbol", "?"), gate_reason
                ))
                continue

            # Xarid
            n_buy_attempt += 1
            await self._execute_trade(token, enriched, ai_result)

            # Har bir juftlik o'rtasida kichik pauza
            await asyncio.sleep(0.5)

        logger.info(
            "[SCAN DONE] juftlik={} | risk_skip={} | filter_fail={} | ai_fail={} | buy_attempt={}".format(
                len(pairs), n_risk_skip, n_filter_fail, n_ai_fail, n_buy_attempt
            )
        )

    # ─────────────── SAVDO BAJARISH ───────────────

    async def _execute_trade(self, token: str, data: dict, ai_result):
        symbol = data.get("symbol", token[:8])
        price = safe_float(data.get("price_usd"))
        amount = settings.TRADE_AMOUNT_USD

        if price <= 0:
            logger.warning("[BUY] {} narxi 0 — o'tkazib yuborildi".format(symbol))
            return

        success, position = await execute_buy(
            token=token,
            symbol=symbol,
            amount_usd=amount,
            current_price=price,
            session=self._session,
            paper=settings.PAPER_TRADING,
        )
        if not success:
            err = position.get("error", "Noma'lum xato")
            logger.warning("[BUY FAIL] {} — {}".format(symbol, err))
            return

        position["ai_score"] = ai_result.score
        position["ai_breakdown"] = ai_result.breakdown
        position["high_price"] = price

        opened = await self.risk.open_position(token, position)
        if not opened:
            logger.warning("[BUY] {} — pozitsiya ochmadi (allaqachon bor?)".format(symbol))
            return

        self.advanced_risk.daily_trades += 1

        # Bildirishnoma
        if settings.NOTIFY_TELEGRAM and settings.NOTIFY_ON_BUY:
            signals_text = ""
            if ai_result.signals:
                signals_text = "\n📋 " + "\n📋 ".join(ai_result.signals[:3])
            warns_text = ""
            if ai_result.warnings:
                warns_text = "\n⚠️ " + "\n⚠️ ".join(ai_result.warnings[:2])

            tx_line = ""
            if not position.get("paper") and position.get("tx_hash"):
                tx_line = "\n🔗 TX: <code>{}</code>".format(
                    position["tx_hash"][:20] + "..."
                )

            await self.notifier.send_message(
                "🟢 <b>XARID: {}</b>\n\n"
                "💰 Miqdor: <b>${:.2f}</b>\n"
                "📈 Narx: <b>${:.10f}</b>\n"
                "🤖 AI: <b>{:.1f}</b> ({})\n"
                "💧 Liq: ${:,.0f}\n"
                "📊 Vol5m: ${:,.0f}\n"
                "👤 Holderlar: {:,}{}{}{}\n"
                "{}".format(
                    symbol,
                    amount, price,
                    ai_result.score, ai_result.recommendation.value,
                    data.get("liquidity_usd", 0),
                    data.get("volume_5m", 0),
                    data.get("holder_count", 0),
                    signals_text,
                    warns_text,
                    tx_line,
                    "PAPER" if settings.PAPER_TRADING else "⚠️ LIVE",
                )
            )

    # ─────────────── MONITOR LOOP ───────────────

    async def _monitor_loop(self):
        logger.info("[MONITOR] Boshlandi — interval: {}s".format(
            settings.POSITION_MONITOR_INTERVAL_SEC
        ))
        while True:
            try:
                if settings.BOT_RUNNING:
                    await self.monitor.check_positions()
                    await self._update_learner()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("[MONITOR] Xato: {}".format(e))
            await asyncio.sleep(settings.POSITION_MONITOR_INTERVAL_SEC)

    async def _update_learner(self):
        """Yopilgan savdolarni learner ga yuborish."""
        trades = history.list_trades(limit=5)
        for trade in trades:
            if trade.get("_learned"):
                continue
            if trade.get("ai_score") is not None:
                try:
                    self.learner.record_trade(
                        symbol=trade.get("symbol", "?"),
                        token=trade.get("token", ""),
                        pnl_pct=trade.get("pnl_pct", 0),
                        score_breakdown=trade.get("ai_breakdown") or {},
                        reason=trade.get("reason", ""),
                    )
                    trade["_learned"] = True
                except Exception:
                    pass
            # Advanced risk ni yangilash
            pnl_usd = trade.get("pnl_usd", 0)
            self.advanced_risk.record_trade_result(pnl_usd)

    # ─────────────── DAILY RESET ───────────────

    async def _daily_reset_loop(self):
        """Har kuni yarim tunda statistikani yangilash."""
        while True:
            try:
                from utils.helpers import utc_now
                now = utc_now()
                # Keyingi yarim tunga qadar necha soniya
                seconds_until_midnight = (
                    (24 - now.hour) * 3600 - now.minute * 60 - now.second
                )
                await asyncio.sleep(seconds_until_midnight)
                from utils.history import reset_today_stats
                try:
                    reset_today_stats()
                except Exception:
                    pass
                await self.risk.reset_daily_loss()
                self.advanced_risk.daily_trades = 0
                self.advanced_risk.consecutive_losses = 0
                self.risk.clear_processed()
                logger.info("Kunlik statistika yangilandi")
                await asyncio.sleep(60)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Daily reset xato: {}".format(e))
                await asyncio.sleep(3600)

    # ─────────────── ADMIN PANEL ───────────────

    async def _start_admin(self):
        try:
            import uvicorn
            from admin_panel.app import create_admin_app
            app = create_admin_app(bot_ref=self)
            port = int(os.environ.get("PORT") or settings.ADMIN_API_PORT)
            config = uvicorn.Config(
                app,
                host=settings.ADMIN_API_HOST,
                port=port,
                log_level="warning",
                access_log=False,
            )
            server = uvicorn.Server(config)
            logger.info("Admin panel: http://{}:{}".format(
                settings.ADMIN_API_HOST, port
            ))
            await server.serve()
        except ImportError:
            logger.warning("uvicorn o'rnatilmagan — admin panel o'chirilgan")
            while True:
                await asyncio.sleep(3600)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error("Admin panel xato: {}".format(e))


def safe_float(val, default=0.0):
    try:
        return float(val) if val is not None else default
    except (TypeError, ValueError):
        return default


# ─────────────── MAIN ───────────────

async def main():
    bot = MemeBot()
    try:
        await bot.start()
    except KeyboardInterrupt:
        logger.info("Foydalanuvchi to'xtatdi (Ctrl+C)")
    except Exception as e:
        logger.exception("Kutilmagan xato: {}".format(e))
    finally:
        if not bot._shutdown_event.is_set():
            bot._shutdown_event.set()


if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())
