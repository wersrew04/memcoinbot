"""Ma'lumotlarni tozalash va real hamyon bilan sinxronlash.

Ghost pozitsiyalar (walletda 0, lekin Redis/memory da ochiq),
eskirgan cooldownlar, scanner cache, ixtiyoriy tarix/kunlik zarar
tozalash. Live rejimda bot xatosiz ishlashi uchun muhim.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from utils.logger import logger
from utils.helpers import utc_now, safe_float, safe_int
from config.settings import settings
from config.constants import (
    REDIS_DAILY_LOSS,
    REDIS_OPEN_POSITIONS,
    REDIS_COOLDOWN_PREFIX,
    REDIS_PROCESSED_TOKENS,
)

DATA_DIR = Path("data")
TRADES_FILE = DATA_DIR / "closed_trades.jsonl"
EVENTS_FILE = DATA_DIR / "events.jsonl"
BLACKLIST_FILE = DATA_DIR / "blacklist.json"


class DataCleaner:
    """RiskManager + RPC bilan ishlaydigan tozalash xizmati."""

    def __init__(self, risk=None, rpc=None):
        self.risk = risk
        self.rpc = rpc

    def attach(self, risk=None, rpc=None):
        if risk is not None:
            self.risk = risk
        if rpc is not None:
            self.rpc = rpc

    # ------------------------------------------------------------------
    # Asosiy: ochiq pozitsiyalarni on-chain bilan sinxronlash
    # ------------------------------------------------------------------
    async def reconcile_positions(
        self,
        *,
        remove_zero_balance: bool = True,
        dust_threshold: float = 1e-9,
        sync_balances: bool = True,
    ) -> Dict[str, Any]:
        """
        Har bir ochiq pozitsiya uchun walletdagi haqiqiy SPL balansini tekshiradi.

        - Balans ~0 → ghost pozitsiya: o'chiriladi (remove_zero_balance=True).
        - Balans bor → tokens / tokens_raw yangilanadi (sync_balances=True).

        Paper mode da on-chain tekshiruv o'tkazib yuboriladi (faqat log).
        """
        report: Dict[str, Any] = {
            "checked": 0,
            "removed": [],
            "synced": [],
            "errors": [],
            "skipped_paper": False,
        }
        if not self.risk:
            report["errors"].append("RiskManager ulanmagan")
            return report

        positions = await self.risk.get_open_positions()
        if not positions:
            return report

        # Paper + keypair yo'q → faqat eskirgan yozuvlarni tozalash mumkin emas
        from wallet.keypair import load_keypair, get_pubkey

        kp = load_keypair()
        owner = get_pubkey()
        if settings.PAPER_TRADING or not owner or not self.rpc:
            report["skipped_paper"] = True
            logger.info(
                "Reconcile: PAPER yoki wallet/RPC yo'q – on-chain sinxron o'tkazib yuborildi "
                f"({len(positions)} pozitsiya)"
            )
            return report

        for token, pos in list(positions.items()):
            report["checked"] += 1
            symbol = pos.get("symbol") or token[:8]
            decimals = safe_int(pos.get("decimals") or 6)
            try:
                balance = await self.rpc.get_token_balance(owner, token)
            except Exception as e:
                msg = f"{symbol}: balance xato – {e}"
                report["errors"].append(msg)
                logger.warning(msg)
                continue

            if balance <= dust_threshold:
                if remove_zero_balance:
                    await self.risk.remove_position(token)
                    await self.risk.set_cooldown(token)
                    report["removed"].append(
                        {"token": token, "symbol": symbol, "balance": balance}
                    )
                    logger.info(
                        f"Tozalash: ghost pozitsiya o'chirildi {symbol} "
                        f"(on-chain balans={balance})"
                    )
                continue

            if sync_balances:
                tokens_raw = int(balance * (10 ** decimals))
                updates = {
                    "tokens": balance,
                    "tokens_raw": tokens_raw,
                }
                # Agar entry_price yo'q bo'lsa – saqlamaymiz, faqat amount
                old_raw = safe_int(pos.get("tokens_raw") or 0)
                if abs(tokens_raw - old_raw) > max(1, int(old_raw * 0.001)):
                    await self.risk.update_position(token, updates)
                    report["synced"].append(
                        {
                            "token": token,
                            "symbol": symbol,
                            "old_raw": old_raw,
                            "new_raw": tokens_raw,
                            "balance": balance,
                        }
                    )
                    logger.info(
                        f"Tozalash: {symbol} balans yangilandi "
                        f"{old_raw} → {tokens_raw} raw ({balance})"
                    )

        return report

    # ------------------------------------------------------------------
    # Cooldown tozalash
    # ------------------------------------------------------------------
    async def clear_expired_cooldowns(self) -> int:
        """Memory dagi muddati o'tgan cooldownlarni o'chirish. Redis TTL o'zi boshqaradi."""
        if not self.risk:
            return 0
        removed = 0
        now = utc_now()
        mem = getattr(self.risk, "_memory", None)
        if not mem:
            return 0
        cooldowns = mem.get("cooldowns") or {}
        expired = []
        for token, exp_iso in list(cooldowns.items()):
            try:
                exp = datetime.fromisoformat(exp_iso)
                if exp.tzinfo is None:
                    exp = exp.replace(tzinfo=timezone.utc)
                if now >= exp:
                    expired.append(token)
            except Exception:
                expired.append(token)
        for token in expired:
            cooldowns.pop(token, None)
            removed += 1
        if removed:
            logger.info(f"Tozalash: {removed} ta eskirgan cooldown o'chirildi")
        return removed

    async def clear_all_cooldowns(self) -> int:
        """Barcha cooldownlarni majburiy o'chirish (Redis + memory)."""
        if not self.risk:
            return 0
        count = 0
        mem = getattr(self.risk, "_memory", None)
        if mem and mem.get("cooldowns"):
            count = len(mem["cooldowns"])
            mem["cooldowns"] = {}

        redis = getattr(self.risk, "_redis", None)
        if redis:
            try:
                cursor = 0
                keys: List[str] = []
                while True:
                    cursor, batch = await redis.scan(
                        cursor=cursor, match=f"{REDIS_COOLDOWN_PREFIX}*", count=200
                    )
                    keys.extend(batch)
                    if cursor == 0:
                        break
                if keys:
                    await redis.delete(*keys)
                    count = max(count, len(keys))
            except Exception as e:
                logger.warning(f"Redis cooldown tozalash xato: {e}")
        if count:
            logger.info(f"Tozalash: barcha cooldownlar o'chirildi ({count})")
        return count

    # ------------------------------------------------------------------
    # Scanner processed tokens
    # ------------------------------------------------------------------
    async def clear_processed_tokens(self) -> bool:
        """Scanner qayta xuddi shu tokenlarni ko'rib chiqishi uchun cache tozalash."""
        if not self.risk:
            return False
        redis = getattr(self.risk, "_redis", None)
        if redis:
            try:
                await redis.delete(REDIS_PROCESSED_TOKENS)
                logger.info("Tozalash: scanner processed tokens o'chirildi")
                return True
            except Exception as e:
                logger.warning(f"Processed tokens tozalash xato: {e}")
                return False
        return True

    # ------------------------------------------------------------------
    # Kunlik zarar / ochiq pozitsiyalar
    # ------------------------------------------------------------------
    async def reset_daily_loss(self) -> bool:
        if not self.risk:
            return False
        today = utc_now().date().isoformat()
        redis = getattr(self.risk, "_redis", None)
        if redis:
            try:
                await redis.set(
                    REDIS_DAILY_LOSS,
                    json.dumps({"date": today, "loss": 0.0}),
                )
            except Exception as e:
                logger.warning(f"Daily loss reset xato: {e}")
                return False
        mem = getattr(self.risk, "_memory", None)
        if mem is not None:
            mem["daily_loss"] = 0.0
            mem["daily_loss_date"] = today
        logger.info("Tozalash: kunlik zarar 0 ga tushirildi")
        return True

    async def clear_all_positions(self, *, force: bool = False) -> int:
        """
        Barcha ochiq pozitsiyalarni yozuvdan o'chirish (sotish YO'Q – faqat state).
        force=False bo'lsa live rejimda ogohlantirish qaytaradi (0).
        """
        if not self.risk:
            return 0
        if not force and not settings.PAPER_TRADING:
            logger.warning(
                "clear_all_positions: live rejimda force=True kerak "
                "(aks holda on-chain tokenlar saqlanadi, faqat bot yozuvi o'chadi)"
            )
        positions = await self.risk.get_open_positions()
        n = len(positions)
        if self.risk._redis:
            await self.risk._redis.set(REDIS_OPEN_POSITIONS, json.dumps({}))
        self.risk._memory["open_positions"] = {}
        logger.info(f"Tozalash: {n} ta pozitsiya yozuvi o'chirildi (force={force})")
        return n

    # ------------------------------------------------------------------
    # Fayl tarixi
    # ------------------------------------------------------------------
    def clear_trade_history(self) -> bool:
        try:
            from utils.history import history

            history.trades.clear()
            history.rejections.clear()
            history.events.clear()
            if TRADES_FILE.exists():
                TRADES_FILE.write_text("", encoding="utf-8")
            if EVENTS_FILE.exists():
                EVENTS_FILE.write_text("", encoding="utf-8")
            logger.info("Tozalash: savdo tarixi va events tozalandi")
            return True
        except Exception as e:
            logger.warning(f"Trade history tozalash xato: {e}")
            return False

    # ------------------------------------------------------------------
    # To'liq tozalash (bir buyruq)
    # ------------------------------------------------------------------
    async def full_cleanup(
        self,
        *,
        reconcile: bool = True,
        clear_cooldowns: bool = True,
        clear_processed: bool = True,
        reset_daily_loss: bool = False,
        clear_history: bool = False,
        clear_positions: bool = False,
    ) -> Dict[str, Any]:
        """
        Standart tozalash paketi – bot startida yoki /clean buyrug'ida.

        Default: reconcile + cooldown + processed.
        Tarix / daily loss / barcha pozitsiyalar – faqat aniq so'ralganda.
        """
        result: Dict[str, Any] = {}

        if reconcile:
            result["reconcile"] = await self.reconcile_positions()
        if clear_cooldowns:
            result["cooldowns_cleared"] = await self.clear_all_cooldowns()
            result["expired_cooldowns"] = await self.clear_expired_cooldowns()
        if clear_processed:
            result["processed_cleared"] = await self.clear_processed_tokens()
        if reset_daily_loss:
            result["daily_loss_reset"] = await self.reset_daily_loss()
        if clear_history:
            result["history_cleared"] = self.clear_trade_history()
        if clear_positions:
            result["positions_cleared"] = await self.clear_all_positions(
                force=True
            )

        logger.info(f"Full cleanup tugadi: {result}")
        return result

    def format_report(self, report: Dict[str, Any]) -> str:
        """Telegram / admin uchun qisqa matn."""
        lines = ["🧹 <b>Ma'lumotlar tozalandi</b>"]
        rec = report.get("reconcile") or {}
        if rec:
            lines.append(
                f"• Tekshirildi: {rec.get('checked', 0)} | "
                f"Ghost o'chirildi: {len(rec.get('removed') or [])} | "
                f"Sinxron: {len(rec.get('synced') or [])}"
            )
            for r in (rec.get("removed") or [])[:5]:
                lines.append(f"  – ghost: {r.get('symbol')}")
            for s in (rec.get("synced") or [])[:5]:
                lines.append(
                    f"  – sync: {s.get('symbol')} "
                    f"({s.get('old_raw')}→{s.get('new_raw')})"
                )
            if rec.get("skipped_paper"):
                lines.append("• PAPER mode – on-chain reconcile o'tkazib yuborildi")
            errs = rec.get("errors") or []
            if errs:
                lines.append(f"• Xatolar: {len(errs)}")
        if "cooldowns_cleared" in report:
            lines.append(f"• Cooldownlar: {report.get('cooldowns_cleared', 0)} o'chirildi")
        if report.get("processed_cleared"):
            lines.append("• Scanner cache tozalandi")
        if report.get("daily_loss_reset"):
            lines.append("• Kunlik zarar 0 ga tushirildi")
        if report.get("history_cleared"):
            lines.append("• Savdo tarixi tozalandi")
        if "positions_cleared" in report:
            lines.append(f"• Pozitsiya yozuvlari: {report.get('positions_cleared', 0)}")
        return "\n".join(lines)


# Singleton – main / telegram / admin bir xil instansiya ishlatadi
cleaner = DataCleaner()
