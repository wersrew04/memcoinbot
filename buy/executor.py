"""
Xarid executor.

Paper rejim  : haqiqiy tranzaksiya yo'q, faqat simulyatsiya.
Live rejim   : Jupiter V6 → sign → RPC → confirm.
"""
from __future__ import annotations
import asyncio
import aiohttp
from typing import Dict, Tuple
from utils.logger import logger
from utils.helpers import safe_float, utc_now
from config.settings import settings

SOL_MIN_RESERVE = 0.08  # gas + priority + ATA   # Gaz uchun doim saqlab qolish kerak bo'lgan SOL


async def execute_buy(
    token: str,
    symbol: str,
    amount_usd: float,
    current_price: float,
    session: aiohttp.ClientSession,
    paper: bool = True,
) -> Tuple[bool, Dict]:
    """
    Returns: (success, position_data)
    """
    if paper or settings.PAPER_TRADING:
        return await _paper_buy(token, symbol, amount_usd, current_price)
    return await _live_buy(token, symbol, amount_usd, current_price, session)


# ─────────────────── PAPER ───────────────────

async def _paper_buy(
    token: str, symbol: str, amount_usd: float, price: float
) -> Tuple[bool, Dict]:
    if price <= 0:
        return False, {"error": "Narx 0"}

    position = {
        "token": token,
        "symbol": symbol,
        "amount_usd": amount_usd,
        "tokens_amount": amount_usd / price,
        "entry_price": price,
        "current_price": price,
        "high_price": price,
        "paper": True,
        "tx_hash": "PAPER_{}".format(utc_now().strftime("%H%M%S%f")[:12]),
    }
    logger.info("[PAPER BUY] {} ${:.2f} @ ${:.10f}".format(symbol, amount_usd, price))
    return True, position


# ─────────────────── LIVE ────────────────────

async def _live_buy(
    token: str, symbol: str, amount_usd: float,
    price: float, session: aiohttp.ClientSession
) -> Tuple[bool, Dict]:
    from wallet.keypair import get_keypair, get_sol_balance, get_sol_price_usd
    from buy.jupiter import get_quote, get_swap_transaction, sign_and_send, confirm_transaction

    keypair = get_keypair()
    if not keypair:
        logger.error("Private key topilmadi — live xarid imkonsiz")
        return False, {"error": "Private key yo'q"}

    pubkey = str(keypair.pubkey())

    # SOL balansini tekshirish
    sol_balance = await get_sol_balance(session, pubkey)
    sol_price = await get_sol_price_usd(session)
    if sol_price <= 0:
        sol_price = 150.0  # fallback to avoid division by zero

    sol_needed = (amount_usd / sol_price) + SOL_MIN_RESERVE
    if sol_balance < sol_needed:
        msg = "Yetarli SOL yo'q: {:.4f} SOL bor, {:.4f} kerak".format(
            sol_balance, sol_needed
        )
        logger.warning("[LIVE BUY] {}".format(msg))
        return False, {"error": msg}

    # SOL miqdorini lamports ga aylantirish
    sol_amount = amount_usd / sol_price
    lamports = int(sol_amount * 1_000_000_000)

    logger.info("[LIVE BUY] {} — ${:.2f} ({:.6f} SOL = {} lamports)".format(
        symbol, amount_usd, sol_amount, lamports
    ))

    # Jupiter quote
    slippage = settings.SLIPPAGE_BPS
    quote = await get_quote(
        session,
        input_mint="So11111111111111111111111111111111111111112",
        output_mint=token,
        amount_lamports=lamports,
        slippage_bps=slippage,
    )
    if not quote:
        return False, {"error": "Jupiter quote xato"}

    out_amount = int(quote.get("outAmount") or 0)
    price_impact = safe_float(quote.get("priceImpactPct"))
    if price_impact > 5.0:
        logger.warning("[LIVE BUY] Price impact juda baland: {:.2f}%".format(price_impact))
        return False, {"error": "Price impact {:.1f}% > 5%".format(price_impact)}

    # Swap tranzaksiyasini yaratish
    swap_tx = await get_swap_transaction(
        session, quote, pubkey,
        priority_fee=settings.PRIORITY_FEE_MICROLAMPORTS,
    )
    if not swap_tx:
        return False, {"error": "Swap tranzaksiya yaratilmadi"}

    # MEV himoya: dinamik slippage
    if settings.MEV_PROTECTION_ENABLED and settings.MEV_DYNAMIC_SLIPPAGE:
        slippage = min(slippage + 50, settings.MEV_MAX_SLIPPAGE_BPS)

    # Imzolash va yuborish
    sig = await sign_and_send(session, swap_tx, keypair, max_retries=settings.MEV_RETRY_ATTEMPTS)
    if not sig:
        return False, {"error": "Tranzaksiya yuborilmadi"}

    # Tasdiqlash
    confirmed = await confirm_transaction(session, sig, timeout_sec=60)
    if not confirmed:
        logger.warning("[LIVE BUY] TX tasdiqlanmadi: {}".format(sig[:20]))
        # TX yuborilgan, lekin tasdiq yo'q — konservativ: xato qaytaramiz
        return False, {"error": "TX tasdiqlanmadi: {}".format(sig)}

    # out_amount = raw (decimals bilan). Jupiter ba'zan outputDecimals bermaydi.
    decimals = 6
    try:
        decimals = int(quote.get("outputDecimals") or quote.get("outDecimals") or 6)
        # routePlan ichidan ham qidirish
        if not quote.get("outputDecimals"):
            for rp in (quote.get("routePlan") or []):
                swap_info = (rp.get("swapInfo") or {})
                if swap_info.get("outputMint") == token or swap_info.get("outMint") == token:
                    pass
    except Exception:
        decimals = 6

    human_tokens = out_amount / (10 ** decimals) if out_amount > 0 else 0.0
    # Haqiqiy entry: sarflangan USD / olingan token
    actual_price = price
    if human_tokens > 0 and amount_usd > 0:
        actual_price = amount_usd / human_tokens
    elif human_tokens > 0 and sol_amount > 0:
        actual_price = (sol_amount * sol_price) / human_tokens

    position = {
        "token": token,
        "symbol": symbol,
        "amount_usd": amount_usd,
        "tokens_amount": out_amount,  # raw — sell uchun
        "tokens_ui": human_tokens,
        "token_decimals": decimals,
        "entry_price": actual_price,
        "current_price": actual_price,
        "high_price": actual_price,
        "paper": False,
        "tx_hash": sig,
        "sol_spent": sol_amount,
        "price_impact": price_impact,
    }
    logger.info("[LIVE BUY OK] {} tx={}".format(symbol, sig[:20] + "..."))
    return True, position
