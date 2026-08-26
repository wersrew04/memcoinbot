"""Filter pipeline — tokenni bosqichma-bosqich tekshirish + yakuniy scam gate."""
from __future__ import annotations
from typing import Any, Dict, Optional, Tuple
import aiohttp
from utils.logger import logger
from utils.helpers import safe_float, safe_int
from utils.history import history
from config.settings import settings
from scanner.birdeye import get_token_security, get_token_overview
from blacklist.manager import BlacklistManager


def _truthy(v) -> bool:
    return v in (True, "true", "True", "1", 1, "yes", "YES")


def _has_authority(v) -> bool:
    """Mint/freeze authority mavjudligi — bo'sh/None = yaxshi."""
    if v in (None, False, "false", "False", "", "null", "None", 0, "0"):
        return False
    if _truthy(v):
        return True
    if isinstance(v, str) and len(v) > 20:
        return True
    return False


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
        if settings.MAX_LIQUIDITY_USD > 0 and liq > settings.MAX_LIQUIDITY_USD:
            self._reject(symbol, token, "liquidity", f"Juda katta liq: ${liq:,.0f}")
            return False, f"Juda katta likvidlik: ${liq:,.0f}", data

        # 4. Bozor hajmi
        mc = safe_float(data.get("market_cap"))
        if mc > 0 and settings.MIN_MARKET_CAP_USD > 0 and mc < settings.MIN_MARKET_CAP_USD:
            self._reject(symbol, token, "mcap", f"Kam market cap: ${mc:,.0f}")
            return False, f"Kam market cap: ${mc:,.0f}", data
        if mc > 0 and settings.MAX_MARKET_CAP_USD > 0 and mc > settings.MAX_MARKET_CAP_USD:
            self._reject(symbol, token, "mcap", f"Katta market cap: ${mc:,.0f}")
            return False, f"Katta market cap: ${mc:,.0f}", data

        # 5. Hajm
        vol5m = safe_float(data.get("volume_5m"))
        if vol5m <= 0:
            vol1h = safe_float(data.get("volume_1h"))
            vol24 = safe_float(data.get("volume_24h"))
            if vol1h > 0:
                vol5m = vol1h / 12.0
            elif vol24 > 0:
                vol5m = vol24 / 288.0
            data["volume_5m"] = vol5m
        if vol5m < settings.MIN_VOLUME_5M_USD:
            self._reject(symbol, token, "volume", f"Kam hajm 5m: ${vol5m:,.0f}")
            return False, f"Kam hajm 5m: ${vol5m:,.0f}", data

        # 6. Xarid/Sotuv nisbati
        bsr = safe_float(data.get("buy_sell_ratio"), 1.0)
        source = (data.get("source") or "")
        bsr_unknown = abs(bsr - 1.0) < 1e-9 and source in (
            "geckoterminal", "birdeye_new", "birdeye_trend", "birdeye"
        )
        if not bsr_unknown and bsr < settings.MIN_BUY_SELL_RATIO:
            self._reject(symbol, token, "bsr", f"Nisbat past: {bsr:.1f}")
            return False, f"Xarid/Sotuv nisbati past: {bsr:.1f}", data

        # 7. Birdeye xavfsizlik
        sec: Dict = {}
        ov: Dict = {}
        if settings.BIRDEYE_API_KEY:
            sec = await get_token_security(session, token)
            ov = await get_token_overview(session, token)
            data["security"] = sec
            data["birdeye_overview"] = ov

            ok, reason = self._check_security_block(sec, ov, symbol, token, data)
            if not ok:
                return False, reason, data
        else:
            if not settings.PAPER_TRADING:
                self._reject(symbol, token, "security", "BIRDEYE_API_KEY yo'q — live xarid taqiqlangan")
                return False, "Xavfsizlik API yo'q", data
            logger.warning("[FILTER] BIRDEYE_API_KEY yo'q — security skip (PAPER)")

        # 8. Likvidlik vs 5m hajm
        if liq > 0 and vol5m > 0 and vol5m < liq * 0.001 and vol5m < 100:
            self._reject(symbol, token, "volume", "Likvidlikka nisbatan faollik juda past")
            return False, "Faollik juda past", data

        # 9. LP lock (sozlangan bo'lsa)
        if settings.REQUIRE_LP_LOCKED and sec:
            if sec.get("lpBurned") is False and sec.get("isLiquidityLocked") is False:
                self._reject(symbol, token, "lp", "LP lock yo'q")
                return False, "LP lock talab qilinadi", data

        logger.info(f"[FILTER OK] {symbol} ({token[:8]}…) liq=${liq:,.0f} vol5m=${vol5m:,.0f}")
        return True, "OK", data

    def _check_security_block(
        self, sec: Dict, ov: Dict, symbol: str, token: str, data: Dict
    ) -> Tuple[bool, str]:
        """Birdeye security — hard reject (scam)."""
        if not sec:
            if not settings.PAPER_TRADING:
                self._reject(symbol, token, "security", "Birdeye security yo'q")
                return False, "Xavfsizlik ma'lumoti yo'q"
            return True, "OK"

        if (
            _truthy(sec.get("is_honeypot"))
            or _truthy(sec.get("honeypot"))
            or _truthy(sec.get("cannotSellAll"))
            or _truthy(sec.get("is_sell_restricted"))
            or _truthy(sec.get("isHoneypot"))
        ):
            if settings.AUTO_BLACKLIST_ENABLED and settings.BLACKLIST_HONEYPOT:
                self.blacklist.add(token, "honeypot", source="filter")
            self._reject(symbol, token, "security", "Honeypot / sell restricted")
            return False, "Honeypot aniqlandi"

        for tax_key in (
            "transferFee", "transfer_fee", "sellTax", "sell_tax",
            "buyTax", "buy_tax", "tax", "tradeTax",
        ):
            tax = safe_float(sec.get(tax_key))
            if tax > 1:
                tax = tax / 100.0
            if tax >= 0.10:
                if settings.AUTO_BLACKLIST_ENABLED:
                    self.blacklist.add(token, f"high_tax_{tax_key}", source="filter")
                self._reject(symbol, token, "security", f"Yuqori tax: {tax*100:.0f}%")
                return False, f"Yuqori transfer/sell tax: {tax*100:.0f}%"

        if _has_authority(sec.get("mint_authority")) or _truthy(sec.get("is_mintable")):
            self._reject(symbol, token, "security", "Mint authority faol")
            return False, "Mint authority faol"
        if _has_authority(sec.get("freeze_authority")) or _truthy(sec.get("is_freezable")):
            self._reject(symbol, token, "security", "Freeze authority faol")
            return False, "Freeze authority faol"

        owner_pct = safe_float(
            sec.get("ownerPercentage")
            or sec.get("creatorPercentage")
            or sec.get("owner_pct")
            or sec.get("creator_pct")
        )
        if owner_pct > 1:
            owner_pct /= 100.0
        max_dev = getattr(settings, "MAX_DEV_WALLET_PCT", 0.15) or 0.15
        if owner_pct > max_dev:
            self._reject(symbol, token, "security", f"Creator ulushi {owner_pct*100:.0f}%")
            return False, f"Creator ulushi yuqori: {owner_pct*100:.0f}%"

        holders = safe_int(
            sec.get("holder_count") or ov.get("holder") or sec.get("holder") or data.get("holder_count")
        )
        data["holder_count"] = holders
        if holders > 0 and holders < settings.MIN_HOLDERS:
            self._reject(symbol, token, "holders", f"Kam holderlar: {holders}")
            return False, f"Kam holderlar: {holders}"

        top10 = safe_float(
            sec.get("top10_holder_pct")
            or sec.get("top10_user_pct")
            or sec.get("top10HolderPercent")
            or sec.get("top10HolderPct")
        )
        if top10 > 1:
            top10 /= 100
        if top10 > 0 and top10 > settings.MAX_TOP10_HOLDER_PCT:
            self._reject(symbol, token, "holders", f"Top10 yuqori: {top10*100:.0f}%")
            return False, f"Top10 holder konsentratsiya: {top10*100:.0f}%"

        if _truthy(sec.get("is_scam")) or _truthy(sec.get("isScam")) or _truthy(sec.get("risky")):
            if settings.AUTO_BLACKLIST_ENABLED:
                self.blacklist.add(token, "scam_flag", source="filter")
            self._reject(symbol, token, "security", "Scam flag")
            return False, "Scam deb belgilangan"

        return True, "OK"

    async def final_scam_gate(
        self,
        token: str,
        symbol: str,
        session: aiohttp.ClientSession,
        data: Optional[Dict] = None,
    ) -> Tuple[bool, str]:
        """
        Filter + AI o'tganidan KEYIN, xarid oldidan yakuniy scam tekshiruvi.
        Filterdan o'tgan bo'lsa ham, shu yerda rad qilinishi mumkin.
        """
        data = data or {}
        if self.blacklist.is_blacklisted(token):
            return False, "Qora ro'yxatda"

        sec: Dict = {}
        ov: Dict = {}
        if settings.BIRDEYE_API_KEY:
            try:
                sec = await get_token_security(session, token)
                ov = await get_token_overview(session, token)
            except Exception as e:
                logger.warning("[SCAM GATE] Birdeye xato %s: %s", symbol, e)
                if not settings.PAPER_TRADING:
                    return False, "Xavfsizlik API javob bermadi"

        if settings.BIRDEYE_API_KEY:
            ok, reason = self._check_security_block(sec, ov, symbol, token, data)
            if not ok:
                logger.warning("[SCAM GATE] %s rad: %s", symbol, reason)
                return False, reason

        try:
            from buy.jupiter import get_quote
            from wallet.keypair import get_sol_price_usd

            sol_px = await get_sol_price_usd(session)
            if sol_px <= 0:
                sol_px = 150.0
            test_usd = min(1.0, float(settings.TRADE_AMOUNT_USD or 1.0))
            lamports = max(int((test_usd / sol_px) * 1_000_000_000), 10_000)
            quote = await get_quote(
                session,
                input_mint="So11111111111111111111111111111111111111112",
                output_mint=token,
                amount_lamports=lamports,
                slippage_bps=min(int(settings.SLIPPAGE_BPS or 300), 800),
            )
            if not quote:
                return False, "Jupiter quote yo'q — savdo qilib bo'lmaydi (scam/liq)"
            impact = safe_float(quote.get("priceImpactPct"))
            if impact > 8.0:
                if settings.AUTO_BLACKLIST_ENABLED and impact > 15.0:
                    self.blacklist.add(token, f"high_impact_{impact:.0f}", source="scam_gate")
                return False, f"Price impact juda baland: {impact:.1f}%"
            out_amt = int(quote.get("outAmount") or 0)
            if out_amt <= 0:
                return False, "Jupiter outAmount=0 — token savdo qilib bo'lmaydi"
        except Exception as e:
            logger.warning("[SCAM GATE] Jupiter tekshiruv xato %s: %s", symbol, e)
            if not settings.PAPER_TRADING:
                return False, f"Pre-buy tekshiruv xato: {e}"

        return True, "OK"

    def _reject(self, symbol: str, token: str, stage: str, reason: str):
        history.add_rejection(symbol, token, stage, reason)
        logger.info(f"[REJECT] {symbol} → {stage}: {reason}")
