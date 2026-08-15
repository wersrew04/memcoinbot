from typing import Dict, Any, Tuple, List
from config.settings import settings
from utils.helpers import safe_float, safe_int


def check_holder_count(data: Dict[str, Any]) -> Tuple[bool, str]:
    count = safe_int(data.get("holder_count"))
    if count <= 0:
        sec = data.get("security") or {}
        count = safe_int(sec.get("holder_count"))
    if count <= 0:
        ov = data.get("birdeye_overview") or {}
        count = safe_int(ov.get("holder"))
    if count < settings.MIN_HOLDERS:
        return False, f"Holder soni past: {count} < {settings.MIN_HOLDERS}"
    return True, f"Holders OK: {count}"


def check_top10_holders(data: Dict[str, Any]) -> Tuple[bool, str]:
    sec = data.get("security") or {}
    top10 = safe_float(sec.get("top10_holder_pct") or sec.get("top10_user_pct"))
    if top10 <= 0:
        # top_holders ro'yxatidan hisoblash
        holders: List[Dict] = data.get("top_holders") or []
        if holders:
            total_pct = 0.0
            for h in holders[:10]:
                pct = safe_float(h.get("percentage") or h.get("uiAmount") or 0)
                # Ba'zi API'larda percentage 0-100, ba'zilarida 0-1
                if pct > 1:
                    pct /= 100.0
                total_pct += pct
            top10 = total_pct
    if top10 > settings.MAX_TOP10_HOLDER_PCT:
        return False, f"Top10 holder ulushi yuqori: {top10*100:.1f}% > {settings.MAX_TOP10_HOLDER_PCT*100:.0f}%"
    return True, f"Top10 OK: {top10*100:.1f}%"


def check_dev_wallet(data: Dict[str, Any]) -> Tuple[bool, str]:
    sec = data.get("security") or {}
    dev_pct = safe_float(sec.get("creator_pct") or sec.get("owner_pct"))
    if dev_pct > settings.MAX_DEV_WALLET_PCT:
        return False, f"Dev/Creator wallet ulushi yuqori: {dev_pct*100:.1f}%"
    return True, f"Dev wallet OK: {dev_pct*100:.1f}%"
