"""Telegram bildirishnoma yuborish."""
from __future__ import annotations
import aiohttp
from typing import Optional
from utils.logger import logger
from config.settings import settings


class TelegramNotifier:
    BASE = "https://api.telegram.org"

    def __init__(self, token: str = "", chat_id: str = ""):
        self.token = token
        self.chat_id = chat_id
        self._session: Optional[aiohttp.ClientSession] = None

    def set_session(self, session: aiohttp.ClientSession):
        self._session = session

    async def send_message(self, text: str, parse_mode: str = "HTML", reply_markup: Optional[dict] = None) -> bool:
        token = self.token or settings.TELEGRAM_BOT_TOKEN
        raw_chat = self.chat_id or settings.TELEGRAM_CHAT_ID
        if not token or not raw_chat:
            return False
        chat_ids = [x.strip() for x in str(raw_chat).split(",") if x.strip()]
        if not chat_ids:
            return False
        try:
            url = f"{self.BASE}/bot{token}/sendMessage"
            session = self._session
            ok_any = False
            for chat_id in chat_ids:
                payload = {
                    "chat_id": chat_id,
                    "text": text,
                    "parse_mode": parse_mode,
                    "disable_web_page_preview": True,
                }
                if reply_markup:
                    payload["reply_markup"] = reply_markup
                if not session or session.closed:
                    async with aiohttp.ClientSession() as s:
                        async with s.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=10)) as r:
                            if r.status == 200:
                                ok_any = True
                else:
                    async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=10)) as r:
                        if r.status == 200:
                            ok_any = True
            return ok_any
        except Exception as e:
            logger.warning(f"Telegram xabar yuborishda xato: {e}")
            return False
