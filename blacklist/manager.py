"""Auto Blacklist – honeypot, rug, fake volume, malicious contracts."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Set
from utils.logger import logger
from utils.helpers import utc_now, safe_float
from config.settings import settings

DB_PATH = Path("data/blacklist.json")


class BlacklistManager:
    REASONS = (
        "honeypot",
        "rug_pull",
        "fake_volume",
        "fake_holders",
        "malicious_contract",
        "scam_developer",
        "suspicious_wallet",
        "high_risk_contract",
        "manual",
    )

    def __init__(self):
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        self._data: Dict[str, Dict[str, Any]] = self._load()
        self._tokens: Set[str] = set(self._data.keys())

    def _load(self) -> Dict[str, Dict[str, Any]]:
        if DB_PATH.exists():
            try:
                return json.loads(DB_PATH.read_text(encoding="utf-8"))
            except Exception as e:
                logger.warning(f"Blacklist load failed: {e}")
        return {}

    def _save(self):
        try:
            DB_PATH.write_text(json.dumps(self._data, indent=2, default=str), encoding="utf-8")
        except Exception as e:
            logger.error(f"Blacklist save failed: {e}")

    def is_blacklisted(self, token: str) -> bool:
        return token in self._tokens

    def get_entry(self, token: str) -> Optional[Dict[str, Any]]:
        return self._data.get(token)

    def add(
        self,
        token: str,
        reason: str,
        details: str = "",
        source: str = "auto",
    ):
        if reason not in self.REASONS:
            reason = "high_risk_contract"
        self._data[token] = {
            "token": token,
            "reason": reason,
            "details": details,
            "source": source,
            "added_at": utc_now().isoformat(),
        }
        self._tokens.add(token)
        self._save()
        logger.warning(f"BLACKLIST + {token[:12]}... reason={reason} ({source})")

    def remove(self, token: str) -> bool:
        if token in self._data:
            del self._data[token]
            self._tokens.discard(token)
            self._save()
            logger.info(f"BLACKLIST - removed {token[:12]}...")
            return True
        return False

    def list_all(self) -> List[Dict[str, Any]]:
        return list(self._data.values())

    def auto_check(self, data: Dict[str, Any]) -> Optional[str]:
        """
        Inspect token data; if risky → add to blacklist and return reason.
        Called from filter pipeline.
        """
        if not settings.AUTO_BLACKLIST_ENABLED:
            return None

        token = data.get("token_address") or data.get("address") or ""
        if not token or self.is_blacklisted(token):
            return "already_blacklisted" if token in self._tokens else None

        sec = data.get("security") or {}

        if settings.BLACKLIST_HONEYPOT and (
            sec.get("is_honeypot") in (True, "true", "1") or str(sec.get("is_honeypot")).lower() == "true"
        ):
            self.add(token, "honeypot", "Detected by security API")
            return "honeypot"

        if settings.BLACKLIST_MALICIOUS and (
            sec.get("mint_authority") or sec.get("is_mintable")
        ):
            # only auto-blacklist if combined with other red flags
            top10 = safe_float(sec.get("top10_holder_pct") or 0)
            if top10 > 1:
                top10 /= 100
            if top10 > 0.5:
                self.add(token, "malicious_contract", "Mintable + high concentration")
                return "malicious_contract"

        # Fake volume heuristic: huge volume, tiny liquidity
        liq = safe_float(data.get("liquidity_usd"))
        vol = safe_float(data.get("volume_24h"))
        if settings.BLACKLIST_FAKE_VOLUME and liq > 0 and vol > liq * 50 and liq < 20_000:
            self.add(token, "fake_volume", f"vol={vol:.0f} liq={liq:.0f}")
            return "fake_volume"

        return None
