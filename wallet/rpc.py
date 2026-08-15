"""Solana RPC client – balance, token account, tx yuborish."""
from __future__ import annotations

from typing import Any, Dict, List, Optional
from solders.keypair import Keypair
from solders.transaction import VersionedTransaction
from solders.signature import Signature
from solana.rpc.async_api import AsyncClient
from solana.rpc.commitment import Confirmed, Processed
from solana.rpc.types import TxOpts
from utils.logger import logger
from config.settings import settings
from config.constants import SOL_MINT, USDC_MINT


class SolanaRPC:
    def __init__(self, rpc_url: Optional[str] = None):
        self.rpc_url = rpc_url or settings.RPC_URL
        self._client: Optional[AsyncClient] = None

    async def connect(self) -> AsyncClient:
        if self._client is None:
            self._client = AsyncClient(self.rpc_url, commitment=Confirmed)
        return self._client

    async def close(self):
        if self._client:
            await self._client.close()
            self._client = None

    async def get_sol_balance(self, pubkey: str) -> float:
        """SOL balance (native)."""
        client = await self.connect()
        from solders.pubkey import Pubkey
        resp = await client.get_balance(Pubkey.from_string(pubkey))
        lamports = resp.value or 0
        return lamports / 1e9

    async def get_token_balance(self, owner: str, mint: str) -> float:
        """SPL token balance (ui amount)."""
        client = await self.connect()
        from solders.pubkey import Pubkey
        try:
            resp = await client.get_token_accounts_by_owner_json_parsed(
                Pubkey.from_string(owner),
                {"mint": Pubkey.from_string(mint)},
            )
            if not resp.value:
                return 0.0
            total = 0.0
            for acc in resp.value:
                info = acc.account.data.parsed.get("info", {})
                amount = info.get("tokenAmount", {}).get("uiAmount")
                if amount is not None:
                    total += float(amount)
            return total
        except Exception as e:
            logger.debug(f"Token balance xato {mint}: {e}")
            return 0.0

    async def send_versioned_tx(
        self,
        tx_bytes: bytes,
        signer: Keypair,
        max_retries: int = 3,
    ) -> Optional[str]:
        """
        Jupiter dan kelgan serialized VersionedTransaction ni imzolab yuborish.
        Returns signature string yoki None.
        """
        if settings.PAPER_TRADING:
            logger.info("[PAPER] Tx yuborilmadi (paper trading)")
            return "PAPER_" + "0" * 40

        client = await self.connect()
        try:
            raw_tx = VersionedTransaction.from_bytes(tx_bytes)
            # message ni imzolash
            signed = VersionedTransaction(raw_tx.message, [signer])
            opts = TxOpts(skip_preflight=False, preflight_commitment=Processed)
            for attempt in range(max_retries):
                try:
                    resp = await client.send_raw_transaction(
                        bytes(signed),
                        opts=opts,
                    )
                    sig = str(resp.value)
                    logger.info(f"Tx yuborildi: {sig}")
                    # confirmation kutish (qisqa)
                    await client.confirm_transaction(Signature.from_string(sig), commitment=Confirmed)
                    return sig
                except Exception as e:
                    logger.warning(f"Send attempt {attempt+1}/{max_retries}: {e}")
                    if attempt == max_retries - 1:
                        raise
            return None
        except Exception as e:
            logger.error(f"Tx yuborish xato: {e}")
            return None

    async def get_slot(self) -> Optional[int]:
        """Lightweight liveness probe used by HealthMonitor."""
        client = await self.connect()
        resp = await client.get_slot()
        return resp.value if resp else None

    async def get_recent_blockhash(self) -> Optional[str]:
        client = await self.connect()
        resp = await client.get_latest_blockhash()
        return str(resp.value.blockhash) if resp.value else None
