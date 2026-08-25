"""Jupiter V6 API — quote olish, swap tranzaksiyasini yaratish va yuborish."""
from __future__ import annotations
import asyncio
import base64
import aiohttp
from typing import Any, Dict, Optional, Tuple
from utils.logger import logger
from utils.helpers import safe_float
from config.settings import settings

# Eski quote-api.jup.ag/v6 2025-oktyabrda deprecat qilindi.
# Yangi endpointlar (API key ixtiyoriy — lite; to'liq limit uchun portal.jup.ag):
JUPITER_QUOTE_URL = "https://lite-api.jup.ag/swap/v1/quote"
JUPITER_SWAP_URL  = "https://lite-api.jup.ag/swap/v1/swap"
# API key bo'lsa pro endpoint (yuqori rate limit):
JUPITER_QUOTE_URL_PRO = "https://api.jup.ag/swap/v1/quote"
JUPITER_SWAP_URL_PRO  = "https://api.jup.ag/swap/v1/swap"
SOL_MINT = "So11111111111111111111111111111111111111112"
LAMPORTS = 1_000_000_000  # 1 SOL


def _jupiter_headers() -> Dict[str, str]:
    headers: Dict[str, str] = {}
    if settings.JUPITER_API_KEY:
        # Yangi API x-api-key ishlatadi; eski Bearer ham qoldiriladi.
        headers["x-api-key"] = settings.JUPITER_API_KEY
        headers["Authorization"] = "Bearer {}".format(settings.JUPITER_API_KEY)
    return headers


def _quote_url() -> str:
    return JUPITER_QUOTE_URL_PRO if settings.JUPITER_API_KEY else JUPITER_QUOTE_URL


def _swap_url() -> str:
    return JUPITER_SWAP_URL_PRO if settings.JUPITER_API_KEY else JUPITER_SWAP_URL


async def get_quote(
    session: aiohttp.ClientSession,
    input_mint: str,
    output_mint: str,
    amount_lamports: int,
    slippage_bps: int = 300,
) -> Optional[Dict]:
    """Jupiter dan swap quote olish."""
    params = {
        "inputMint": input_mint,
        "outputMint": output_mint,
        "amount": str(amount_lamports),
        "slippageBps": str(slippage_bps),
        "onlyDirectRoutes": "false",
        "asLegacyTransaction": "false",
    }
    headers = _jupiter_headers()

    try:
        async with session.get(
            _quote_url(), params=params, headers=headers,
            timeout=aiohttp.ClientTimeout(total=15)
        ) as r:
            if r.status != 200:
                text = await r.text()
                logger.warning("Jupiter quote {} xato: {}".format(r.status, text[:200]))
                return None
            return await r.json()
    except Exception as e:
        logger.error("Jupiter quote xato: {}".format(e))
        return None


async def get_swap_transaction(
    session: aiohttp.ClientSession,
    quote: Dict,
    user_pubkey: str,
    priority_fee: int = 50_000,
) -> Optional[str]:
    """
    Jupiter dan swap tranzaksiyasini olish.
    Returns: base64 encoded serialized transaction
    """
    headers = {"Content-Type": "application/json"}
    headers.update(_jupiter_headers())

    body = {
        "quoteResponse": quote,
        "userPublicKey": user_pubkey,
        "wrapAndUnwrapSol": True,
        "dynamicComputeUnitLimit": True,
        "prioritizationFeeLamports": priority_fee,
        "asLegacyTransaction": False,
    }
    try:
        async with session.post(
            _swap_url(), json=body, headers=headers,
            timeout=aiohttp.ClientTimeout(total=20)
        ) as r:
            if r.status != 200:
                text = await r.text()
                logger.warning("Jupiter swap tx {} xato: {}".format(r.status, text[:200]))
                return None
            data = await r.json()
            return data.get("swapTransaction")
    except Exception as e:
        logger.error("Jupiter swap tx xato: {}".format(e))
        return None


async def send_transaction(
    session: aiohttp.ClientSession,
    signed_tx_b64: str,
    max_retries: int = 3,
) -> Optional[str]:
    """
    Imzolangan tranzaksiyani Solana RPC ga yuborish.
    Returns: tx signature yoki None
    """
    for attempt in range(max_retries):
        try:
            payload = {
                "jsonrpc": "2.0", "id": 1,
                "method": "sendTransaction",
                "params": [
                    signed_tx_b64,
                    {
                        "encoding": "base64",
                        "skipPreflight": True,
                        "preflightCommitment": "confirmed",
                        "maxRetries": 3,
                    }
                ]
            }
            async with session.post(
                settings.RPC_URL, json=payload,
                timeout=aiohttp.ClientTimeout(total=30)
            ) as r:
                data = await r.json()
                if "error" in data:
                    err = data["error"]
                    logger.warning("RPC sendTransaction xato ({}): {}".format(attempt+1, err))
                    if attempt < max_retries - 1:
                        await asyncio.sleep(1.5 * (attempt + 1))
                        continue
                    return None
                sig = data.get("result")
                if sig:
                    logger.info("TX yuborildi: {}".format(sig))
                    return sig
        except Exception as e:
            logger.error("sendTransaction xato ({}): {}".format(attempt+1, e))
            if attempt < max_retries - 1:
                await asyncio.sleep(1.5 * (attempt + 1))
    return None


async def confirm_transaction(
    session: aiohttp.ClientSession,
    signature: str,
    timeout_sec: int = 60,
) -> bool:
    """Tranzaksiya tasdiqlanishini kutish."""
    deadline = asyncio.get_event_loop().time() + timeout_sec
    while asyncio.get_event_loop().time() < deadline:
        try:
            payload = {
                "jsonrpc": "2.0", "id": 1,
                "method": "getSignatureStatuses",
                "params": [[signature], {"searchTransactionHistory": True}]
            }
            async with session.post(
                settings.RPC_URL, json=payload,
                timeout=aiohttp.ClientTimeout(total=10)
            ) as r:
                data = await r.json()
                statuses = (data.get("result") or {}).get("value") or []
                if statuses and statuses[0]:
                    status = statuses[0]
                    if status.get("err"):
                        logger.error("TX xato bilan tugadi: {}".format(status["err"]))
                        return False
                    conf = status.get("confirmationStatus")
                    if conf in ("confirmed", "finalized"):
                        logger.info("TX tasdiqlandi: {}".format(signature[:16] + "..."))
                        return True
        except Exception as e:
            logger.debug("TX status tekshiruv xato: {}".format(e))
        await asyncio.sleep(3)
    logger.warning("TX tasdiq vaqti tugadi: {}".format(signature[:16]))
    return False


async def sign_and_send(
    session: aiohttp.ClientSession,
    swap_tx_b64: str,
    keypair,
    max_retries: int = 3,
) -> Optional[str]:
    """
    Tranzaksiyani sign qilib yuborish.
    Returns: tx signature yoki None
    """
    try:
        from solders.transaction import VersionedTransaction
        from solders.keypair import Keypair

        raw = base64.b64decode(swap_tx_b64)
        tx = VersionedTransaction.from_bytes(raw)

        # Sign
        signed = VersionedTransaction(tx.message, [keypair])
        signed_b64 = base64.b64encode(bytes(signed)).decode()

        sig = await send_transaction(session, signed_b64, max_retries)
        return sig
    except ImportError:
        logger.error("solders kutubxonasi topilmadi: pip install solders")
        return None
    except Exception as e:
        logger.error("sign_and_send xato: {}".format(e))
        return None
