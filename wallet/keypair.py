"""Solana wallet — keypair, pubkey, SOL balansi, SPL + Token-2022 holdings."""
from __future__ import annotations
import asyncio
import aiohttp
from typing import Optional, Tuple, List, Dict
from utils.logger import logger
from config.settings import settings

# Classic SPL Token program
TOKEN_PROGRAM_ID = "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"
# Token-2022 (ko'p yangi memecoinlar shu programda)
TOKEN_2022_PROGRAM_ID = "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb"


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


async def _fetch_token_accounts_by_mint(
    session: aiohttp.ClientSession,
    owner: str,
    token_mint: str,
) -> Tuple[float, int]:
    """Bitta mint uchun balans (classic + Token-2022)."""
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
            if data.get("error"):
                logger.debug("getTokenAccountsByOwner error: %s", data["error"])
                return 0.0, 0
            accounts = data.get("result", {}).get("value", [])
            if not accounts:
                return 0.0, 0
            # Bir nechta account bo'lishi mumkin — yig'indisini olamiz
            total_ui = 0.0
            total_raw = 0
            for acc in accounts:
                try:
                    info = acc["account"]["data"]["parsed"]["info"]["tokenAmount"]
                    total_ui += float(info.get("uiAmount") or 0)
                    total_raw += int(info.get("amount") or 0)
                except Exception:
                    continue
            return total_ui, total_raw
    except Exception as e:
        logger.warning("Token balans xato {}: {}".format(token_mint[:8], e))
        return 0.0, 0


async def get_token_balance(
    session: aiohttp.ClientSession,
    token_mint: str,
    owner: str = ""
) -> Tuple[float, int]:
    """
    Hamyondagi token miqdorini olish (SPL + Token-2022).
    Returns: (ui_amount, raw_amount)
    """
    if not owner:
        owner = get_pubkey()
    if not owner:
        return 0.0, 0
    # mint filter ishlatilganda programId kerak emas — RPC ikkala programni ham qaytaradi
    return await _fetch_token_accounts_by_mint(session, owner, token_mint)


async def _fetch_holdings_for_program(
    session: aiohttp.ClientSession,
    owner: str,
    program_id: str,
) -> List[Dict]:
    """Berilgan token program bo'yicha barcha holdinglarni olish."""
    payload = {
        "jsonrpc": "2.0", "id": 1,
        "method": "getTokenAccountsByOwner",
        "params": [
            owner,
            {"programId": program_id},
            {"encoding": "jsonParsed", "commitment": "confirmed"}
        ]
    }
    try:
        async with session.post(
            settings.RPC_URL, json=payload,
            timeout=aiohttp.ClientTimeout(total=20)
        ) as r:
            if r.status != 200:
                body = await r.text()
                logger.warning(
                    "Token holdings HTTP {}: {} (program={})".format(
                        r.status, body[:120], program_id[:12]
                    )
                )
                return []
            data = await r.json()
            if data.get("error"):
                logger.warning(
                    "Token holdings RPC error ({}): {}".format(
                        program_id[:12], data["error"]
                    )
                )
                return []
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
                        "decimals": int(amount_info.get("decimals") or 0),
                        "program": program_id,
                    })
                except Exception:
                    continue
            return holdings
    except Exception as e:
        logger.warning(
            "Token holdings ro'yxatini olishda xato ({}): {}".format(
                program_id[:12], e
            )
        )
        return []


async def get_all_token_holdings(
    session: aiohttp.ClientSession,
    owner: str = ""
) -> list:
    """
    Hamyondagi BARCHA SPL + Token-2022 tokenlarni (mint + miqdor) qaytaradi.
    Restart'dan keyin RAM'dagi pozitsiyalar yo'qolgan/eskirgan bo'lsa,
    haqiqiy on-chain holatni tekshirish uchun ishlatiladi.
    Returns: [{"mint": str, "ui_amount": float, "raw_amount": int, ...}, ...]
    """
    if not owner:
        owner = get_pubkey()
    if not owner:
        return []

    # Parallel: classic Token + Token-2022
    classic, t2022 = await asyncio.gather(
        _fetch_holdings_for_program(session, owner, TOKEN_PROGRAM_ID),
        _fetch_holdings_for_program(session, owner, TOKEN_2022_PROGRAM_ID),
        return_exceptions=True,
    )
    if isinstance(classic, Exception):
        logger.warning("Classic token holdings xato: %s", classic)
        classic = []
    if isinstance(t2022, Exception):
        logger.warning("Token-2022 holdings xato: %s", t2022)
        t2022 = []

    # Mint bo'yicha birlashtirish (bir xil mint ikkala programda bo'lmasligi kerak, lekin himoya)
    by_mint: Dict[str, Dict] = {}
    for h in list(classic) + list(t2022):
        mint = h.get("mint") or ""
        if not mint:
            continue
        if mint in by_mint:
            by_mint[mint]["ui_amount"] = by_mint[mint].get("ui_amount", 0) + h.get("ui_amount", 0)
            by_mint[mint]["raw_amount"] = by_mint[mint].get("raw_amount", 0) + h.get("raw_amount", 0)
        else:
            by_mint[mint] = dict(h)
    return list(by_mint.values())


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
