"""Telegram bot — buyruqlar: /start /stop /positions /status /stats /wallet."""
from __future__ import annotations
import asyncio
from typing import Optional
from utils.logger import logger
from utils.helpers import utc_now, safe_float
from utils.history import history
from config.settings import settings
from telegram.notifier import TelegramNotifier
import aiohttp


class TelegramBot:
    def __init__(self, bot_ref=None):
        self.bot_ref = bot_ref
        self.notifier = TelegramNotifier()
        self._session: Optional[aiohttp.ClientSession] = None
        self._offset: int = 0
        self._running: bool = False
        self._states = {}  # chat_id -> state

    def set_session(self, session: aiohttp.ClientSession):
        self._session = session
        self.notifier.set_session(session)

    async def start_polling(self):
        self._running = True
        logger.info("Telegram bot polling boshlandi")
        while self._running:
            try:
                await self._poll()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning(f"Telegram poll xato: {e}")
            await asyncio.sleep(2)

    async def stop(self):
        self._running = False

    async def _poll(self):
        if not settings.TELEGRAM_BOT_TOKEN:
            await asyncio.sleep(10)
            return
        url = f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/getUpdates"
        params = {"timeout": 20, "offset": self._offset, "limit": 10}
        try:
            async with self._session.get(url, params=params,
                                          timeout=aiohttp.ClientTimeout(total=30)) as r:
                if r.status != 200:
                    return
                data = await r.json()
                updates = data.get("result") or []
                for upd in updates:
                    self._offset = upd["update_id"] + 1
                    await self._handle_update(upd)
        except asyncio.TimeoutError:
            pass

    def _get_inline_keyboard(self) -> dict:
        return {
            "inline_keyboard": [
                [
                    {"text": "▶️ Start", "callback_data": "start"},
                    {"text": "⏹ Stop", "callback_data": "stop"},
                ],
                [
                    {"text": "💰 Savdo ochish", "callback_data": "open_trade"},
                    {"text": "🔍 Token Tekshirish", "callback_data": "check_token"},
                ],
                [
                    {"text": "📊 Positions", "callback_data": "positions"},
                    {"text": "📈 Status", "callback_data": "status"},
                ],
                [
                    {"text": "🏆 Stats", "callback_data": "stats"},
                    {"text": "👛 Hamyon", "callback_data": "wallet"},
                ],
                [
                    {"text": "🧹 Tozalash", "callback_data": "clean"},
                    {"text": "👤 Admin qo'shish", "callback_data": "add_admin"},
                ],
                [
                    {"text": "🔄 Restart", "callback_data": "restart"},
                ]
            ]
        }

    async def _handle_update(self, update: dict):
        cb_query = update.get("callback_query")
        if cb_query:
            msg = cb_query.get("message") or {}
            chat_id = str(msg.get("chat", {}).get("id", ""))
            
            allowed_chat_ids = [x.strip() for x in str(settings.TELEGRAM_CHAT_ID).split(",") if x.strip()]
            if allowed_chat_ids and chat_id not in allowed_chat_ids:
                return
                
            data = cb_query.get("data", "")
            
            # Answer callback query to stop loading spinner
            try:
                url = f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/answerCallbackQuery"
                await self._session.post(url, json={"callback_query_id": cb_query["id"]})
            except Exception:
                pass
                
            if data == "start":
                await self._cmd_start()
            elif data == "stop":
                await self._cmd_stop()
            elif data == "positions":
                await self._cmd_positions()
            elif data == "status":
                await self._cmd_status()
            elif data == "stats":
                await self._cmd_stats()
            elif data == "wallet":
                await self._cmd_wallet()
            elif data == "clean":
                await self._cmd_clean()
            elif data == "restart":
                settings.BOT_RUNNING = True
                await self.notifier.send_message("🔄 Bot qayta ishga tushirildi", reply_markup=self._get_inline_keyboard())
            elif data == "check_token":
                self._states[chat_id] = "awaiting_token"
                await self.notifier.send_message(
                    "🔍 Iltimos, tekshirmoqchi bo'lgan Solana token manzilingizni yuboring (Mint address):",
                    reply_markup=self._get_inline_keyboard()
                )
            elif data == "open_trade":
                self._states[chat_id] = "awaiting_buy_token"
                await self.notifier.send_message(
                    "💰 <b>Savdo ochish</b>\n\n"
                    "Sotib olmoqchi bo'lgan Solana token manzilini (Mint address) yuboring.\n"
                    f"Miqdor: <b>${settings.TRADE_AMOUNT_USD:.2f}</b>\n"
                    f"Rejim: <b>{'PAPER' if settings.PAPER_TRADING else 'LIVE'}</b>",
                    reply_markup=self._get_inline_keyboard()
                )
            elif data == "add_admin":
                self._states[chat_id] = "awaiting_admin_id"
                await self.notifier.send_message(
                    "👤 <b>Yangi admin qo'shish</b>\n\n"
                    "Yangi adminning Telegram chat ID sini yuboring (raqam).\n"
                    "Masalan: <code>123456789</code>\n\n"
                    "Chat ID ni bilish: @userinfobot yoki @getidsbot ga yozing.",
                    reply_markup=self._get_inline_keyboard()
                )
            return

        msg = update.get("message")
        if not msg:
            return
        text = msg.get("text", "").strip()
        chat_id = str(msg.get("chat", {}).get("id", ""))

        allowed_chat_ids = [x.strip() for x in str(settings.TELEGRAM_CHAT_ID).split(",") if x.strip()]
        if allowed_chat_ids and chat_id not in allowed_chat_ids:
            return

        # State: token tekshirish
        if self._states.get(chat_id) == "awaiting_token":
            self._states[chat_id] = None
            if len(text) >= 30 and not text.startswith("/"):
                await self.notifier.send_message(f"⏳ <code>{text[:15]}...</code> token tahlil qilinmoqda...")
                result_text = await self._check_token_info(text)
                await self.notifier.send_message(result_text, reply_markup=self._get_inline_keyboard())
                return
            else:
                await self.notifier.send_message("❌ Yaroqsiz token manzili yuborildi.", reply_markup=self._get_inline_keyboard())
                return

        # State: savdo ochish (token yuboriladi → bot sotib oladi)
        if self._states.get(chat_id) == "awaiting_buy_token":
            self._states[chat_id] = None
            if len(text) >= 30 and not text.startswith("/"):
                await self.notifier.send_message(
                    f"⏳ <code>{text[:15]}...</code> uchun savdo ochilmoqda...\n"
                    f"Miqdor: ${settings.TRADE_AMOUNT_USD:.2f}"
                )
                result_text = await self._open_manual_trade(text)
                await self.notifier.send_message(result_text, reply_markup=self._get_inline_keyboard())
                return
            else:
                await self.notifier.send_message("❌ Yaroqsiz token manzili yuborildi.", reply_markup=self._get_inline_keyboard())
                return

        # State: yangi admin qo'shish
        if self._states.get(chat_id) == "awaiting_admin_id":
            self._states[chat_id] = None
            new_id = text.strip()
            if new_id.isdigit() and len(new_id) >= 5:
                ok, msg = self._add_admin(new_id)
                await self.notifier.send_message(msg, reply_markup=self._get_inline_keyboard())
                return
            else:
                await self.notifier.send_message(
                    "❌ Yaroqsiz chat ID. Faqat raqam yuboring (masalan: 123456789).",
                    reply_markup=self._get_inline_keyboard()
                )
                return

        # Check if text is a potential private key (base58, usually 87-88 chars)
        if len(text) >= 80 and not text.startswith("/"):
            try:
                import base58
                decoded = base58.b58decode(text)
                if len(decoded) in (32, 64):
                    from solders.keypair import Keypair
                    kp = Keypair.from_base58_string(text)
                    settings.PRIVATE_KEY = text
                    # Persist to .env
                    try:
                        from dotenv import set_key
                        from pathlib import Path
                        env_file = Path(__file__).resolve().parent.parent / ".env"
                        set_key(str(env_file), "PRIVATE_KEY", text)
                    except Exception:
                        pass
                    await self.notifier.send_message(
                        f"✅ Hamyon ulandi!\n"
                        f"Manzil: <code>{str(kp.pubkey())}</code>\n"
                        f"Rejim: {'PAPER' if settings.PAPER_TRADING else 'LIVE'}",
                        reply_markup=self._get_inline_keyboard()
                    )
                    return
            except Exception:
                pass

        if text in ("/start", "▶️ Start"):
            await self._cmd_start()
        elif text in ("/stop", "⏹ Stop"):
            await self._cmd_stop()
        elif text == "/positions":
            await self._cmd_positions()
        elif text == "/status":
            await self._cmd_status()
        elif text == "/stats":
            await self._cmd_stats()
        elif text in ("/wallet", "👛 Hamyon"):
            await self._cmd_wallet()
        elif text in ("/clean", "🧹 Tozalash"):
            await self._cmd_clean()
        elif text == "/clean_all":
            await self._cmd_clean_all()
        elif text.startswith("/set_wallet"):
            pk = text.replace("/set_wallet", "").strip()
            if pk:
                try:
                    from solders.keypair import Keypair
                    kp = Keypair.from_base58_string(pk)
                    settings.PRIVATE_KEY = pk
                    # Persist to .env
                    try:
                        from dotenv import set_key
                        from pathlib import Path
                        env_file = Path(__file__).resolve().parent.parent / ".env"
                        set_key(str(env_file), "PRIVATE_KEY", pk)
                    except Exception:
                        pass
                    await self.notifier.send_message(
                        f"✅ Hamyon ulandi!\n"
                        f"Manzil: <code>{str(kp.pubkey())}</code>\n"
                        f"Rejim: {'PAPER' if settings.PAPER_TRADING else 'LIVE'}",
                        reply_markup=self._get_inline_keyboard()
                    )
                except Exception as e:
                    await self.notifier.send_message(f"❌ Xato: Yaroqsiz private key ({e})", reply_markup=self._get_inline_keyboard())
        elif text == "/clear_wallet":
            settings.PRIVATE_KEY = ""
            # Persist to .env
            try:
                from dotenv import set_key
                from pathlib import Path
                env_file = Path(__file__).resolve().parent.parent / ".env"
                set_key(str(env_file), "PRIVATE_KEY", "")
            except Exception:
                pass
            await self.notifier.send_message("🗑 Hamyon tozalandi", reply_markup=self._get_inline_keyboard())
        elif text == "/restart":
            settings.BOT_RUNNING = True
            await self.notifier.send_message("🔄 Bot qayta ishga tushirildi", reply_markup=self._get_inline_keyboard())
        elif text in ("/buy", "/savdo", "💰 Savdo ochish"):
            self._states[chat_id] = "awaiting_buy_token"
            await self.notifier.send_message(
                "💰 <b>Savdo ochish</b>\n\n"
                "Sotib olmoqchi bo'lgan Solana token manzilini (Mint address) yuboring.\n"
                f"Miqdor: <b>${settings.TRADE_AMOUNT_USD:.2f}</b>\n"
                f"Rejim: <b>{'PAPER' if settings.PAPER_TRADING else 'LIVE'}</b>",
                reply_markup=self._get_inline_keyboard()
            )
        elif text.startswith("/add_admin"):
            parts = text.split(maxsplit=1)
            if len(parts) > 1 and parts[1].strip().isdigit():
                ok, msg = self._add_admin(parts[1].strip())
                await self.notifier.send_message(msg, reply_markup=self._get_inline_keyboard())
            else:
                self._states[chat_id] = "awaiting_admin_id"
                await self.notifier.send_message(
                    "👤 <b>Yangi admin qo'shish</b>\n\n"
                    "Yangi adminning Telegram chat ID sini yuboring (raqam).\n"
                    "Masalan: <code>123456789</code>",
                    reply_markup=self._get_inline_keyboard()
                )
        elif text in ("/admins", "/adminlar"):
            ids = [x.strip() for x in str(settings.TELEGRAM_CHAT_ID or "").split(",") if x.strip()]
            await self.notifier.send_message(
                f"👤 <b>Adminlar ro'yxati</b>\n\n"
                f"Jami: <b>{len(ids)}</b>\n"
                + "\n".join(f"• <code>{i}</code>" for i in ids),
                reply_markup=self._get_inline_keyboard()
            )

    async def _cmd_start(self):
        settings.BOT_RUNNING = True
        if self.bot_ref and hasattr(self.bot_ref, "risk"):
            await self.bot_ref.risk.set_bot_running(True)
        await self.notifier.send_message(
            "▶️ <b>Bot ishga tushdi!</b>\n\n"
            f"Mode: <b>{'PAPER' if settings.PAPER_TRADING else 'LIVE'}</b>\n"
            f"Trade: <b>${settings.TRADE_AMOUNT_USD:.1f}</b>\n"
            f"TP: <b>{settings.TAKE_PROFIT_PCT*100:.0f}%</b> | "
            f"SL: <b>{settings.STOP_LOSS_PCT*100:.0f}%</b>\n\n"
            "Boshqarish uchun quyidagi tugmalardan foydalaning:",
            reply_markup=self._get_inline_keyboard()
        )

    async def _cmd_stop(self):
        settings.BOT_RUNNING = False
        if self.bot_ref and hasattr(self.bot_ref, "risk"):
            await self.bot_ref.risk.set_bot_running(False)
        await self.notifier.send_message("⏹ <b>Bot to'xtatildi</b>", reply_markup=self._get_inline_keyboard())

    async def _cmd_positions(self):
        if not self.bot_ref or not hasattr(self.bot_ref, "risk"):
            await self.notifier.send_message("Pozitsiyalar mavjud emas", reply_markup=self._get_inline_keyboard())
            return
        positions = await self.bot_ref.risk.get_open_positions()
        if not positions:
            await self.notifier.send_message("📭 Ochiq pozitsiyalar yo'q", reply_markup=self._get_inline_keyboard())
            return
        lines = ["📊 <b>Ochiq pozitsiyalar:</b>\n"]
        for tok, pos in positions.items():
            entry = pos.get("entry_price", 0)
            curr = pos.get("current_price", entry)
            from utils.helpers import pnl_percent, pnl_usd as calc_pnl
            pct = pnl_percent(entry, curr)
            usd = calc_pnl(pos.get("amount_usd", 0), entry, curr)
            emoji = "🟢" if pct >= 0 else "🔴"
            lines.append(
                f"{emoji} <b>{pos.get('symbol', tok[:8])}</b>\n"
                f"   Miqdor: ${pos.get('amount_usd', 0):.2f}\n"
                f"   PnL: ${usd:+.2f} ({pct:+.1f}%)\n"
                f"   {'PAPER' if pos.get('paper') else 'LIVE'}"
            )
        await self.notifier.send_message("\n".join(lines), reply_markup=self._get_inline_keyboard())

    async def _cmd_status(self):
        if not self.bot_ref or not hasattr(self.bot_ref, "risk"):
            await self.notifier.send_message("Status mavjud emas", reply_markup=self._get_inline_keyboard())
            return
        summary = await self.bot_ref.risk.get_status_summary()
        pnl = history.pnl_summary()
        await self.notifier.send_message(
            f"📈 <b>Bot holati</b>\n\n"
            f"▶️ Ishlamoqda: <b>{'Ha' if settings.BOT_RUNNING else 'Yoq'}</b>\n"
            f"📦 Ochiq: <b>{summary.get('open_positions', 0)}/{settings.MAX_OPEN_POSITIONS}</b>\n"
            f"💸 Kunlik zarar: <b>${summary.get('daily_loss_usd', 0):.2f}</b>\n"
            f"📊 Net PnL: <b>${pnl['net_pnl']:+.2f}</b>\n"
            f"🏆 Win rate: <b>{pnl['win_rate']}%</b>\n"
            f"🎯 Jami savdolar: <b>{pnl['total_trades']}</b>\n"
            f"Mode: <b>{'PAPER' if settings.PAPER_TRADING else 'LIVE'}</b>",
            reply_markup=self._get_inline_keyboard()
        )

    async def _cmd_stats(self):
        pnl = history.pnl_summary()
        await self.notifier.send_message(
            f"📊 <b>Statistika</b>\n\n"
            f"Jami savdolar: <b>{pnl['total_trades']}</b>\n"
            f"Net PnL: <b>${pnl['net_pnl']:+.2f}</b>\n"
            f"Profit: <b>${pnl['profit']:.2f}</b>\n"
            f"Zarar: <b>${pnl['loss']:.2f}</b>\n"
            f"Win rate: <b>{pnl['win_rate']}%</b>\n"
            f"Eng yaxshi: <b>${pnl['best']:+.2f}</b>\n"
            f"Eng yomon: <b>${pnl['worst']:+.2f}</b>",
            reply_markup=self._get_inline_keyboard()
        )

    async def _cmd_wallet(self):
        from wallet.keypair import get_pubkey, get_sol_balance
        pubkey = get_pubkey()
        if not pubkey:
            await self.notifier.send_message(
                "👛 <b>Hamyon ulanmagan</b>\n\n"
                "Paper rejimda ishlayapsiz.\n"
                "Ulash: /set_wallet <private_key>",
                reply_markup=self._get_inline_keyboard()
            )
            return
        sol_bal = 0.0
        if self._session:
            sol_bal = await get_sol_balance(self._session, pubkey)
        await self.notifier.send_message(
            f"👛 <b>Hamyon</b>\n\n"
            f"Manzil: <code>{pubkey}</code>\n"
            f"SOL balans: <b>{sol_bal:.4f} SOL</b>\n"
            f"Mode: <b>{'PAPER' if settings.PAPER_TRADING else 'LIVE'}</b>",
            reply_markup=self._get_inline_keyboard()
        )

    async def _cmd_clean(self):
        if self.bot_ref and hasattr(self.bot_ref, "risk"):
            self.bot_ref.risk.clear_cooldowns()
            self.bot_ref.risk.clear_processed()
        await self.notifier.send_message("🧹 Tozalash amalga oshirildi", reply_markup=self._get_inline_keyboard())

    async def _cmd_clean_all(self):
        if self.bot_ref and hasattr(self.bot_ref, "risk"):
            self.bot_ref.risk.clear_cooldowns()
            self.bot_ref.risk.clear_processed()
            await self.bot_ref.risk.reset_daily_loss()
            if hasattr(self.bot_ref, "advanced_risk"):
                self.bot_ref.advanced_risk.daily_trades = 0
                self.bot_ref.advanced_risk.consecutive_losses = 0
        history.clear_trades()
        await self.notifier.send_message("🧹 Kuchli tozalash bajarildi (tarix, kunlik zarar va cooldown nollashdi)", reply_markup=self._get_inline_keyboard())

    async def _check_token_info(self, token_address: str) -> str:
        if not self.bot_ref:
            return "❌ Xato: Bot bog'lanmagan."
            
        url = f"https://api.dexscreener.com/latest/dex/tokens/{token_address}"
        try:
            async with self._session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as r:
                if r.status != 200:
                    return f"❌ DexScreener ma'lumot topa olmadi (Status: {r.status})."
                data = await r.json()
                pairs = data.get("pairs") or []
                if not pairs:
                    return "❌ Token uchun hech qanday savdo juftligi topilmadi."
                
                from scanner.dexscreener import _normalize_pair
                from config.settings import settings
                
                best_pair_raw = sorted(
                    [p for p in pairs if p.get("chainId") == "solana"],
                    key=lambda p: safe_float((p.get("liquidity") or {}).get("usd")),
                    reverse=True
                )
                if not best_pair_raw:
                    return "❌ Faqat Solana tarmog'idagi juftliklar qo'llab-quvvatlanadi."
                
                pair = _normalize_pair(best_pair_raw[0])
                
                pipeline = self.bot_ref.filter_pipeline
                passed, reason, enriched = await pipeline.run(pair, self._session)
                
                scorer = self.bot_ref.scorer
                ai_result = scorer.score(enriched)
                
                lines = [
                    f"🔍 <b>TOKEN TAHLILI: {enriched.get('symbol', '?')}</b>\n",
                    f"📝 Nomi: <b>{enriched.get('name', '?')}</b>",
                    f"🔑 Address: <code>{token_address}</code>\n",
                    f"💵 Narxi: <b>${enriched.get('price_usd', 0):.10f}</b>",
                    f"💧 Liquidity: <b>${enriched.get('liquidity_usd', 0):,.0f}</b>",
                    f"📊 Vol 5m: <b>${enriched.get('volume_5m', 0):,.0f}</b>",
                    f"📈 Market Cap: <b>${enriched.get('market_cap', 0):,.0f}</b>",
                    f"⏳ Yoshi: <b>{enriched.get('token_age_minutes', 0):.1f} daqiqa</b>\n",
                    f"🛡 Filtrlar: <b>{'Oʻtdi ✅' if passed else 'Oʻtmadi ❌'}</b>",
                    f"💬 Sabab: <b>{reason or 'Muammosiz'}</b>\n",
                    f"🤖 AI ball: <b>{ai_result.score:.1f} / 100</b>",
                    f"📢 Tavsiya: <b>{ai_result.recommendation.value}</b>"
                ]
                
                if ai_result.signals:
                    lines.append("\n🟢 <b>AI Signallar:</b>")
                    for sig in ai_result.signals[:3]:
                        lines.append(f"• {sig}")
                if ai_result.warnings:
                    lines.append("\n⚠️ <b>AI Ogohlantirishlar:</b>")
                    for warn in ai_result.warnings[:3]:
                        lines.append(f"• {warn}")
                        
                return "\n".join(lines)
                
        except Exception as e:
            return f"❌ Tahlil jarayonida xatolik yuz berdi: {e}"


    def _add_admin(self, new_chat_id: str) -> tuple:
        """Yangi admin (chat_id) qo'shish va .env ga yozish."""
        current = str(settings.TELEGRAM_CHAT_ID or "").strip()
        ids = [x.strip() for x in current.split(",") if x.strip()]
        if new_chat_id in ids:
            return False, f"ℹ️ Bu chat ID allaqachon admin: <code>{new_chat_id}</code>"
        ids.append(new_chat_id)
        new_value = ",".join(ids)
        settings.TELEGRAM_CHAT_ID = new_value
        try:
            from dotenv import set_key
            from pathlib import Path
            env_file = Path(__file__).resolve().parent.parent / ".env"
            set_key(str(env_file), "TELEGRAM_CHAT_ID", new_value)
        except Exception as e:
            return False, f"❌ .env ga yozishda xato: {e}"
        return True, (
            f"✅ Yangi admin qo'shildi!\n\n"
            f"Chat ID: <code>{new_chat_id}</code>\n"
            f"Jami adminlar: <b>{len(ids)}</b>\n"
            f"Ro'yxat: <code>{new_value}</code>"
        )

    async def _open_manual_trade(self, token_address: str) -> str:
        """Token manzili bo'yicha qo'lda savdo ochish (sotib olish)."""
        if not self.bot_ref:
            return "❌ Xato: Bot bog'lanmagan."

        if not settings.BOT_RUNNING:
            return "❌ Bot to'xtatilgan. Avval ▶️ Start bosing."

        # DexScreener dan ma'lumot
        url = f"https://api.dexscreener.com/latest/dex/tokens/{token_address}"
        try:
            async with self._session.get(url, timeout=aiohttp.ClientTimeout(total=12)) as r:
                if r.status != 200:
                    return f"❌ DexScreener ma'lumot topa olmadi (Status: {r.status})."
                data = await r.json()
                pairs = data.get("pairs") or []
                if not pairs:
                    return "❌ Token uchun savdo juftligi topilmadi."

                from scanner.dexscreener import _normalize_pair
                from buy.executor import execute_buy
                from utils.helpers import safe_float

                solana_pairs = [p for p in pairs if p.get("chainId") == "solana"]
                if not solana_pairs:
                    return "❌ Faqat Solana tarmog'idagi tokenlar qo'llab-quvvatlanadi."

                best = sorted(
                    solana_pairs,
                    key=lambda p: safe_float((p.get("liquidity") or {}).get("usd")),
                    reverse=True
                )[0]
                pair = _normalize_pair(best)
                symbol = pair.get("symbol") or token_address[:8]
                price = safe_float(pair.get("price_usd"))
                if price <= 0:
                    return "❌ Token narxi 0 yoki topilmadi."

                # Risk pre-check
                amount = settings.TRADE_AMOUNT_USD
                ok, reason = await self.bot_ref.risk.pre_trade_check(token_address, amount)
                if not ok:
                    return f"❌ Savdo ochilmadi: {reason}"

                # Sotib olish
                success, position = await execute_buy(
                    token=token_address,
                    symbol=symbol,
                    amount_usd=amount,
                    current_price=price,
                    session=self._session,
                    paper=settings.PAPER_TRADING,
                )
                if not success:
                    err = position.get("error", "Noma'lum xato")
                    return f"❌ Xarid muvaffaqiyatsiz: {err}"

                position["ai_score"] = 0
                position["manual"] = True
                position["high_price"] = price

                opened = await self.bot_ref.risk.open_position(token_address, position)
                if not opened:
                    return "❌ Pozitsiya ochilmadi (allaqachon mavjud bo'lishi mumkin)."

                if hasattr(self.bot_ref, "advanced_risk"):
                    self.bot_ref.advanced_risk.daily_trades += 1

                mode = "PAPER" if settings.PAPER_TRADING else "LIVE"
                liq = safe_float(pair.get("liquidity_usd"))
                return (
                    f"🟢 <b>SAVDO OCHILDI: {symbol}</b>\n\n"
                    f"🔑 Address: <code>{token_address}</code>\n"
                    f"💰 Miqdor: <b>${amount:.2f}</b>\n"
                    f"📈 Narx: <b>${price:.10f}</b>\n"
                    f"💧 Liquidity: <b>${liq:,.0f}</b>\n"
                    f"📦 Token miqdori: <b>{position.get('tokens_amount', 0):.4f}</b>\n"
                    f"Rejim: <b>{mode}</b>\n\n"
                    f"✅ Pozitsiya ochiq. Monitor TP/SL ishlaydi."
                )
        except Exception as e:
            return f"❌ Savdo ochishda xatolik: {e}"
