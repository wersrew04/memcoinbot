"""Jupiter Aggregator – quote + swap (buy / sell)."""
from __future__ import annotations

import base64
from typing import Any, Dict, Optional, Tuple
import httpx
from solders.keypair import Keypair
from utils.logger import logger
from utils.retry import async_retry
from utils.helpers import safe_float
from config.settings import settings
from config.constants import JUPITER_QUOTE, JUPITER_SWAP, SOL_MINT, USDC_MINT
from wallet.rpc import SolanaRPC


class JupiterSwap:
    def __init__(self, rpc: Optional[SolanaRPC] = None):
        self.rpc = rpc or SolanaRPC()
        self.timeout = 30.0
        self.headers = {"Accept": "application/json", "Content-Type": "application/json"}
        if settings.JUPITER_API_KEY:
            self.headers["x-api-key"] = settings.JUPITER_API_KEY

    @async_retry(max_attempts=3)
    async def get_quote(
        self,
        input_mint: str,
        output_mint: str,
        amount: int,
        slippage_bps: Optional[int] = None,
        swap_mode: str = "ExactIn",
    ) -> Optional[Dict[str, Any]]:
        """
        amount – smallest units (lamports yoki token decimals).
        """
        params = {
            "inputMint": input_mint,
            "outputMint": output_mint,
            "amount": str(amount),
            "slippageBps": str(slippage_bps or settings.SLIPPAGE_BPS),
            "swapMode": swap_mode,
            "onlyDirectRoutes": "false",
            "asLegacyTransaction": "false",
        }
        async with httpx.AsyncClient(timeout=self.timeout, headers=self.headers) as client:
            resp = await client.get(JUPITER_QUOTE, params=params)
            if resp.status_code != 200:
                logger.warning(f"Jupiter quote {resp.status_code}: {resp.text[:200]}")
                return None
            return resp.json()

    @async_retry(max_attempts=2)
    async def get_swap_transaction(
        self,
        quote: Dict[str, Any],
        user_public_key: str,
        prioritization_fee_lamports: Optional[int] = None,
    ) -> Optional[bytes]:
        """Swap transaction (serialized base64) qaytaradi."""
        body = {
            "quoteResponse": quote,
            "userPublicKey": user_public_key,
            "wrapAndUnwrapSol": True,
            "dynamicComputeUnitLimit": True,
            "prioritizationFeeLamports": prioritization_fee_lamports
            or settings.PRIORITY_FEE_MICROLAMPORTS,
        }
        async with httpx.AsyncClient(timeout=self.timeout, headers=self.headers) as client:
            resp = await client.post(JUPITER_SWAP, json=body)
            if resp.status_code != 200:
                logger.warning(f"Jupiter swap {resp.status_code}: {resp.text[:300]}")
                return None
            data = resp.json()
            b64 = data.get("swapTransaction")
            if not b64:
                return None
            return base64.b64decode(b64)

    async def buy_token(
        self,
        token_mint: str,
        amount_usd: float,
        keypair: Keypair,
        sol_price_usd: float = 150.0,
        token_decimals: int = 6,
    ) -> Tuple[bool, Dict[str, Any]]:
        """
        SOL → Token swap.
        Returns (success, result_dict).
        """
        result: Dict[str, Any] = {
            "side": "buy",
            "token": token_mint,
            "amount_usd": amount_usd,
            "paper": settings.PAPER_TRADING,
        }
        if amount_usd <= 0:
            return False, {**result, "error": "amount_usd <= 0"}

        # SOL miqdori (lamports)
        sol_amount = amount_usd / max(sol_price_usd, 1.0)
        lamports = int(sol_amount * 1e9)
        if lamports < 10_000:  # ~0.00001 SOL
            return False, {**result, "error": "Juda kichik amount"}

        if not keypair:
            return False, {**result, "error": "Keypair taqdim etilmadi (None)"}

        user_pk = str(keypair.pubkey())

        # Live rejimda SOL balansini tekshirish (komissiya va buy hajmini qoplashiga ishonch hosil qilish)
        if not settings.PAPER_TRADING:
            try:
                sol_bal = await self.rpc.get_sol_balance(user_pk)
                needed = (lamports / 1e9) + 0.005  # 0.005 SOL komissiyalar uchun zaxira
                if sol_bal < needed:
                    err_msg = f"Balans yetarli emas: {sol_bal:.4f} SOL (Kerak: {needed:.4f} SOL)"
                    logger.warning(err_msg)
                    return False, {**result, "error": err_msg}
            except Exception as e:
                logger.warning(f"SOL balansini tekshirishda xato: {e}")

        quote = await self.get_quote(SOL_MINT, token_mint, lamports)
        if not quote:
            return False, {**result, "error": "Quote olinmadi"}

        out_amount = int(quote.get("outAmount") or 0)
        price_impact = safe_float(quote.get("priceImpactPct"))
        result["quote"] = {
            "in_amount": lamports,
            "out_amount": out_amount,
            "price_impact_pct": price_impact,
            "route": (quote.get("routePlan") or [])[:2],
        }

        if settings.PAPER_TRADING:
            # taxminiy entry price
            entry_price = (amount_usd / (out_amount / (10 ** token_decimals))) if out_amount else 0
            result.update({
                "success": True,
                "tx": "PAPER_BUY",
                "tokens_received": out_amount / (10 ** token_decimals) if token_decimals else out_amount,
                "entry_price": entry_price,
                "sol_spent": sol_amount,
            })
            logger.info(
                f"[PAPER BUY] {token_mint[:8]}... ${amount_usd:.2f} → "
                f"~{result['tokens_received']:.4f} tokens @ ${entry_price:.8f}"
            )
            return True, result

        tx_bytes = await self.get_swap_transaction(quote, user_pk)
        if not tx_bytes:
            return False, {**result, "error": "Swap tx olinmadi"}

        sig = await self.rpc.send_versioned_tx(tx_bytes, keypair)
        if not sig:
            return False, {**result, "error": "Tx yuborilmadi"}

        tokens_ui = out_amount / (10 ** token_decimals) if token_decimals else float(out_amount)
        entry_price = amount_usd / tokens_ui if tokens_ui else 0
        result.update({
            "success": True,
            "tx": sig,
            "tokens_received": tokens_ui,
            "entry_price": entry_price,
            "sol_spent": sol_amount,
        })
        logger.info(f"BUY OK {token_mint[:8]} tx={sig}")
        return True, result

    async def sell_token(
        self,
        token_mint: str,
        token_amount_raw: int,
        keypair: Keypair,
        token_decimals: int = 6,
        expected_usd: float = 0.0,
    ) -> Tuple[bool, Dict[str, Any]]:
        """
        Token → SOL swap (to'liq yoki qisman).
        token_amount_raw – smallest units.
        """
        result: Dict[str, Any] = {
            "side": "sell",
            "token": token_mint,
            "amount_raw": token_amount_raw,
            "paper": settings.PAPER_TRADING,
        }
        if token_amount_raw <= 0:
            return False, {**result, "error": "amount <= 0"}

        if not keypair:
            return False, {**result, "error": "Keypair taqdim etilmadi (None)"}

        user_pk = str(keypair.pubkey())
        quote = await self.get_quote(token_mint, SOL_MINT, token_amount_raw)
        if not quote:
            return False, {**result, "error": "Sell quote olinmadi"}

        out_lamports = int(quote.get("outAmount") or 0)
        result["quote"] = {
            "in_amount": token_amount_raw,
            "out_lamports": out_lamports,
            "price_impact_pct": safe_float(quote.get("priceImpactPct")),
        }

        if settings.PAPER_TRADING:
            sol_out = out_lamports / 1e9
            result.update({
                "success": True,
                "tx": "PAPER_SELL",
                "sol_received": sol_out,
                "usd_received": expected_usd or sol_out * 150.0,
            })
            logger.info(f"[PAPER SELL] {token_mint[:8]}... → {sol_out:.6f} SOL")
            return True, result

        tx_bytes = await self.get_swap_transaction(quote, user_pk)
        if not tx_bytes:
            return False, {**result, "error": "Sell swap tx olinmadi"}

        sig = await self.rpc.send_versioned_tx(tx_bytes, keypair)
        if not sig:
            return False, {**result, "error": "Sell tx yuborilmadi"}

        sol_out = out_lamports / 1e9
        result.update({
            "success": True,
            "tx": sig,
            "sol_received": sol_out,
            "usd_received": expected_usd or sol_out * 150.0,
        })
        logger.info(f"SELL OK {token_mint[:8]} tx={sig}")
        return True, result

    _sol_price_client = None  # lazy shared BirdeyeClient (avoids leaking a client per call)

    async def get_sol_price_usd(self) -> float:
        """Taxminiy SOL narxi (Birdeye yoki fallback)."""
        try:
            if JupiterSwap._sol_price_client is None:
                from scanner.birdeye import BirdeyeClient
                JupiterSwap._sol_price_client = BirdeyeClient()
            price = await JupiterSwap._sol_price_client.get_price(SOL_MINT)
            if price and price > 0:
                return price
        except Exception:
            pass
        return 150.0  # fallback
