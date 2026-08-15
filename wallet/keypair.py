"""Solana keypair yuklash va asosiy wallet utilitlar."""
from __future__ import annotations

from typing import Optional, Tuple
from solders.keypair import Keypair
from solders.pubkey import Pubkey
import base58
from utils.logger import logger
from config.settings import settings


def load_keypair(private_key: Optional[str] = None) -> Optional[Keypair]:
    """
    Phantom / Solflare base58 private key yoki byte array JSON dan Keypair.
    """
    pk = (private_key or settings.PRIVATE_KEY or "").strip()
    if not pk:
        logger.warning("PRIVATE_KEY bo'sh – wallet ishlamaydi")
        return None

    try:
        # base58 string (Phantom export)
        if pk.startswith("["):
            # JSON byte array: [1,2,3,...]
            import json
            secret = bytes(json.loads(pk))
            return Keypair.from_bytes(secret)
        secret = base58.b58decode(pk)
        if len(secret) == 64:
            return Keypair.from_bytes(secret)
        if len(secret) == 32:
            return Keypair.from_seed(secret)
        # ba'zi exportlar 64 byte raw
        return Keypair.from_bytes(secret[:64])
    except Exception as e:
        logger.error(f"Keypair yuklash xato: {e}")
        return None


def get_pubkey(keypair: Optional[Keypair] = None) -> Optional[str]:
    kp = keypair or load_keypair()
    if not kp:
        return None
    return str(kp.pubkey())


def pubkey_from_str(address: str) -> Pubkey:
    return Pubkey.from_string(address)
