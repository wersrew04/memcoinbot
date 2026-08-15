"""Buy executor – filterdan o'tgan tokenni xarid qilish."""
from __future__ import annotations

from typing import Any, Dict, Optional
from utils.logger import logger
from utils.helpers import utc_now, safe_float, safe_int
from config.settings import settings
from risk.manager import RiskManager
from buy.jupiter import JupiterSwap
from wallet.keypair import load_keypair
from wallet.rpc import SolanaRPC


class BuyExecutor:
    def __init__(
        self,
        risk: RiskManager,
        jupiter: Optional[JupiterSwap] = None,
        rpc: Optional[SolanaRPC] = None,
        telegram=None,
        advanced_risk=None,
        mev=None,
        portfolio=None,
        notifications=None,
    ):
        self.risk = risk
        self.rpc = rpc or SolanaRPC()
        self.jupiter = jupiter or JupiterSwap(self.rpc)
        self.telegram = telegram
        self.advanced_risk = advanced_risk
        self.mev = mev
        self.portfolio = portfolio
        self.notifications = notifications
        self.keypair = load_keypair()

    async def try_buy(self, token_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Risk check + MEV + portfolio + buy. Muvaffaqiyatli bo'lsa position qaytaradi.
        """
        token = token_data.get("token_address") or token_data.get("address")
        if not token:
            return None

        symbol = (
            token_data.get("token_symbol")
            or (token_data.get("birdeye_overview") or {}).get("symbol")
            or token[:8]
        )
        amount_usd = min(settings.TRADE_AMOUNT_USD, settings.MAX_RISK_PER_TOKEN_USD)

        # Advanced risk (falls back to base)
        if self.advanced_risk:
            ok, reason = await self.advanced_risk.pre_trade_check(token, amount_usd)
        else:
            ok, reason = await self.risk.pre_trade_check(token, amount_usd)
        if not ok:
            logger.info(f"Buy skip {symbol}: {reason}")
            return None

        if self.portfolio:
            ok_p, reason_p = await self.portfolio.can_allocate(amount_usd)
            if not ok_p:
                logger.info(f"Buy skip {symbol}: {reason_p}")
                return None

        # MEV protection
        if self.mev:
            liq = safe_float(token_data.get("liquidity_usd"))
            vol5 = safe_float(token_data.get("volume_5m"))
            safe, mev_reason, meta = self.mev.assess_risk(
                token, liquidity_usd=liq, volume_5m=vol5
            )
            if not safe:
                logger.warning(f"Buy skip {symbol}: {mev_reason}")
                return None

        kp = load_keypair()
        if not kp and not settings.PAPER_TRADING:
            logger.error("Keypair yo'q – real buy mumkin emas")
            return None

        # Decimals
        decimals = safe_int(
            (token_data.get("birdeye_overview") or {}).get("decimals")
            or token_data.get("decimals")
            or 6
        )
        sol_price = await self.jupiter.get_sol_price_usd()

        # Paper uchun dummy keypair
        if settings.PAPER_TRADING and kp is None:
            from solders.keypair import Keypair
            kp = Keypair()  # ephemeral for paper

        success, result = await self.jupiter.buy_token(
            token_mint=token,
            amount_usd=amount_usd,
            keypair=kp,
            sol_price_usd=sol_price,
            token_decimals=decimals,
        )
        if not success:
            logger.warning(f"Buy failed {symbol}: {result.get('error')}")
            return None

        entry_price = safe_float(result.get("entry_price"))
        tokens = safe_float(result.get("tokens_received"))
        # agar quote dan price_usd bo'lsa
        if entry_price <= 0:
            entry_price = safe_float(token_data.get("price_usd"))

        position = {
            "token": token,
            "symbol": symbol,
            "entry_price": entry_price,
            "amount_usd": amount_usd,
            "tokens": tokens,
            "tokens_raw": int(tokens * (10 ** decimals)) if tokens else 0,
            "decimals": decimals,
            "entry_tx": result.get("tx"),
            "entry_time": utc_now().isoformat(),
            "highest_price": entry_price,
            "stop_loss": entry_price * (1 - settings.STOP_LOSS_PCT),
            "take_profit": entry_price * (1 + settings.TAKE_PROFIT_PCT),
            "trailing_stop_pct": settings.TRAILING_STOP_PCT,
            "source": token_data.get("source"),
            "paper": settings.PAPER_TRADING,
            # AI learning uchun saqlanadi
            "ai_score": safe_float(token_data.get("ai_score")),
            "ai_factors": token_data.get("ai_factors") or {},
            "ai_recommendation": token_data.get("ai_recommendation"),
        }

        await self.risk.add_position(token, position)

        # Kunlik savdo hisoblagichi (ochilishda ham)
        if self.advanced_risk:
            self.advanced_risk._reset_daily_if_needed()
            self.advanced_risk.daily_trades += 1

        ai_score = safe_float(token_data.get("ai_score"))
        logger.info(
            f"✅ Position ochildi: {symbol} @ ${entry_price:.8f} | ${amount_usd} | "
            f"AI={ai_score:.1f} | {'PAPER' if settings.PAPER_TRADING else 'LIVE'}"
        )

        if self.telegram:
            await self.telegram.notify_trade_open(
                symbol=symbol,
                token=token,
                amount_usd=amount_usd,
                price=entry_price,
                tx=result.get("tx") or "",
            )
        if self.notifications:
            await self.notifications.notify_buy(
                symbol=symbol,
                token=token,
                amount=amount_usd,
                score=ai_score,
                tx=result.get("tx") or "",
            )
        return position
