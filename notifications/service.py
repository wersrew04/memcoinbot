"""Ko'p kanalli xabarnomalar: Telegram, Discord, Email."""
from __future__ import annotations

import httpx
from typing import Any, Optional
from utils.logger import logger
from config.settings import settings


class NotificationService:
    def __init__(self, telegram_bot=None):
        self.telegram = telegram_bot

    async def send(
        self,
        title: str,
        message: str,
        level: str = "info",  # info | trade | signal | error | whale
    ):
        text = f"<b>{title}</b>\n{message}"
        if settings.NOTIFY_TELEGRAM and self.telegram:
            try:
                await self.telegram.send_message(text, parse_mode="HTML")
            except Exception as e:
                logger.error(f"Telegram xabar yuborilmadi: {e}")

        if settings.NOTIFY_DISCORD and settings.DISCORD_WEBHOOK_URL:
            await self._discord(title, message, level)

        if settings.NOTIFY_EMAIL and settings.EMAIL_TO:
            await self._email(title, message)

    async def _discord(self, title: str, message: str, level: str):
        color = {
            "info": 0x3498DB,
            "trade": 0x2ECC71,
            "signal": 0x9B59B6,
            "error": 0xE74C3C,
            "whale": 0xF1C40F,
        }.get(level, 0x95A5A6)
        payload = {
            "embeds": [{
                "title": title,
                "description": message,
                "color": color,
            }]
        }
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                await client.post(settings.DISCORD_WEBHOOK_URL, json=payload)
        except Exception as e:
            logger.error(f"Discord xabar yuborilmadi: {e}")

    async def _email(self, title: str, message: str):
        # Minimal SMTP – production'da aiosmtplib ishlatish tavsiya etiladi
        try:
            import smtplib
            from email.mime.text import MIMEText
            msg = MIMEText(message)
            msg["Subject"] = f"[MemeBot] {title}"
            msg["From"] = settings.EMAIL_USER
            msg["To"] = settings.EMAIL_TO
            with smtplib.SMTP(settings.EMAIL_SMTP_HOST, settings.EMAIL_SMTP_PORT) as s:
                s.starttls()
                s.login(settings.EMAIL_USER, settings.EMAIL_PASSWORD)
                s.send_message(msg)
        except Exception as e:
            logger.error(f"Email xabar yuborilmadi: {e}")

    async def notify_buy(self, symbol: str, token: str, amount: float, score: float, tx: str = ""):
        if not settings.NOTIFY_ON_BUY:
            return
        await self.send(
            "🟢 XARID",
            f"{symbol}\nToken: <code>{token}</code>\nMiqdor: ${amount:.2f}\nAI ball: {score:.1f}\nTranzaksiya: {tx or 'PAPER'}",
            "trade",
        )

    async def notify_sell(self, symbol: str, pnl_usd: float, pnl_pct: float, reason: str, tx: str = ""):
        if not settings.NOTIFY_ON_SELL:
            return
        emoji = "🟢" if pnl_usd >= 0 else "🔴"
        await self.send(
            f"{emoji} SOTISH ({reason})",
            f"{symbol}\nFoyda/zarar: ${pnl_usd:+.2f} ({pnl_pct:+.1f}%)\nTranzaksiya: {tx or 'PAPER'}",
            "trade",
        )

    async def notify_ai_signal(self, symbol: str, score: float, rec: str):
        if not settings.NOTIFY_ON_AI_SIGNAL:
            return
        await self.send("🤖 AI signal", f"{symbol}\nBall: {score:.1f}\nTavsiya: {rec}", "signal")

    async def notify_whale(self, token: str, event_type: str, amount: float, tier: str):
        if not settings.NOTIFY_ON_WHALE:
            return
        await self.send(
            f"🐋 Whale {event_type.upper()}",
            f"Token: <code>{token[:12]}...</code>\n{tier} ${amount:,.0f}",
            "whale",
        )

    async def notify_error(self, context: str, error: str):
        if not settings.NOTIFY_ON_ERROR:
            return
        await self.send("❌ Xato", f"{context}\n{error}", "error")
