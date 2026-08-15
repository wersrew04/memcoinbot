from typing import Dict, Any, Tuple
from config.settings import settings
from utils.helpers import safe_float, safe_int


def check_volume_24h(data: Dict[str, Any]) -> Tuple[bool, str]:
    """Yangi tokenlar uchun 24h volume ko'pincha past — MIN=0 bo'lsa o'tkaziladi."""
    min_v = getattr(settings, "MIN_24H_VOLUME_USD", 0) or 0
    if min_v <= 0:
        return True, "24h Volume filter o'chirilgan"

    vol = safe_float(data.get("volume_24h"))
    if vol <= 0:
        ov = data.get("birdeye_overview") or {}
        vol = safe_float(ov.get("v24h_usd"))
    if vol < min_v:
        return False, f"24h Volume past: ${vol:,.0f} < ${min_v:,.0f}"
    return True, f"24h Volume OK: ${vol:,.0f}"


def check_volume_5m(data: Dict[str, Any]) -> Tuple[bool, str]:
    """5 daqiqalik volume ≥ MIN_VOLUME_5M_USD ($20K+)."""
    min_v = getattr(settings, "MIN_VOLUME_5M_USD", 20_000)
    vol_5m = safe_float(data.get("volume_5m"))
    if vol_5m <= 0:
        return False, f"5m Volume yo'q yoki 0 < ${min_v:,.0f}"
    if vol_5m < min_v:
        return False, f"5m Volume past: ${vol_5m:,.0f} < ${min_v:,.0f}"
    return True, f"5m Volume OK: ${vol_5m:,.0f}"


def check_buy_sell_ratio(data: Dict[str, Any]) -> Tuple[bool, str]:
    """Buy/Sell nisbati ≥ 2:1 (5m txns asosida)."""
    min_ratio = getattr(settings, "MIN_BUY_SELL_RATIO", 2.0)
    buys = safe_int(data.get("txns_5m_buys"))
    sells = safe_int(data.get("txns_5m_sells"))

    if buys <= 0 and sells <= 0:
        # 1h fallback
        buys = safe_int(data.get("txns_1h_buys"))
        sells = safe_int(data.get("txns_1h_sells"))
        if buys <= 0 and sells <= 0:
            return True, "Buy/Sell ma'lumot yo'q (o'tkazildi)"

    if sells <= 0:
        ratio = float(buys) if buys > 0 else 0.0
    else:
        ratio = buys / sells

    if ratio < min_ratio:
        return False, f"Buy/Sell past: {buys}:{sells} ({ratio:.2f}x) < {min_ratio:.1f}x"
    return True, f"Buy/Sell OK: {buys}:{sells} ({ratio:.2f}x)"


def check_volume_spike(data: Dict[str, Any]) -> Tuple[bool, str]:
    """Oxirgi 5-10 daqiqada volume o'sishi (yumshoq)."""
    vol_5m = safe_float(data.get("volume_5m"))
    vol_1h = safe_float(data.get("volume_1h"))
    if vol_1h <= 0:
        return True, "Volume spike tekshiruvi o'tkazib yuborildi (ma'lumot yo'q)"
    ratio = vol_5m / (vol_1h / 12) if vol_1h > 0 else 0
    if ratio >= settings.MIN_VOLUME_SPIKE_PCT:
        return True, f"Volume spike bor: 5m/avg ratio ≈ {ratio:.1f}x"
    return True, f"Volume spike yumshoq: ratio={ratio:.2f}"
