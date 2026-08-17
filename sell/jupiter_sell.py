"""
Jupiter orqali token → SOL sotish.
"""
from __future__ import annotations
import aiohttp
from typing import Optional, Tuple
from utils.logger import logger
from utils.helpers import safe_float
from config.settings import settings


async def execute_sell(
    session: aiohttp.ClientSession,
    token: str,
    symbol: str,
    raw_amount: int,
    slippage_bps: int = None,
) -> Tuple[bool, str, float]:
    """
    Token larni SOL ga sotish.

    Args:
        raw_amount : token raw miqdori (onchain, decimals bilan)

    Returns: (success, tx_signature, sol_received)
    """
    from buy.jupiter import get_quote, get_swap_transaction, sign_and_send, confirm_transaction
    from wallet.keypair import get_keypair, get_sol_price_usd

    if settings.PAPER_TRADING:
        logger.info("[PAPER SELL] {} {} raw tokens".format(symbol, raw_amount))
        return True, "PAPER_SELL", 0.0

    keypair = get_keypair()
    if not keypair:
        return False, "", 0.0

    pubkey = str(keypair.pubkey())
    slippage = slippage_bps or settings.SLIPPAGE_BPS

    # Quote: token → SOL
    quote = await get_quote(
        session,
        input_mint=token,
        output_mint="So11111111111111111111111111111111111111112",
        amount_lamports=raw_amount,
        slippage_bps=slippage,
    )
    if not quote:
        logger.warning("[LIVE SELL] Jupiter quote xato: {}".format(symbol))
        return False, "", 0.0

    out_lamports = int(quote.get("outAmount") or 0)
    sol_received = out_lamports / 1_000_000_000

    # Swap tranzaksiyasi
    swap_tx = await get_swap_transaction(
        session, quote, pubkey,
        priority_fee=settings.PRIORITY_FEE_MICROLAMPORTS,
    )
    if not swap_tx:
        return False, "", 0.0

    # Sign va yuborish
    for attempt in range(settings.SELL_RETRY_ATTEMPTS):
        sig = await sign_and_send(session, swap_tx, keypair)
        if sig:
            confirmed = await confirm_transaction(session, sig, timeout_sec=60)
            if confirmed:
                logger.info("[LIVE SELL OK] {} SOL={:.4f} tx={}".format(
                    symbol, sol_received, sig[:20] + "..."
                ))
                return True, sig, sol_received
            else:
                logger.warning("[LIVE SELL] Tasdiq yo'q ({}): {}".format(attempt+1, sig[:20]))
        else:
            logger.warning("[LIVE SELL] TX yuborilmadi ({}), qayta urinish...".format(attempt+1))

    return False, "", 0.0


async def get_token_raw_amount(
    session: aiohttp.ClientSession,
    token_mint: str,
    owner: str = "",
) -> int:
    """Hamyondagi token raw miqdorini olish."""
    from wallet.keypair import get_token_balance
    _, raw = await get_token_balance(session, token_mint, owner)
    return raw
