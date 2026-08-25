"""Filter pipeline — tokenni bosqichma-bosqich tekshirish."""
from __future__ import annotations
from typing import Any, Dict, Optional, Tuple
import aiohttp
from utils.logger import logger
from utils.helpers import safe_float, safe_int
from utils.history import history
from config.settings import settings
from scanner.birdeye import get_token_security, get_token_overview
from blacklist.manager import BlacklistManager


class FilterPipeline:
    def __init__(self, blacklist: BlacklistManager):
        self.blacklist = blacklist

    async def run(self, token_data: Dict, session: aiohttp.ClientSession) -> Tuple[bool, str, Dict]:
        """
        Returns: (passed, reason, enriched_data)
        """
        token = token_data.get("token", "")
        symbol = token_data.get("symbol", "?")
        data = dict(token_data)

        # 1. Blacklist
        if self.blacklist.is_blacklisted(token):
            self._reject(symbol, token, "blacklist", "Qora ro'yxatda")
            return False, "Qora ro'yxatda", data

        # 2. Token yoshi
        age = safe_float(data.get("token_age_minutes"))
        if age < settings.MIN_TOKEN_AGE_MINUTES:
            self._reject(symbol, token, "age", f"Juda yangi: {age:.1f} min")
            return False, f"Juda yangi: {age:.1f} min", data
        if settings.MAX_TOKEN_AGE_MINUTES > 0 and age > settings.MAX_TOKEN_AGE_MINUTES:
            self._reject(symbol, token, "age", f"Juda eski: {age:.1f} min")
            return False, f"Juda eski: {age:.1f} min", data

        # 3. Likvidlik
        liq = safe_float(data.get("liquidity_usd"))
        if liq < settings.MIN_LIQUIDITY_USD:
            self._reject(symbol, token, "liquidity", f"Kam likvidlik: ${liq:,.0f}")
            return False, f"Kam likvidlik: ${liq:,.0f}", data

        # 4. Bozor hajmi
        mc = safe_float(data.get("market_cap"))
        if mc > 0 and settings.MIN_MARKET_CAP_USD > 0 and mc < settings.MIN_MARKET_CAP_USD:
            self._reject(symbol, token, "mcap", f"Kam market cap: ${mc:,.0f}")
            return False, f"Kam market cap: ${mc:,.0f}", data
        if mc > 0 and settings.MAX_MARKET_CAP_USD > 0 and mc > settings.MAX_MARKET_CAP_USD:
            self._reject(symbol, token, "mcap", f"Katta market cap: ${mc:,.0f}")
            return False, f"Katta market cap: ${mc:,.0f}", data

        # 5. Hajm (Gecko/Birdeye ba'zan volume_5m bermaydi → 1h dan taxmin)
        vol5m = safe_float(data.get("volume_5m"))
        if vol5m <= 0:
            vol1h = safe_float(data.get("volume_1h"))
            vol24 = safe_float(data.get("volume_24h"))
            if vol1h > 0:
                vol5m = vol1h / 12.0  # 1 soatni 12 ta 5 daqiqaga bo'lish
            elif vol24 > 0:
                vol5m = vol24 / 288.0
            data["volume_5m"] = vol5m
        if vol5m < settings.MIN_VOLUME_5M_USD:
            self._reject(symbol, token, "volume", f"Kam hajm 5m: ${vol5m:,.0f}")
            return False, f"Kam hajm 5m: ${vol5m:,.0f}", data

        # 6. Xarid/Sotuv nisbati
        bsr = safe_float(data.get("buy_sell_ratio"), 1.0)
        if bsr < settings.MIN_BUY_SELL_RATIO:
            self._reject(symbol, token, "bsr", f"Nisbat past: {bsr:.1f}")
            return False, f"Xarid/Sotuv nisbati past: {bsr:.1f}", data

        # 7. Birdeye xavfsizlik tekshiruvi
        if settings.BIRDEYE_API_KEY:
            sec = await get_token_security(session, token)
            ov = await get_token_overview(session, token)
            data["security"] = sec
            data["birdeye_overview"] = ov

            if sec:
                # Honeypot
                if sec.get("is_honeypot") in (True, "true", "1", 1):
                    if settings.AUTO_BLACKLIST_ENABLED and settings.BLACKLIST_HONEYPOT:
                        self.blacklist.add(token, "honeypot", source="filter")
                    self._reject(symbol, token, "security", "Honeypot")
                    return False, "Honeypot aniqlandi", data

                # Mint / Freeze
                if sec.get("mint_authority") or sec.get("is_mintable"):
                    self._reject(symbol, token, "security", "Mint authority faol")
                    return False, "Mint authority faol", data
                if sec.get("freeze_authority") or sec.get("is_freezable"):
                    self._reject(symbol, token, "security", "Freeze authority faol")
                    return False, "Freeze authority faol", data

                # Holderlar
                holders = safe_int(sec.get("holder_count") or ov.get("holder"))
                data["holder_count"] = holders
                if holders > 0 and holders < settings.MIN_HOLDERS:
                    self._reject(symbol, token, "holders", f"Kam holderlar: {holders}")
                    return False, f"Kam holderlar: {holders}", data

                # Top10
                top10 = safe_float(sec.get("top10_holder_pct") or sec.get("top10_user_pct"))
                if top10 > 1:
                    top10 /= 100
                if top10 > settings.MAX_TOP10_HOLDER_PCT:
                    self._reject(symbol, token, "holders", f"Top10 yuqori: {top10*100:.0f}%")
                    return False, f"Top10 holder konsentratsiya: {top10*100:.0f}%", data

        logger.info(f"[FILTER OK] {symbol} ({token[:8]}…) liq=${liq:,.0f} vol5m=${vol5m:,.0f}")
        return True, "OK", data

    def _reject(self, symbol: str, token: str, stage: str, reason: str):
        history.add_rejection(symbol, token, stage, reason)
        # INFO darajasida yozamiz — aks holda foydalanuvchi nima uchun
        # savdo ochilmayotganini bilmaydi (faqat SCAN loglari qolardi).
        logger.info(f"[REJECT] {symbol} → {stage}: {reason}")
