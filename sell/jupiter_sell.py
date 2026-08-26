"""
Jupiter orqali token → SOL sotish.
Har urinishda yangi quote + oshirilgan slippage (Custom 6024 = slippage).
"""
from __future__ import annotations

import aiohttp
from typing import Optional, Tuple

from utils.logger import logger
from utils.helpers import safe_float
from config.settings import settings

SOL_MINT = "So11111111111111111111111111111111111111112"


async def execute_sell(
    session: aiohttp.ClientSession,
    token: str,
    symbol: str,
    raw_amount: int,
    slippage_bps: int = None,
) -> Tuple[bool, str, float]:
    """
    Token → SOL.
    Returns: (success, tx_signature, sol_received)
    """
    from buy.jupiter import get_quote, get_swap_transaction, sign_and_send, confirm_transaction
    from wallet.keypair import get_keypair

    if settings.PAPER_TRADING:
        logger.info("[PAPER SELL] {} {} raw tokens".format(symbol, raw_amount))
        return True, "PAPER_SELL", 0.0

    keypair = get_keypair()
    if not keypair:
        return False, "", 0.0

    pubkey = str(keypair.pubkey())
    base_slip = slippage_bps or settings.SLIPPAGE_BPS
    attempts = max(1, int(getattr(settings, "SELL_RETRY_ATTEMPTS", 3) or 3))

    # Meme coin sell: slippage bosqichma-bosqich oshadi
    # 6024 = ko'pincha SlippageToleranceExceeded
    slip_steps = [
        base_slip,
        min(base_slip + 200, 1500),
        min(base_slip + 500, 2000),
        min(base_slip + 800, 2500),
    ]

    last_sol = 0.0
    for attempt in range(attempts):
        slip = slip_steps[min(attempt, len(slip_steps) - 1)]
        priority = int(getattr(settings, "PRIORITY_FEE_MICROLAMPORTS", 50000) or 50000)
        # Har urinishda priority biroz oshadi
        priority = priority + attempt * 50_000

        quote = await get_quote(
            session,
            input_mint=token,
            output_mint=SOL_MINT,
            amount_lamports=raw_amount,
            slippage_bps=slip,
        )
        if not quote:
            logger.warning(
                "[LIVE SELL] Jupiter quote xato: {} (attempt {}, slip={}bps)",
                symbol, attempt + 1, slip,
            )
            continue

        out_lamports = int(quote.get("outAmount") or 0)
        last_sol = out_lamports / 1_000_000_000
        impact = safe_float(quote.get("priceImpactPct"))
        if impact > 25.0:
            logger.warning(
                "[LIVE SELL] {} price impact {:.1f}% — davom etamiz (sotish majburiy)",
                symbol, impact,
            )

        swap_tx = await get_swap_transaction(
            session, quote, pubkey, priority_fee=priority,
        )
        if not swap_tx:
            logger.warning("[LIVE SELL] swap tx yo'q: {} attempt {}", symbol, attempt + 1)
            continue

        sig = await sign_and_send(session, swap_tx, keypair, max_retries=2)
        if not sig:
            logger.warning("[LIVE SELL] TX yuborilmadi ({}) {}", attempt + 1, symbol)
            continue

        confirmed = await confirm_transaction(session, sig, timeout_sec=45)
        if confirmed:
            logger.info(
                "[LIVE SELL OK] {} SOL={:.6f} slip={}bps tx={}...",
                symbol, last_sol, slip, sig[:20],
            )
            return True, sig, last_sol

        logger.warning(
            "[LIVE SELL] Tasdiq yo'q/on-chain xato ({}/{}): {} slip={}bps — yangi quote",
            attempt + 1, attempts, sig[:20], slip,
        )

    logger.error("[LIVE SELL FAIL] {} — {} urinishdan keyin", symbol, attempts)
    return False, "", last_sol


async def get_token_raw_amount(
    session: aiohttp.ClientSession,
    token_mint: str,
    owner: str = "",
) -> int:
    """Hamyondagi token raw miqdorini olish."""
    from wallet.keypair import get_token_balance
    _, raw = await get_token_balance(session, token_mint, owner)
    return raw
