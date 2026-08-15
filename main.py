"""Meme Coin Auto Trading Bot – extended with AI, Smart Money, Whale, MEV, Admin."""
from __future__ import annotations

import asyncio
import signal
from utils.logger import logger
from config.settings import settings
from risk.manager import RiskManager
from scanner.new_pairs import NewPairsScanner
from telegram.bot import TelegramBotService
from buy.executor import BuyExecutor
from sell.monitor import PositionMonitor
from buy.jupiter import JupiterSwap
from wallet.rpc import SolanaRPC
from wallet.keypair import load_keypair, get_pubkey

# New modules
from ai_engine.scorer import AIScorer
from ai_engine.learner import TradeLearner
from smart_money.tracker import SmartMoneyTracker
from whale_tracking.monitor import WhaleMonitor
from mev_protection.protector import MEVProtector
from blacklist.manager import BlacklistManager
from advanced_risk.manager import AdvancedRiskManager
from portfolio.manager import PortfolioManager
from notifications.service import NotificationService
from monitoring.health import HealthMonitor
from filters.pipeline import FilterPipeline
from social_intelligence.analyzer import SocialAnalyzer
from admin_panel.app import create_admin_app
from utils.cleanup import cleaner


class MemeBot:
    def __init__(self):
        self.rpc = SolanaRPC()
        self.risk = RiskManager()
        self.jupiter = JupiterSwap(self.rpc)
        self.telegram = TelegramBotService(self.risk)

        # New services
        self.learner = TradeLearner()
        self.ai_scorer = AIScorer(custom_weights=self.learner.get_weights())
        self.smart_money = SmartMoneyTracker()
        self.whale = WhaleMonitor()
        self.social = SocialAnalyzer()
        self.mev = MEVProtector()
        self.blacklist = BlacklistManager()
        self.advanced_risk = AdvancedRiskManager(self.risk)
        self.portfolio = PortfolioManager(self.risk)
        self.notifications = NotificationService(telegram_bot=self.telegram)
        self.health = HealthMonitor(rpc=self.rpc)
        # Ma'lumotlarni tozalash + real hamyon sinxroni
        cleaner.attach(risk=self.risk, rpc=self.rpc)
        self.cleaner = cleaner
        self.telegram.cleaner = cleaner

        self.pipeline = FilterPipeline(
            blacklist=self.blacklist,
            ai_scorer=self.ai_scorer,
            smart_money=self.smart_money,
            whale_monitor=self.whale,
            social=self.social,
        )

        self.buy_executor = BuyExecutor(
            risk=self.risk,
            jupiter=self.jupiter,
            rpc=self.rpc,
            telegram=self.telegram,
            advanced_risk=self.advanced_risk,
            mev=self.mev,
            portfolio=self.portfolio,
            notifications=self.notifications,
        )
        self.monitor = PositionMonitor(
            risk=self.risk,
            jupiter=self.jupiter,
            rpc=self.rpc,
            telegram=self.telegram,
            advanced_risk=self.advanced_risk,
            learner=self.learner,
            notifications=self.notifications,
        )
        self.telegram.monitor = self.monitor
        self.scanner = NewPairsScanner(
            on_passed=self._on_token_passed,
            pipeline=self.pipeline,
        )
        self._tasks: list[asyncio.Task] = []
        self._admin_server = None

    async def _on_token_passed(self, token_data: dict):
        if not await self.risk.is_bot_running():
            return
        await self.buy_executor.try_buy(token_data)

    async def start(self):
        logger.info("=" * 60)
        logger.info("Solana Mem Coin Auto Trading Bot (Extended)")
        logger.info(f"  PAPER_TRADING : {settings.PAPER_TRADING}")
        logger.info(f"  Trade amount  : ${settings.TRADE_AMOUNT_USD}")
        logger.info(f"  Max positions : {settings.MAX_OPEN_POSITIONS}")
        logger.info(
            f"  SL / TP / Trail: {settings.STOP_LOSS_PCT*100:.0f}% / "
            f"{settings.TAKE_PROFIT_PCT*100:.0f}% / {settings.TRAILING_STOP_PCT*100:.0f}%"
        )
        logger.info(f"  Max daily loss: ${settings.MAX_DAILY_LOSS_USD}")
        logger.info(f"  AI Engine     : {settings.AI_ENABLED} (min score {settings.AI_MIN_SCORE})")
        logger.info(f"  Smart Money   : {settings.SMART_MONEY_ENABLED}")
        logger.info(f"  Whale Track   : {settings.WHALE_TRACKING_ENABLED}")
        logger.info(f"  MEV Protect   : {settings.MEV_PROTECTION_ENABLED}")
        logger.info(f"  Auto Blacklist: {settings.AUTO_BLACKLIST_ENABLED}")
        pk = get_pubkey()
        if pk:
            logger.info(f"  Wallet        : {pk[:8]}...{pk[-6:]}")
        else:
            logger.warning("  Wallet        : PRIVATE_KEY yo'q (faqat paper ishlaydi)")
        logger.info("=" * 60)

        await self.risk.connect()
        await self.risk.set_bot_running(True)

        # Start oldidan ma'lumotlarni tozalash / on-chain sinxronlash
        # (ghost pozitsiyalar, eskirgan cooldown, scanner cache)
        try:
            cleanup_report = await self.cleaner.full_cleanup(
                reconcile=True,
                clear_cooldowns=False,  # faqat eskirganlar – start da barchasini o'chirmaymiz
                clear_processed=False,
                reset_daily_loss=False,
                clear_history=False,
                clear_positions=False,
            )
            # Faqat muddati o'tgan cooldownlar
            await self.cleaner.clear_expired_cooldowns()
            removed = len((cleanup_report.get("reconcile") or {}).get("removed") or [])
            synced = len((cleanup_report.get("reconcile") or {}).get("synced") or [])
            if removed or synced:
                logger.info(
                    f"Start cleanup: ghost={removed}, synced={synced}"
                )
        except Exception as e:
            logger.warning(f"Start cleanup xato (davom etiladi): {e}")

        await self.telegram.start()

        scan_task = asyncio.create_task(
            self.scanner.run_loop(interval_sec=settings.SCANNER_INTERVAL_SEC)
        )
        self._tasks.append(scan_task)

        mon_task = asyncio.create_task(self.monitor.run_loop())
        self._tasks.append(mon_task)

        health_task = asyncio.create_task(self.health.run_loop())
        self._tasks.append(health_task)

        try:
            import os
            import uvicorn
            # Railway / Render / Heroku set $PORT – use it so public URL works
            port = int(os.environ.get("PORT", settings.ADMIN_API_PORT))
            host = settings.ADMIN_API_HOST or "0.0.0.0"
            app = create_admin_app(bot_ref=self)
            config = uvicorn.Config(
                app,
                host=host,
                port=port,
                log_level="warning",
            )
            server = uvicorn.Server(config)
            admin_task = asyncio.create_task(server.serve())
            self._tasks.append(admin_task)
            self._admin_server = server
            logger.info(f"Admin API: http://{host}:{port}")
        except Exception as e:
            logger.warning(f"Admin API ishga tushmadi: {e}")

        logger.info("Bot ishga tushdi. Ctrl+C bilan to'xtating.")
        if settings.PAPER_TRADING:
            logger.info("⚠️  PAPER MODE – real tranzaksiya yuborilmaydi.")

        try:
            await asyncio.gather(*self._tasks)
        except asyncio.CancelledError:
            pass

    async def shutdown(self):
        logger.info("Bot to'xtatilmoqda...")
        self.scanner.stop()
        self.monitor.stop()
        self.health.stop()
        await self.risk.set_bot_running(False)
        for t in self._tasks:
            t.cancel()
        if self._admin_server:
            self._admin_server.should_exit = True
        await self.telegram.stop()
        await self.risk.close()
        await self.rpc.close()

        # Persistent httpx clients (BirdeyeClient / XApiClient keep one alive per instance)
        for obj in (
            getattr(self.scanner, "birdeye", None),
            getattr(self.monitor, "birdeye", None),
            getattr(self.jupiter, "_sol_price_client", None),
            self.social,
        ):
            if obj is not None:
                try:
                    await obj.close()
                except Exception as e:
                    logger.debug(f"Birdeye client yopishda xato: {e}")

        logger.info("Bot to'xtatildi.")


async def main():
    bot = MemeBot()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, lambda: asyncio.create_task(bot.shutdown()))
        except NotImplementedError:
            pass

    try:
        await bot.start()
    except KeyboardInterrupt:
        await bot.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
