"""Telegram bot – start/stop, positions, balance, trade xabarlari. To'liq o'zbek tilida."""
from __future__ import annotations

import asyncio
import html
from typing import Optional, Any
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton
from utils.logger import logger
from config.settings import settings
from risk.manager import RiskManager
from utils.history import history

BTN_START = "▶️ Ishga tushirish"
BTN_STOP = "⏹ To'xtatish"
BTN_POSITIONS = "📊 Pozitsiyalar"
BTN_STATUS = "💰 Holat"
BTN_STATS = "📈 Statistika"
BTN_RESTART = "🔄 Qayta ishga tushirish"
BTN_CLEAN = "🧹 Tozalash"


class TelegramBotService:
    def __init__(self, risk_manager: RiskManager):
        self.token = settings.TELEGRAM_BOT_TOKEN
        self.chat_id = settings.TELEGRAM_CHAT_ID
        self.risk = risk_manager
        self.bot: Optional[Bot] = None
        self.dp: Optional[Dispatcher] = None
        self._task: Optional[asyncio.Task] = None
        self.monitor: Optional[Any] = None
        self.cleaner: Optional[Any] = None

    def _keyboard(self) -> ReplyKeyboardMarkup:
        return ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text=BTN_START), KeyboardButton(text=BTN_STOP)],
                [KeyboardButton(text=BTN_POSITIONS), KeyboardButton(text=BTN_STATUS)],
                [KeyboardButton(text=BTN_STATS), KeyboardButton(text=BTN_RESTART)],
                [KeyboardButton(text=BTN_CLEAN)],
            ],
            resize_keyboard=True,
        )

    async def start(self):
        if not self.token:
            logger.warning("TELEGRAM_BOT_TOKEN yo'q – Telegram o'chirilgan")
            return
        self.bot = Bot(token=self.token)
        self.dp = Dispatcher()
        self._register_handlers()
        self._task = asyncio.create_task(self.dp.start_polling(self.bot))
        logger.info("Telegram bot ishga tushdi")
        await self.send_message(
            "🤖 MemeBot Telegram ishga tushdi.\n"
            "Quyidagi menyudan foydalaning yoki buyruqlar: "
            "/start /stop /positions /status /stats /restart /clean"
        )

    async def stop(self):
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        if self.bot:
            await self.bot.session.close()
        logger.info("Telegram bot to'xtatildi")

    def _register_handlers(self):
        assert self.dp is not None

        @self.dp.message(Command("start"))
        @self.dp.message(F.text == BTN_START)
        async def cmd_start(message: Message):
            if not self._authorized(message):
                return
            await self.risk.set_bot_running(True)
            await message.answer("✅ Bot <b>ishga tushirildi</b>", parse_mode="HTML", reply_markup=self._keyboard())

        @self.dp.message(Command("stop"))
        @self.dp.message(F.text == BTN_STOP)
        async def cmd_stop(message: Message):
            if not self._authorized(message):
                return
            await self.risk.set_bot_running(False)
            await message.answer("🛑 Bot <b>to'xtatildi</b>", parse_mode="HTML", reply_markup=self._keyboard())

        @self.dp.message(Command("positions"))
        @self.dp.message(F.text == BTN_POSITIONS)
        async def cmd_positions(message: Message):
            if not self._authorized(message):
                return
            pos = await self.risk.get_open_positions()
            if not pos:
                await message.answer("Ochiq pozitsiya yo'q.", reply_markup=self._keyboard())
                return

            # Ochiq pozitsiyalar uchun narxlarni parallel ravishda yangilaymiz (agar monitor mavjud bo'lsa)
            if self.monitor:
                async def _update_price(tok: str):
                    try:
                        price = await self.monitor.get_current_price(tok)
                        if price > 0:
                            await self.risk.update_position(tok, {"current_price": price})
                    except Exception:
                        pass
                await asyncio.gather(*(_update_price(tok) for tok in pos.keys()))
                # Qayta o'qiymiz yangilangan narxlar bilan
                pos = await self.risk.get_open_positions()

            lines = []
            for token, p in pos.items():
                entry = float(p.get("entry_price") or 0)
                amount = float(p.get("amount_usd") or 0)
                symbol = p.get("symbol", token[:8])
                price = p.get("current_price")
                
                if price:
                    price_val = float(price)
                    pnl_pct = ((price_val / entry) - 1.0) * 100.0 if entry > 0 else 0.0
                    pnl_usd = amount * (price_val / entry - 1.0) if entry > 0 else 0.0
                    emoji = "🟢" if pnl_pct >= 0 else "🔴"
                    pnl_text = f"{emoji} PnL: ${pnl_usd:+.2f} ({pnl_pct:+.1f}%)"
                    price_text = f"${price_val:.8f}"
                else:
                    pnl_text = "⏳ PnL: kutilmoqda..."
                    price_text = "kutilmoqda..."
                
                lines.append(
                    f"• <b>{html.escape(symbol)}</b>\n"
                    f"  Kirish: ${entry:.8f} | Joriy: {price_text}\n"
                    f"  Hajm: ${amount:.2f} | {pnl_text}\n"
                    f"  Manzil: <code>{html.escape(token)}</code>\n"
                )

            # Xabarni qismlarga bo'lib yuborish (Telegram 4096 belgi limiti tufayli)
            header = f"📊 <b>Ochiq pozitsiyalar ({len(pos)}):</b>\n\n"
            current_chunk = header
            chunks = []
            for line in lines:
                if len(current_chunk) + len(line) + 2 > 4000:
                    chunks.append(current_chunk)
                    current_chunk = ""
                current_chunk += line + "\n"
            if current_chunk:
                chunks.append(current_chunk)

            for i, chunk in enumerate(chunks):
                # Faqat eng oxirgi xabarga keyboardni biriktiramiz
                markup = self._keyboard() if i == len(chunks) - 1 else None
                await message.answer(chunk, parse_mode="HTML", reply_markup=markup)

        @self.dp.message(Command("status"))
        @self.dp.message(F.text == BTN_STATUS)
        async def cmd_status(message: Message):
            if not self._authorized(message):
                return
            summary = await self.risk.get_status_summary()
            text = (
                f"🤖 <b>Bot holati</b>\n"
                f"Ishlayapti: {'✅' if summary['bot_running'] else '🛑'}\n"
                f"Kunlik zarar: ${summary['daily_loss_usd']:.2f} / ${summary['max_daily_loss_usd']:.2f}\n"
                f"Ochiq pozitsiyalar: {summary['open_positions']} / {summary['max_open_positions']}"
            )
            await message.answer(text, parse_mode="HTML", reply_markup=self._keyboard())

        @self.dp.message(Command("stats"))
        @self.dp.message(F.text == BTN_STATS)
        async def cmd_stats(message: Message):
            if not self._authorized(message):
                return
            summary = await self.risk.get_status_summary()
            pnl = history.pnl_summary()
            await message.answer(
                f"📈 <b>Statistika</b>\n"
                f"Ishlayapti: {'✅' if summary['bot_running'] else '🛑'}\n"
                f"Kunlik zarar: ${summary['daily_loss_usd']:.2f} / ${summary['max_daily_loss_usd']:.2f}\n"
                f"Ochiq: {summary['open_positions']} / {summary['max_open_positions']}\n"
                f"Savdolar: {pnl['total_trades']} | Yutuq foizi: {pnl['win_rate']}%\n"
                f"Sof foyda/zarar: ${pnl['net_pnl']:+.2f}",
                parse_mode="HTML",
                reply_markup=self._keyboard(),
            )

        @self.dp.message(Command("restart"))
        @self.dp.message(F.text == BTN_RESTART)
        async def cmd_restart(message: Message):
            if not self._authorized(message):
                return
            await self.risk.set_bot_running(False)
            await asyncio.sleep(1)
            await self.risk.set_bot_running(True)
            await message.answer("🔄 Bot qayta ishga tushirildi", parse_mode="HTML", reply_markup=self._keyboard())

        @self.dp.message(Command("clean"))
        @self.dp.message(Command("tozalash"))
        @self.dp.message(F.text == BTN_CLEAN)
        async def cmd_clean(message: Message):
            """Ghost pozitsiyalar, cooldown, scanner cache tozalash + on-chain sinxron."""
            if not self._authorized(message):
                return
            if not self.cleaner:
                await message.answer(
                    "❌ Tozalash moduli ulanmagan.",
                    reply_markup=self._keyboard(),
                )
                return
            await message.answer("🧹 Tozalanmoqda… biroz kuting.")
            try:
                report = await self.cleaner.full_cleanup(
                    reconcile=True,
                    clear_cooldowns=True,
                    clear_processed=True,
                    reset_daily_loss=False,
                    clear_history=False,
                    clear_positions=False,
                )
                text = self.cleaner.format_report(report)
                await message.answer(text, parse_mode="HTML", reply_markup=self._keyboard())
            except Exception as e:
                logger.exception(f"Telegram /clean xato: {e}")
                await message.answer(
                    f"❌ Tozalash xatosi: {html.escape(str(e))}",
                    parse_mode="HTML",
                    reply_markup=self._keyboard(),
                )

        @self.dp.message(Command("clean_all"))
        async def cmd_clean_all(message: Message):
            """Kuchli tozalash: + kunlik zarar reset + tarix (pozitsiya yozuvlari SAQLANADI)."""
            if not self._authorized(message):
                return
            if not self.cleaner:
                await message.answer("❌ Tozalash moduli ulanmagan.", reply_markup=self._keyboard())
                return
            await message.answer("🧹 Kuchli tozalash…")
            try:
                report = await self.cleaner.full_cleanup(
                    reconcile=True,
                    clear_cooldowns=True,
                    clear_processed=True,
                    reset_daily_loss=True,
                    clear_history=True,
                    clear_positions=False,
                )
                text = self.cleaner.format_report(report)
                await message.answer(text, parse_mode="HTML", reply_markup=self._keyboard())
            except Exception as e:
                logger.exception(f"Telegram /clean_all xato: {e}")
                await message.answer(
                    f"❌ Tozalash xatosi: {html.escape(str(e))}",
                    parse_mode="HTML",
                    reply_markup=self._keyboard(),
                )

    def _authorized(self, message: Message) -> bool:
        if not self.chat_id:
            return True
        return str(message.chat.id) == str(self.chat_id)

    async def send_message(self, text: str, parse_mode: str = "HTML"):
        if not self.bot or not self.chat_id:
            return
        try:
            await self.bot.send_message(chat_id=self.chat_id, text=text, parse_mode=parse_mode)
        except Exception as e:
            logger.error(f"Telegram xabar yuborish xato: {e}")

    async def notify_trade_open(self, symbol: str, token: str, amount_usd: float, price: float, tx: str = ""):
        text = (
            f"🟢 <b>XARID</b>\n"
            f"Token: <code>{html.escape(symbol)}</code>\n"
            f"Manzil: <code>{html.escape(token)}</code>\n"
            f"Miqdor: ${amount_usd:.2f}\n"
            f"Narx: ${price:.8f}\n"
        )
        if tx:
            text += f"Tranzaksiya: <code>{html.escape(tx[:20])}...</code>"
        await self.send_message(text)

    async def notify_trade_close(
        self,
        symbol: str,
        token: str,
        pnl_usd: float,
        pnl_pct: float,
        reason: str,
        tx: str = "",
    ):
        emoji = "🟢" if pnl_usd >= 0 else "🔴"
        text = (
            f"{emoji} <b>SOTISH</b> ({html.escape(reason)})\n"
            f"Token: <code>{html.escape(symbol)}</code>\n"
            f"Foyda/zarar: ${pnl_usd:+.2f} ({pnl_pct:+.1f}%)\n"
        )
        if tx:
            text += f"Tranzaksiya: <code>{html.escape(tx[:20])}...</code>"
        await self.send_message(text)

    async def notify_daily_limit(self):
        await self.send_message(
            f"🛑 <b>Kunlik zarar limiti yetdi</b> (${settings.MAX_DAILY_LOSS_USD})\nBot avtomatik to'xtatildi."
        )
