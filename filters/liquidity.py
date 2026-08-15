from typing import Dict, Any, Tuple
from config.settings import settings
from utils.helpers import safe_float


def check_liquidity(data: Dict[str, Any]) -> Tuple[bool, str]:
    """Liquidity $20K–100K+ (MIN majburiy, MAX ixtiyoriy)."""
    liq = safe_float(data.get("liquidity_usd"))
    if liq <= 0:
        ov = data.get("birdeye_overview") or {}
        liq = safe_float(ov.get("liquidity"))

    min_liq = settings.MIN_LIQUIDITY_USD
    max_liq = getattr(settings, "MAX_LIQUIDITY_USD", 0) or 0

    if liq < min_liq:
        return False, f"Liquidity past: ${liq:,.0f} < ${min_liq:,.0f}"
    if max_liq > 0 and liq > max_liq:
        return False, f"Liquidity yuqori: ${liq:,.0f} > ${max_liq:,.0f}"
    return True, f"Liquidity OK: ${liq:,.0f}"
