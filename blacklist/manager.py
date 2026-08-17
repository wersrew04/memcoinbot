"""Qora ro'yxat — token manzillarini bloklash."""
from __future__ import annotations
import json
from pathlib import Path
from typing import Dict, List, Optional
from utils.logger import logger

BL_FILE = Path("data/blacklist.json")


class BlacklistManager:
    def __init__(self):
        self._list: Dict[str, Dict] = {}
        self._load()

    def _load(self):
        if BL_FILE.exists():
            try:
                self._list = json.loads(BL_FILE.read_text(encoding="utf-8"))
            except Exception:
                self._list = {}

    def _save(self):
        try:
            BL_FILE.parent.mkdir(parents=True, exist_ok=True)
            BL_FILE.write_text(json.dumps(self._list, indent=2), encoding="utf-8")
        except Exception as e:
            logger.error(f"Blacklist save xato: {e}")

    def add(self, token: str, reason: str = "", details: str = "", source: str = "auto"):
        from utils.helpers import utc_now
        self._list[token] = {
            "token": token, "reason": reason,
            "details": details, "source": source,
            "ts": utc_now().isoformat(),
        }
        self._save()
        logger.info(f"Blacklist qo'shildi: {token[:12]}… sabab={reason}")

    def remove(self, token: str) -> bool:
        if token in self._list:
            del self._list[token]
            self._save()
            return True
        return False

    def is_blacklisted(self, token: str) -> bool:
        return token in self._list

    def list_all(self) -> List[Dict]:
        return list(self._list.values())
