"""Solana wallet — keypair, pubkey, SOL balansi."""
from __future__ import annotations
import asyncio
import aiohttp
from typing import Optional, Tuple
from utils.logger import logger
from config.settings import settings

def get_keypair():
    """Private key dan keypair yuklash."""
    pk = settings.PRIVATE_KEY
    if not pk:
        return None
    try:
        from solders.keypair import Keypair
        kp = Keypair.from_base58_string(pk)
        return kp
    except ImportError:
        logger.warning("solders o'rnatilmagan — pip install solders")
        return None
    except Exception as e:
        logger.error("Keypair yuklash xato: {}".format(e))
        return None


def get_pubkey() -> str:
    kp = get_keypair()
    if not kp:
        return ""
    try:
        return str(kp.pubkey())
    except Exception:
        return ""


async def get_sol_balance(session: aiohttp.ClientSession, pubkey: str = "") -> float:
    """Hamyondagi SOL balansini olish (RPC orqali)."""
    if not pubkey:
        pubkey = get_pubkey()
    if not pubkey:
        return 0.0
    payload = {
        "jsonrpc": "2.0", "id": 1,
        "method": "getBalance",
        "params": [pubkey, {"commitment": "confirmed"}]
    }
    try:
        async with session.post(
            settings.RPC_URL, json=payload,
            timeout=aiohttp.ClientTimeout(total=10)
        ) as r:
            if r.status != 200:
                return 0.0
            data = await r.json()
            lamports = data.get("result", {}).get("value", 0)
            return lamports / 1_000_000_000  # lamports → SOL
    except Exception as e:
        logger.warning("SOL balans xato: {}".format(e))
        return 0.0


async def get_token_balance(
    session: aiohttp.ClientSession,
    token_mint: str,
    owner: str = ""
) -> Tuple[float, int]:
    """
    Hamyondagi token miqdorini olish.
    Returns: (ui_amount, raw_amount)
    """
    if not owner:
        owner = get_pubkey()
    if not owner:
        return 0.0, 0

    payload = {
        "jsonrpc": "2.0", "id": 1,
        "method": "getTokenAccountsByOwner",
        "params": [
            owner,
            {"mint": token_mint},
            {"encoding": "jsonParsed", "commitment": "confirmed"}
        ]
    }
    try:
        async with session.post(
            settings.RPC_URL, json=payload,
            timeout=aiohttp.ClientTimeout(total=10)
        ) as r:
            if r.status != 200:
                return 0.0, 0
            data = await r.json()
            accounts = data.get("result", {}).get("value", [])
            if not accounts:
                return 0.0, 0
            info = accounts[0]["account"]["data"]["parsed"]["info"]["tokenAmount"]
            ui_amount = float(info.get("uiAmount") or 0)
            raw = int(info.get("amount") or 0)
            return ui_amount, raw
    except Exception as e:
        logger.warning("Token balans xato {}: {}".format(token_mint[:8], e))
        return 0.0, 0


TOKEN_PROGRAM_ID = "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"


async def get_all_token_holdings(
    session: aiohttp.ClientSession,
    owner: str = ""
) -> list:
    """
    Hamyondagi BARCHA SPL tokenlarni (mint + miqdor) qaytaradi.
    Restart'dan keyin RAM'dagi pozitsiyalar yo'qolgan/eskirgan bo'lsa,
    haqiqiy on-chain holatni tekshirish uchun ishlatiladi.
    Returns: [{"mint": str, "ui_amount": float, "raw_amount": int}, ...]
    """
    if not owner:
        owner = get_pubkey()
    if not owner:
        return []

    payload = {
        "jsonrpc": "2.0", "id": 1,
        "method": "getTokenAccountsByOwner",
        "params": [
            owner,
            {"programId": TOKEN_PROGRAM_ID},
            {"encoding": "jsonParsed", "commitment": "confirmed"}
        ]
    }
    try:
        async with session.post(
            settings.RPC_URL, json=payload,
            timeout=aiohttp.ClientTimeout(total=15)
        ) as r:
            if r.status != 200:
                return []
            data = await r.json()
            accounts = data.get("result", {}).get("value", [])
            holdings = []
            for acc in accounts:
                try:
                    info = acc["account"]["data"]["parsed"]["info"]
                    amount_info = info["tokenAmount"]
                    ui_amount = float(amount_info.get("uiAmount") or 0)
                    if ui_amount <= 0:
                        continue
                    holdings.append({
                        "mint": info.get("mint", ""),
                        "ui_amount": ui_amount,
                        "raw_amount": int(amount_info.get("amount") or 0),
                    })
                except Exception:
                    continue
            return holdings
    except Exception as e:
        logger.warning("Token holdings ro'yxatini olishda xato: {}".format(e))
        return []


async def get_sol_price_usd(session: aiohttp.ClientSession) -> float:
    """SOL/USD narxini olish."""
    try:
        url = "https://api.coingecko.com/api/v3/simple/price?ids=solana&vs_currencies=usd"
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=8)) as r:
            if r.status != 200:
                return 150.0  # fallback
            data = await r.json()
            return float(data.get("solana", {}).get("usd", 150.0))
    except Exception:
        return 150.0
