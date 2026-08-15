from typing import Dict, Any, Tuple
from utils.helpers import safe_float


def check_mint_authority(data: Dict[str, Any]) -> Tuple[bool, str]:
    sec = data.get("security") or {}
    # Ma'lumot umuman yo'q (Birdeye plan) – o'tkazib yuboramiz
    if not sec:
        return True, "Mint Authority ma'lumot yo'q (o'tkazildi)"
    mint_auth = sec.get("mint_authority")
    is_mintable = sec.get("is_mintable")
    if mint_auth or is_mintable:
        return False, f"Mint Authority hali faol: {mint_auth}"
    return True, "Mint Authority o'chirilgan"


def check_freeze_authority(data: Dict[str, Any]) -> Tuple[bool, str]:
    sec = data.get("security") or {}
    if not sec:
        return True, "Freeze Authority ma'lumot yo'q (o'tkazildi)"
    freeze_auth = sec.get("freeze_authority")
    is_freezable = sec.get("is_freezable")
    if freeze_auth or is_freezable:
        return False, f"Freeze Authority hali faol: {freeze_auth}"
    return True, "Freeze Authority o'chirilgan"


def check_honeypot(data: Dict[str, Any]) -> Tuple[bool, str]:
    sec = data.get("security") or {}
    if not sec:
        return True, "Honeypot ma'lumot yo'q (o'tkazildi)"
    is_hp = sec.get("is_honeypot")
    if is_hp is True or str(is_hp).lower() in ("true", "1", "yes"):
        return False, "Honeypot aniqlandi"
    return True, "Honeypot emas"


def check_market_cap(data: Dict[str, Any]) -> Tuple[bool, str]:
    from config.settings import settings

    mc = safe_float(data.get("market_cap") or data.get("fdv"))
    if mc <= 0:
        ov = data.get("birdeye_overview") or {}
        mc = safe_float(ov.get("mc"))
    if mc <= 0:
        return True, "Market Cap ma'lumot yo'q (o'tkazildi)"

    min_mc = getattr(settings, "MIN_MARKET_CAP_USD", 0) or 0
    max_mc = settings.MAX_MARKET_CAP_USD

    if min_mc > 0 and mc < min_mc:
        return False, f"Market Cap past: ${mc:,.0f} < ${min_mc:,.0f}"
    if mc > max_mc:
        return False, f"Market Cap yuqori: ${mc:,.0f} > ${max_mc:,.0f}"
    return True, f"Market Cap OK: ${mc:,.0f}"


def check_lp_locked(data: Dict[str, Any]) -> Tuple[bool, str]:
    """
    LP Locked yoki Burned.
    Birdeye security / overview maydonlaridan o'qiladi.
    Ma'lumot yo'q bo'lsa – REQUIRE_LP_LOCKED=False yoki soft-pass.
    """
    from config.settings import settings

    require = getattr(settings, "REQUIRE_LP_LOCKED", True)
    sec = data.get("security") or {}
    ov = data.get("birdeye_overview") or {}
    raw_sec = sec.get("raw") or {}

    # Turli API maydon nomlari
    flags = [
        sec.get("lp_locked"),
        sec.get("is_lp_locked"),
        sec.get("lpBurned"),
        sec.get("lp_burned"),
        raw_sec.get("isLock"),
        raw_sec.get("lpLocked"),
        raw_sec.get("lpBurnPercentage"),
        ov.get("lp_locked"),
    ]

    locked = False
    for f in flags:
        if f is True or str(f).lower() in ("true", "1", "yes"):
            locked = True
            break
        try:
            if f is not None and float(f) >= 50:  # burn % ≥ 50
                locked = True
                break
        except (TypeError, ValueError):
            pass

    # labels dan (DexScreener ba'zan "lp-burned" beradi)
    labels = data.get("labels") or []
    label_str = " ".join(str(x).lower() for x in labels)
    if "burn" in label_str or "lock" in label_str:
        locked = True

    if locked:
        return True, "LP Locked/Burned OK"

    if not sec and not any(flags):
        # Ma'lumot umuman yo'q
        if require:
            return True, "LP lock ma'lumot yo'q (yumshoq o'tkazildi)"
        return True, "LP lock tekshiruvi o'chirilgan"

    if require:
        return False, "LP Locked/Burned emas"
    return True, "LP lock yumshoq (require=off)"
