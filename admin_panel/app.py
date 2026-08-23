"""MemeBot Pro Admin Panel – login + full dashboard + JSON API."""
from __future__ import annotations

import html as html_lib
from pathlib import Path
import asyncio
from typing import Any, Dict, Optional, List

from fastapi import FastAPI, Header, HTTPException, Depends, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from starlette.middleware.sessions import SessionMiddleware
from pydantic import BaseModel

from config.settings import settings
from utils.history import history

try:
    from dotenv import set_key as _dotenv_set_key
except ImportError:
    _dotenv_set_key = None

ENV_FILE = Path(__file__).resolve().parent.parent / ".env"


def _persist_to_env(key: str, value: Any) -> None:
    """Sozlamani saqlash:
    1) DATA_DIR/runtime_settings.json (Railway Volume — redeployda saqlanadi)
    2) lokal .env (ixtiyoriy)
    PRIVATE_KEY va API kalitlarini Railway Variables ga yozing.
    """
    try:
        from config.settings import persist_runtime_setting
        persist_runtime_setting(key, value)
    except Exception:
        pass
    if _dotenv_set_key is None:
        return
    try:
        _dotenv_set_key(str(ENV_FILE), key, str(value))
    except Exception:
        pass


def _auth(x_admin_key: Optional[str] = Header(None)):
    if x_admin_key != settings.ADMIN_API_KEY:
        raise HTTPException(status_code=401, detail="Invalid admin key")
    return True


class SettingUpdate(BaseModel):
    key: str
    value: Any


def _is_logged_in(request: Request) -> bool:
    return bool(request.session.get("authenticated"))


def _require_web_auth(request: Request) -> Optional[RedirectResponse]:
    if not _is_logged_in(request):
        return RedirectResponse(url="/login", status_code=303)
    return None


PAGE_STYLE = """
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet">
<style>
  :root {
    --bg: #05070c;
    --panel: #0b0f17;
    --card: #111722;
    --card2: #161d2b;
    --border: #1c2433;
    --border-light: #2a3548;
    --text: #f1f3f7;
    --muted: #7d8aa0;
    --accent: #6366f1;
    --accent2: #8b5cf6;
    --accent-glow: rgba(99,102,241,.3);
    --ok: #10b981;
    --ok-soft: rgba(16,185,129,.14);
    --bad: #f43f5e;
    --bad-soft: rgba(244,63,94,.14);
    --warn: #f59e0b;
    --radius: 16px;
    --shadow: 0 4px 24px rgba(0,0,0,.35);
  }
  * { box-sizing: border-box; }
  body {
    margin: 0; background: var(--bg); color: var(--text);
    font-family: Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    font-size: 14px; line-height: 1.5;
    background-image:
      radial-gradient(ellipse 90% 60% at 10% -10%, rgba(99,102,241,.18), transparent 50%),
      radial-gradient(ellipse 70% 50% at 90% 0%, rgba(139,92,246,.12), transparent 45%),
      radial-gradient(ellipse 50% 40% at 50% 100%, rgba(16,185,129,.06), transparent 40%);
    background-attachment: fixed;
    min-height: 100vh;
  }
  a { color: #a5b4fc; text-decoration: none; transition: color .15s; }
  a:hover { color: #c7d2fe; text-decoration: none; }
  .layout { display: flex; min-height: 100vh; }
  .sidebar {
    width: 240px;
    background: linear-gradient(180deg, rgba(11,15,23,.95) 0%, rgba(5,7,12,.98) 100%);
    border-right: 1px solid var(--border);
    padding: 24px 16px;
    position: sticky; top: 0; height: 100vh; flex-shrink: 0;
    backdrop-filter: blur(12px);
    display: flex; flex-direction: column;
  }
  .sidebar .logo {
    font-weight: 800; font-size: 18px; margin-bottom: 32px;
    letter-spacing: -0.03em; display: flex; align-items: center; gap: 10px;
    padding: 0 8px;
  }
  .sidebar .logo .logo-icon {
    width: 32px; height: 32px; border-radius: 10px;
    background: linear-gradient(135deg, #6366f1, #a855f7);
    display: flex; align-items: center; justify-content: center;
    font-size: 16px; box-shadow: 0 4px 12px rgba(99,102,241,.4);
  }
  .sidebar .logo span {
    background: linear-gradient(90deg, #a5b4fc, #c4b5fd);
    -webkit-background-clip: text; -webkit-text-fill-color: transparent;
    background-clip: text;
  }
  .nav { flex: 1; }
  .nav a {
    display: flex; align-items: center; gap: 10px;
    padding: 10px 14px; border-radius: 12px; color: var(--muted);
    margin-bottom: 2px; text-decoration: none; font-weight: 500;
    font-size: 13.5px; transition: all .18s ease;
  }
  .nav a:hover {
    background: rgba(255,255,255,.04); color: var(--text); text-decoration: none;
  }
  .nav a.active {
    background: linear-gradient(135deg, rgba(99,102,241,.22), rgba(139,92,246,.1));
    color: #c7d2fe;
    border: 1px solid rgba(99,102,241,.3);
    box-shadow: 0 0 20px rgba(99,102,241,.12);
    text-decoration: none;
  }
  .sidebar .logout {
    margin-top: auto; padding: 12px 14px; font-size: 12px; color: var(--muted);
    border-radius: 10px; transition: all .15s;
  }
  .sidebar .logout:hover { background: rgba(244,63,94,.1); color: #fda4af; }
  .main { flex: 1; padding: 28px 32px 80px; max-width: 1320px; }
  .topbar {
    display: flex; justify-content: space-between; align-items: center;
    margin-bottom: 28px; gap: 16px; flex-wrap: wrap;
  }
  .topbar h1 {
    margin: 0; font-size: 24px; font-weight: 800; letter-spacing: -0.03em;
    display: flex; align-items: center; gap: 10px;
  }
  #live-dot {
    display: inline-block; width: 9px; height: 9px; border-radius: 50%;
    background: #10b981; box-shadow: 0 0 0 0 rgba(16,185,129,.5);
    animation: pulse-dot 2s infinite;
  }
  @keyframes pulse-dot {
    0% { box-shadow: 0 0 0 0 rgba(16,185,129,.5); }
    70% { box-shadow: 0 0 0 8px rgba(16,185,129,0); }
    100% { box-shadow: 0 0 0 0 rgba(16,185,129,0); }
  }
  #top-badges { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }
  .grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
    gap: 14px; margin-bottom: 20px;
  }
  .stat {
    background: linear-gradient(160deg, var(--card2) 0%, var(--card) 100%);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 16px 18px;
    transition: border-color .2s, transform .2s, box-shadow .2s;
    position: relative; overflow: hidden;
  }
  .stat::before {
    content: ''; position: absolute; top: 0; left: 0; right: 0; height: 1px;
    background: linear-gradient(90deg, transparent, rgba(255,255,255,.08), transparent);
  }
  .stat:hover {
    border-color: var(--border-light);
    transform: translateY(-2px);
    box-shadow: var(--shadow);
  }
  .stat .label {
    font-size: 10.5px; text-transform: uppercase; letter-spacing: .08em;
    color: var(--muted); font-weight: 600;
  }
  .stat .value {
    font-size: 22px; font-weight: 800; margin-top: 8px;
    letter-spacing: -0.03em; line-height: 1.15;
  }
  .card {
    background: linear-gradient(165deg, var(--card2) 0%, var(--card) 100%);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 22px 24px; margin-bottom: 18px;
    box-shadow: 0 1px 0 rgba(255,255,255,.04) inset, var(--shadow);
    position: relative;
  }
  .card h2 {
    margin: 0 0 16px; font-size: 12px; text-transform: uppercase; letter-spacing: .07em;
    color: var(--muted); font-weight: 700;
    display: flex; align-items: center; gap: 8px;
  }
  .badge {
    display: inline-flex; align-items: center; gap: 5px;
    padding: 5px 12px; border-radius: 999px; font-size: 11px; font-weight: 700;
    letter-spacing: .03em;
  }
  .badge.on {
    background: var(--ok-soft); color: #34d399;
    border: 1px solid rgba(16,185,129,.35);
    box-shadow: 0 0 12px rgba(16,185,129,.15);
  }
  .badge.off {
    background: var(--bad-soft); color: #fb7185;
    border: 1px solid rgba(244,63,94,.3);
  }
  button, .btn {
    background: linear-gradient(135deg, #6366f1, #7c3aed);
    color: #fff; border: none; padding: 9px 16px; border-radius: 10px;
    cursor: pointer; font-size: 13px; font-weight: 600; margin: 3px 5px 3px 0;
    transition: filter .15s, box-shadow .15s, transform .1s;
    box-shadow: 0 2px 8px rgba(99,102,241,.3);
  }
  button:hover {
    filter: brightness(1.12);
    box-shadow: 0 4px 16px rgba(99,102,241,.4);
    transform: translateY(-1px);
  }
  button:active { transform: translateY(0); }
  button.stop {
    background: linear-gradient(135deg, #f43f5e, #e11d48);
    box-shadow: 0 2px 8px rgba(244,63,94,.3);
  }
  button.stop:hover { box-shadow: 0 4px 16px rgba(244,63,94,.4); }
  button.warn {
    background: linear-gradient(135deg, #f59e0b, #d97706);
    color: #111; box-shadow: 0 2px 8px rgba(245,158,11,.3);
  }
  button.ghost {
    background: var(--card2); color: var(--text);
    border: 1px solid var(--border); box-shadow: none;
  }
  button.ghost:hover { background: var(--border); border-color: var(--border-light); box-shadow: none; }
  button.ok {
    background: linear-gradient(135deg, #10b981, #059669);
    color: #fff; box-shadow: 0 2px 8px rgba(16,185,129,.3);
  }
  button.copy-btn {
    background: var(--card2); color: var(--muted); padding: 3px 9px; font-size: 10px;
    margin: 0 0 0 8px; border-radius: 6px; vertical-align: middle;
    border: 1px solid var(--border); box-shadow: none; font-weight: 600;
  }
  button.copy-btn:hover {
    color: var(--text); background: var(--border); box-shadow: none; transform: none;
  }
  input[type=text], input[type=password], input[type=number] {
    background: var(--bg); border: 1px solid var(--border); color: var(--text);
    padding: 10px 14px; border-radius: 10px; width: 100%; font-size: 13px;
    transition: border-color .15s, box-shadow .15s;
  }
  input:focus {
    outline: none; border-color: var(--accent);
    box-shadow: 0 0 0 3px var(--accent-glow);
  }
  label { display: block; font-size: 12px; color: var(--muted); margin-bottom: 5px; font-weight: 500; }
  .form-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 14px; }
  .form-row { margin-bottom: 4px; }
  table { width: 100%; border-collapse: separate; border-spacing: 0; font-size: 13px; }
  th, td {
    text-align: left; padding: 12px 10px;
    border-bottom: 1px solid var(--border); vertical-align: middle;
  }
  th {
    color: var(--muted); font-weight: 600; font-size: 10.5px;
    text-transform: uppercase; letter-spacing: .06em;
    background: rgba(0,0,0,.2);
  }
  th:first-child { border-radius: 10px 0 0 0; }
  th:last-child { border-radius: 0 10px 0 0; }
  tr:last-child td { border-bottom: none; }
  tr:hover td { background: rgba(99,102,241,.04); }
  .mono { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size: 11.5px; }
  .token-full {
    font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    font-size: 11px; word-break: break-all; max-width: 300px; line-height: 1.45;
    color: #94a3b8;
  }
  .token-full a { color: #a5b4fc; }
  .token-full a:hover { color: #c7d2fe; text-decoration: underline; }
  .muted { color: var(--muted); }
  .bad-t { color: var(--bad); }
  .login-wrap { max-width: 400px; margin: 14vh auto; }
  .login-wrap .card {
    padding: 36px; box-shadow: 0 24px 60px rgba(0,0,0,.5);
    border: 1px solid rgba(99,102,241,.2);
  }
  form.inline { display: inline; }
  .section { display: none !important; }
  .section.active { display: block !important; }
  .pnl-pos { color: #34d399; font-weight: 700; }
  .pnl-neg { color: #fb7185; font-weight: 700; }
  .pnl-card {
    background: linear-gradient(160deg, var(--card2), var(--card));
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 18px 18px 16px;
    position: relative; overflow: hidden;
    transition: border-color .2s, transform .2s, box-shadow .2s;
  }
  .pnl-card::before {
    content: ''; position: absolute; top: 0; left: 0; width: 3px; height: 100%;
    border-radius: 3px 0 0 3px;
  }
  .pnl-card:hover { transform: translateY(-3px); box-shadow: var(--shadow); }
  .pnl-card.pos {
    border-color: rgba(16,185,129,.4);
    background: linear-gradient(145deg, rgba(16,185,129,.12) 0%, var(--card) 55%);
  }
  .pnl-card.pos::before { background: linear-gradient(180deg, #34d399, #10b981); }
  .pnl-card.neg {
    border-color: rgba(244,63,94,.4);
    background: linear-gradient(145deg, rgba(244,63,94,.12) 0%, var(--card) 55%);
  }
  .pnl-card.neg::before { background: linear-gradient(180deg, #fb7185, #f43f5e); }
  .pnl-card.wait { border-color: var(--border); }
  .pnl-card.wait::before { background: var(--border-light); }
  .pnl-card .sym {
    font-size: 13px; font-weight: 700; color: var(--text); letter-spacing: .01em;
  }
  .pnl-card .amt {
    font-size: 11px; color: var(--muted); margin-left: 8px;
    background: rgba(255,255,255,.05); padding: 2px 8px; border-radius: 6px;
  }
  .pnl-card .pnl-val {
    font-size: 26px; font-weight: 800; margin-top: 10px;
    letter-spacing: -0.04em; line-height: 1.1;
  }
  .pnl-card .pnl-val.pos { color: #34d399; text-shadow: 0 0 24px rgba(16,185,129,.3); }
  .pnl-card .pnl-val.neg { color: #fb7185; text-shadow: 0 0 24px rgba(244,63,94,.25); }
  .pnl-card .pnl-val.wait { color: var(--muted); font-size: 14px; font-weight: 500; text-shadow: none; }
  .pnl-card .pct-pill {
    display: inline-block; margin-top: 10px; padding: 4px 12px; border-radius: 999px;
    font-size: 12px; font-weight: 700; letter-spacing: .02em;
  }
  .pnl-card .pct-pill.pos {
    background: rgba(16,185,129,.2); color: #34d399;
    border: 1px solid rgba(16,185,129,.3);
  }
  .pnl-card .pct-pill.neg {
    background: rgba(244,63,94,.2); color: #fb7185;
    border: 1px solid rgba(244,63,94,.3);
  }
  .log-line {
    font-family: ui-monospace, monospace; font-size: 12px;
    padding: 4px 0; border-bottom: 1px solid #151b26;
  }
  @media (max-width: 900px) {
    .layout { flex-direction: column; }
    .sidebar {
      width: 100%; height: auto; position: relative;
      border-right: none; border-bottom: 1px solid var(--border);
    }
    .nav { display: flex; flex-wrap: wrap; gap: 4px; }
    .nav a { padding: 8px 12px; font-size: 12px; }
    .token-full { max-width: 160px; }
    .main { padding: 20px 16px 60px; }
  }
</style>
"""


def _bool_badge(val: bool, on="ON", off="OFF") -> str:
    return f'<span class="badge {"on" if val else "off"}">{on if val else off}</span>'


def _esc(v: Any) -> str:
    return html_lib.escape(str(v if v is not None else ""))

def _mask_secret(val: str, show: int = 4) -> str:
    """Display mask for secrets – empty stays empty."""
    s = str(val or "")
    if not s:
        return ""
    if len(s) <= show * 2:
        return "*" * len(s)
    return s[:show] + "…" + s[-show:]


SECRET_SETTING_KEYS = (
    "PRIVATE_KEY",
    "TELEGRAM_BOT_TOKEN",
    "BIRDEYE_API_KEY",
    "HELIUS_API_KEY",
    "JUPITER_API_KEY",
    "OPENAI_API_KEY",
    "X_API_BEARER_TOKEN",
    "EMAIL_PASSWORD",
    "ADMIN_API_KEY",
    "ADMIN_PASSWORD",
    "ADMIN_SESSION_SECRET",
    "DISCORD_WEBHOOK_URL",
)

API_SETTING_KEYS = (
    "TELEGRAM_BOT_TOKEN",
    "TELEGRAM_CHAT_ID",
    "BIRDEYE_API_KEY",
    "HELIUS_API_KEY",
    "JUPITER_API_KEY",
    "OPENAI_API_KEY",
    "X_API_BEARER_TOKEN",
    "RPC_URL",
    "PRIVATE_KEY",
    "DATABASE_URL",
    "REDIS_URL",
    "ADMIN_USERNAME",
    "ADMIN_PASSWORD",
    "ADMIN_API_KEY",
    "ADMIN_SESSION_SECRET",
    "DISCORD_WEBHOOK_URL",
    "EMAIL_SMTP_HOST",
    "EMAIL_SMTP_PORT",
    "EMAIL_USER",
    "EMAIL_PASSWORD",
    "EMAIL_TO",
)



def _sidebar(active: str = "overview") -> str:
    items = [
        ("overview", "Overview"),
        ("positions", "Positions"),
        ("trades", "Trades / PnL"),
        ("filters", "Filter Settings"),
        ("api", "API / Keys"),
        ("rejections", "Rejections"),
        ("blacklist", "Blacklist"),
        ("ai", "AI Weights"),
        ("modules", "Modules"),
        ("logs", "Logs"),
        ("control", "Control"),
    ]
    # onclick — listener ishlamasa ham menyu almashtadi
    links = "".join(
        (
            '<a href="#{k}" class="{cls}" data-section="{k}" '
            'onclick="return window.mbShow && window.mbShow(\'{k}\')">{label}</a>'
        ).format(
            k=k,
            cls=("active" if k == active else ""),
            label=label,
        )
        for k, label in items
    )
    return f"""
    <aside class="sidebar">
      <div class="logo"><div class="logo-icon">⚡</div> <span>MemeBot</span>&nbsp;Pro</div>
      <nav class="nav">{links}</nav>
      <a href="/logout" class="logout">← Chiqish</a>
    </aside>
    """


def _login_page(error: Optional[str] = None) -> str:
    err = f'<p class="bad-t">{_esc(error)}</p>' if error else ""
    return f"""<!DOCTYPE html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
    <title>MemeBot Pro – Login</title>{PAGE_STYLE}</head><body>
    <div class="login-wrap"><div class="card">
        <h1>MemeBot <span style="color:var(--accent)">Pro</span></h1>
        <p class="muted">Admin panelga kirish</p>{err}
        <form method="post" action="/login" style="margin-top:16px">
          <div class="form-row"><label>Login</label><input type="text" name="username" required autofocus></div>
          <div class="form-row" style="margin-top:10px"><label>Parol</label><input type="password" name="password" required></div>
          <button type="submit" style="width:100%;margin-top:16px;padding:11px">Kirish</button>
        </form>
    </div></div></body></html>"""


def _read_log_tail(n: int = 80) -> List[str]:
    log_dir = Path("logs")
    if not log_dir.exists():
        return []
    files = sorted(log_dir.glob("bot_*.log"), reverse=True)
    if not files:
        return []
    try:
        lines = files[0].read_text(encoding="utf-8", errors="replace").splitlines()
        return lines[-n:]
    except Exception:
        return []



async def _live_snapshot(bot_ref) -> dict:
    """Dashboard uchun jonli statistika (JSON)."""
    from utils.helpers import pnl_percent, pnl_usd as calc_pnl_usd, net_pnl_usd, net_pnl_percent, roundtrip_fee_usd

    running = settings.BOT_RUNNING
    paper = settings.PAPER_TRADING
    emergency = settings.EMERGENCY_STOP
    if bot_ref and hasattr(bot_ref, "advanced_risk"):
        emergency = emergency or getattr(bot_ref.advanced_risk, "emergency_stop", False)

    open_count = 0
    daily_loss = 0.0
    positions_out = []
    unrealized = 0.0
    known = 0

    if bot_ref and hasattr(bot_ref, "risk"):
        summary = await bot_ref.risk.get_status_summary()
        positions = summary.get("positions", {}) or {}
        if bot_ref and hasattr(bot_ref, "monitor") and positions:
            async def _upd(tok: str):
                try:
                    price = await bot_ref.monitor.get_current_price(tok)
                    if price > 0:
                        await bot_ref.risk.update_position(tok, {"current_price": price})
                except Exception:
                    pass
            await asyncio.gather(*(_upd(t) for t in positions.keys()))
            summary = await bot_ref.risk.get_status_summary()
            positions = summary.get("positions", {}) or {}

        open_count = summary.get("open_positions", len(positions))
        daily_loss = float(summary.get("daily_loss_usd", 0) or 0)

        for token, pos in positions.items():
            entry = float(pos.get("entry_price") or 0)
            amount = float(pos.get("amount_usd") or 0)
            symbol = pos.get("symbol", token[:8])
            try:
                current = float(pos.get("current_price") or 0)
            except (TypeError, ValueError):
                current = 0.0
            if entry > 0 and current > 0:
                pct = net_pnl_percent(amount, entry, current)
                usd = net_pnl_usd(amount, entry, current)
                unrealized += usd
                known += 1
            else:
                pct, usd = 0.0, 0.0
            positions_out.append({
                "token": token,
                "symbol": symbol,
                "amount_usd": amount,
                "entry_price": entry,
                "current_price": current,
                "pnl_usd": round(usd, 4),
                "pnl_pct": round(pct, 2),
                "ai_score": pos.get("ai_score"),
                "paper": bool(pos.get("paper")),
            })

    pnl = history.pnl_summary()
    adv = {}
    if bot_ref and hasattr(bot_ref, "advanced_risk"):
        try:
            adv = bot_ref.advanced_risk.status()
        except Exception:
            adv = {}

    wallet_sol = 0.0
    wallet_usd = 0.0
    wallet_pub = ""
    try:
        from wallet.keypair import get_pubkey, get_sol_balance, get_sol_price_usd
        wallet_pub = get_pubkey() or ""
        if wallet_pub and bot_ref and getattr(bot_ref, "_session", None):
            wallet_sol = await get_sol_balance(bot_ref._session, wallet_pub)
            px = await get_sol_price_usd(bot_ref._session)
            wallet_usd = wallet_sol * px
    except Exception:
        pass

    return {
        "ts": __import__("datetime").datetime.utcnow().isoformat() + "Z",
        "running": running,
        "paper": paper,
        "emergency": emergency,
        "open_count": open_count,
        "max_open": settings.MAX_OPEN_POSITIONS,
        "unrealized_pnl": round(unrealized, 4) if known else None,
        "daily_loss": round(daily_loss, 4),
        "net_pnl": pnl.get("net_pnl", 0),
        "profit": pnl.get("profit", 0),
        "loss": pnl.get("loss", 0),
        "win_rate": pnl.get("win_rate", 0),
        "total_trades": pnl.get("total_trades", 0),
        "best": pnl.get("best", 0),
        "worst": pnl.get("worst", 0),
        "trade_amount": settings.TRADE_AMOUNT_USD,
        "wallet_sol": round(wallet_sol, 6),
        "wallet_usd": round(wallet_usd, 2),
        "wallet_pub": wallet_pub,
        "positions": positions_out,
        "adv": {
            "paused": adv.get("paused"),
            "consecutive_losses": adv.get("consecutive_losses", 0),
            "daily_trades": adv.get("daily_trades", 0),
            "max_daily_trades": adv.get("max_daily_trades"),
            "pause_reason": adv.get("pause_reason") or "",
        },
    }


async def _dashboard_html(bot_ref) -> str:
    running = settings.BOT_RUNNING
    paper = settings.PAPER_TRADING
    emergency = settings.EMERGENCY_STOP
    if bot_ref and hasattr(bot_ref, "advanced_risk"):
        emergency = emergency or bot_ref.advanced_risk.emergency_stop

    open_count = 0
    daily_loss = 0.0
    positions_rows = ""
    open_pnl_cards = ""
    unrealized_pnl = 0.0
    unrealized_known = 0
    if bot_ref and hasattr(bot_ref, "risk"):
        summary = await bot_ref.risk.get_status_summary()
        positions = summary.get("positions", {})

        # Ochiq pozitsiyalar uchun oxirgi narxlarni parallel yangilaymiz
        if bot_ref and hasattr(bot_ref, "monitor") and positions:
            async def _update_price(tok: str):
                try:
                    price = await bot_ref.monitor.get_current_price(tok)
                    if price > 0:
                        await bot_ref.risk.update_position(tok, {"current_price": price})
                except Exception:
                    pass
            await asyncio.gather(*(_update_price(tok) for tok in positions.keys()))
            summary = await bot_ref.risk.get_status_summary()
            positions = summary.get("positions", {})

        open_count = summary.get("open_positions", len(positions))
        daily_loss = summary.get("daily_loss_usd", 0.0)
        from utils.helpers import pnl_percent, pnl_usd as calc_pnl_usd, net_pnl_usd, net_pnl_percent, roundtrip_fee_usd

        for token, pos in positions.items():
            entry = float(pos.get("entry_price") or 0)
            amount = float(pos.get("amount_usd") or 0)
            symbol = pos.get("symbol", token[:8])
            current_raw = pos.get("current_price")
            try:
                current_val = float(current_raw) if current_raw is not None else 0.0
            except (TypeError, ValueError):
                current_val = 0.0

            if entry > 0 and current_val > 0:
                pnl_pct = pnl_percent(entry, current_val)
                pnl_u = calc_pnl_usd(amount, entry, current_val)
                unrealized_pnl += pnl_u
                unrealized_known += 1
                pnl_class = "pnl-pos" if pnl_u >= 0 else "pnl-neg"
                arrow = "▲" if pnl_u >= 0 else "▼"
                pnl_text = f"{arrow} ${pnl_u:+.2f} ({pnl_pct:+.1f}%)"
                current_text = f"${current_val:.8f}"
                card_color = "#22c55e" if pnl_u >= 0 else "#ef4444"
            else:
                pnl_class = "muted"
                pnl_text = "narx kutilmoqda..."
                current_text = "—"
                card_color = "var(--muted)"
                pnl_pct = 0.0
                pnl_u = 0.0
                arrow = "·"

            tok_esc = _esc(token)
            positions_rows += (
                f"<tr><td><strong>{_esc(symbol)}</strong></td>"
                f"<td><div class='token-full'>"
                f"<a href='https://solscan.io/token/{tok_esc}' target='_blank' rel='noopener' title='Solscan'>{tok_esc}</a>"
                f"<button type='button' class='copy-btn' onclick=\"navigator.clipboard.writeText('{tok_esc}');this.textContent='✓';setTimeout(()=>this.textContent='Copy',1200)\">Copy</button>"
                f"</div></td>"
                f"<td>${amount:.2f}</td>"
                f"<td class='mono'>${entry:.8f}</td>"
                f"<td class='mono'>{current_text}</td>"
                f"<td class='{pnl_class}' style='font-weight:700;font-size:15px'>{pnl_text}</td>"
                f"<td>{_esc(pos.get('ai_score', '—'))}</td>"
                f"<td class='muted'>{'PAPER' if pos.get('paper') else 'LIVE'}</td>"
                f"<td><form class='inline' method='post' action='/dashboard/positions/close' onsubmit=\"return confirm('Pozitsiyani yopishni tasdiqlaysizmi?');\">"
                f"<input type='hidden' name='token' value='{tok_esc}'>"
                f"<button class='stop' type='submit' style='padding:4px 8px;font-size:11px'>Yopish</button></form></td></tr>"
            )

            # Overview dagi katta kartochka
            if entry > 0 and current_val > 0:
                side = "pos" if pnl_u >= 0 else "neg"
                sign = "+" if pnl_u >= 0 else ""
                open_pnl_cards += f"""
            <div class="pnl-card {side}">
              <div><span class="sym">{_esc(symbol)}</span><span class="amt">${amount:.0f}</span></div>
              <div class="pnl-val {side}">{sign}${abs(pnl_u):.2f}</div>
              <span class="pct-pill {side}">{pnl_pct:+.1f}%</span>
            </div>"""
            else:
                open_pnl_cards += f"""
            <div class="pnl-card wait">
              <div><span class="sym">{_esc(symbol)}</span><span class="amt">${amount:.0f}</span></div>
              <div class="pnl-val wait">narx kutilmoqda…</div>
            </div>"""

    if not positions_rows:
        positions_rows = '<tr><td colspan="9" class="muted">Ochiq pozitsiya yo\'q</td></tr>'
    if not open_pnl_cards:
        open_pnl_cards = '<div class="pnl-card wait"><div class="pnl-val wait">Hozircha ochiq savdo yo\'q</div></div>'

    u_color = "#22c55e" if unrealized_pnl >= 0 else "#ef4444"
    u_label = f"${unrealized_pnl:+.2f}" if unrealized_known else "—"

    pnl = history.pnl_summary()
    trades = history.list_trades(40)
    trade_rows = ""
    for t in trades:
        pnl_u = float(t.get("pnl_usd") or 0)
        cls = "pnl-pos" if pnl_u >= 0 else "pnl-neg"
        trade_rows += (
            f"<tr><td class='muted mono'>{_esc(str(t.get('ts',''))[:19])}</td>"
            f"<td><strong>{_esc(t.get('symbol'))}</strong></td>"
            f"<td class='{cls}'>${pnl_u:+.2f}</td>"
            f"<td class='{cls}'>{float(t.get('pnl_pct') or 0):+.1f}%</td>"
            f"<td>{_esc(t.get('reason'))}</td>"
            f"<td>{_esc(t.get('ai_score'))}</td></tr>"
        )
    if not trade_rows:
        trade_rows = '<tr><td colspan="6" class="muted">Hali yopilgan savdo yo\'q</td></tr>'

    rejs = history.list_rejections(40)
    rej_rows = ""
    for r in rejs:
        rej_rows += (
            f"<tr><td class='muted mono'>{_esc(str(r.get('ts',''))[:19])}</td>"
            f"<td>{_esc(r.get('symbol'))}</td>"
            f"<td class='token-full' title='{_esc(r.get('token',''))}'>{_esc(r.get('token',''))}</td>"
            f"<td>{_esc(r.get('stage'))}</td>"
            f"<td class='muted'>{_esc(r.get('last_reason'))}</td></tr>"
        )
    if not rej_rows:
        rej_rows = '<tr><td colspan="5" class="muted">Hali rad yo\'q</td></tr>'

    bl_rows = ""
    if bot_ref and hasattr(bot_ref, "blacklist"):
        for e in bot_ref.blacklist.list_all()[:40]:
            tok = _esc(e.get("token", ""))
            bl_rows += (
                f"<tr><td class='mono'>{tok[:14]}…</td><td>{_esc(e.get('reason'))}</td>"
                f"<td class='muted'>{_esc(e.get('source'))}</td>"
                f"<td><form class='inline' method='post' action='/dashboard/blacklist/remove'>"
                f"<input type='hidden' name='token' value='{tok}'>"
                f"<button class='ghost' type='submit'>O'chirish</button></form></td></tr>"
            )
    if not bl_rows:
        bl_rows = '<tr><td colspan="4" class="muted">Qora ro\'yxat bo\'sh</td></tr>'

    weights = {}
    if bot_ref and hasattr(bot_ref, "learner"):
        weights = bot_ref.learner.get_weights()
    w_rows = "".join(
        f"<tr><td>{_esc(k)}</td><td class='mono'>{float(v):.4f}</td></tr>"
        for k, v in sorted(weights.items())
    ) or '<tr><td colspan="2" class="muted">Weights yo\'q</td></tr>'

    log_lines = _read_log_tail(60)
    log_html = "".join(f'<div class="log-line">{_esc(l)}</div>' for l in reversed(log_lines)) or (
        '<div class="muted">Log fayl topilmadi</div>'
    )

    adv = {}
    if bot_ref and hasattr(bot_ref, "advanced_risk"):
        adv = bot_ref.advanced_risk.status()

    # Hamyon balansi (web da ko'rinishi uchun)
    wallet_pubkey = ""
    wallet_sol = 0.0
    wallet_sol_usd = 0.0
    wallet_err = ""
    try:
        from wallet.keypair import get_pubkey, get_sol_balance, get_sol_price_usd
        wallet_pubkey = get_pubkey() or ""
        if wallet_pubkey and bot_ref and getattr(bot_ref, "_session", None):
            wallet_sol = await get_sol_balance(bot_ref._session, wallet_pubkey)
            sol_px = await get_sol_price_usd(bot_ref._session)
            wallet_sol_usd = wallet_sol * sol_px
        elif not wallet_pubkey:
            wallet_err = "PRIVATE_KEY o'rnatilmagan"
        else:
            wallet_err = "Session yo'q"
    except Exception as e:
        wallet_err = str(e)[:80]

    def fv(name, default=0):
        return getattr(settings, name, default)

    net_color = "#22c55e" if pnl["net_pnl"] >= 0 else "#ef4444"
    emerg_badge = _bool_badge(not emergency, "SAFE", "EMERGENCY") if not emergency else '<span class="badge off">EMERGENCY</span>'
    wallet_short = (wallet_pubkey[:6] + "…" + wallet_pubkey[-4:]) if len(wallet_pubkey) > 12 else (wallet_pubkey or "—")


    # Masked secrets for API form placeholders
    tg_ph = _mask_secret(getattr(settings, "TELEGRAM_BOT_TOKEN", "") or "") or "token yo'q"
    tg_chat = _esc(getattr(settings, "TELEGRAM_CHAT_ID", "") or "")
    be_ph = _mask_secret(getattr(settings, "BIRDEYE_API_KEY", "") or "") or "kalit yo'q"
    he_ph = _mask_secret(getattr(settings, "HELIUS_API_KEY", "") or "") or "ixtiyoriy"
    ju_ph = _mask_secret(getattr(settings, "JUPITER_API_KEY", "") or "") or "ixtiyoriy"
    oa_ph = _mask_secret(getattr(settings, "OPENAI_API_KEY", "") or "") or "ixtiyoriy"
    x_ph = _mask_secret(getattr(settings, "X_API_BEARER_TOKEN", "") or "") or "ixtiyoriy"
    rpc = _esc(getattr(settings, "RPC_URL", "") or "")
    pk_ph = _mask_secret(getattr(settings, "PRIVATE_KEY", "") or "") or "paper uchun bo'sh"
    db_url = _esc(getattr(settings, "DATABASE_URL", "") or "")
    redis_url = _esc(getattr(settings, "REDIS_URL", "") or "")
    admin_user = _esc(getattr(settings, "ADMIN_USERNAME", "") or "")
    ak_ph = _mask_secret(getattr(settings, "ADMIN_API_KEY", "") or "") or "change-me"
    discord = _esc(getattr(settings, "DISCORD_WEBHOOK_URL", "") or "")

    return f"""<!DOCTYPE html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>MemeBot Pro Admin</title>{PAGE_STYLE}</head><body>
<div class="layout">
{_sidebar("overview")}
<main class="main">
  <div class="topbar">
    <h1>Dashboard <span id="live-dot" title="jonli"></span>
      <span id="live-ts" class="muted" style="font-size:12px;font-weight:500"></span></h1>
    <div id="top-badges">
      {_bool_badge(running, "RUNNING", "STOPPED")}
      {_bool_badge(paper, "PAPER", "LIVE")}
      {emerg_badge}
    </div>
  </div>

  <section id="sec-overview" class="section active">
    <div class="grid" id="stats-grid">
      <div class="stat"><div class="label">Bot</div><div class="value" id="st-bot">{'✅' if running else '🛑'}</div></div>
      <div class="stat"><div class="label">Mode</div><div class="value" id="st-mode" style="font-size:16px">{'PAPER' if paper else 'LIVE'}</div></div>
      <div class="stat"><div class="label">Open</div><div class="value" id="st-open">{open_count}/{settings.MAX_OPEN_POSITIONS}</div></div>
      <div class="stat"><div class="label">Ochiq PnL</div><div class="value" id="st-upnl" style="font-size:18px;color:{u_color}">{u_label}</div></div>
      <div class="stat"><div class="label">Daily loss</div><div class="value" id="st-dloss" style="font-size:16px">${daily_loss:.2f}</div></div>
      <div class="stat"><div class="label">Yopilgan Net PnL</div><div class="value" id="st-net" style="font-size:16px;color:{net_color}">${pnl['net_pnl']:+.2f}</div></div>
      <div class="stat"><div class="label">Win rate</div><div class="value" id="st-wr" style="font-size:16px">{pnl['win_rate']}%</div></div>
      <div class="stat"><div class="label">Trades</div><div class="value" id="st-trades">{pnl['total_trades']}</div></div>
      <div class="stat"><div class="label">Trade $</div><div class="value" id="st-trade$" style="font-size:16px">${settings.TRADE_AMOUNT_USD:.0f}</div></div>
      <div class="stat"><div class="label">SOL balans</div><div class="value" id="st-sol" style="font-size:16px">{wallet_sol:.4f}</div></div>
      <div class="stat"><div class="label">SOL ≈ USD</div><div class="value" id="st-solusd" style="font-size:16px">${wallet_sol_usd:.2f}</div></div>
    </div>
    <div class="card">
      <h2>📈 Ochiq savdolar (jonli PnL) <span class="muted" style="font-weight:400;text-transform:none;letter-spacing:0">· har 5s</span></h2>
      <p class="muted" style="margin:0 0 12px;font-size:12px">Yashil = foyda (+) · Qizil = zarar (−). Avtomatik yangilanadi.</p>
      <div class="grid" id="open-pnl-cards">{open_pnl_cards}</div>
    </div>
    <div class="card">
      <h2>👛 Hamyon</h2>
      <div class="grid">
        <div class="stat"><div class="label">Pubkey</div><div class="value" style="font-size:13px;font-family:monospace">{_esc(wallet_short)}</div></div>
        <div class="stat"><div class="label">SOL</div><div class="value" style="font-size:16px">{wallet_sol:.6f}</div></div>
        <div class="stat"><div class="label">≈ USD</div><div class="value" style="font-size:16px">${wallet_sol_usd:.2f}</div></div>
        <div class="stat"><div class="label">Holat</div><div class="value" style="font-size:13px">{'✅ ulangan' if wallet_pubkey and not wallet_err else _esc(wallet_err or 'ulangan emas')}</div></div>
      </div>
      <p class="muted" style="margin-top:10px;font-size:12px">To'liq manzil: <code class="mono">{_esc(wallet_pubkey or '—')}</code></p>
    </div>
    <div class="card" style="border-color:{'#22c55e' if str(getattr(settings, 'DATA_DIR', 'data')).startswith('/data') else '#f59e0b'}">
      <h2>💾 Sozlamalar saqlanishi</h2>
      <div class="grid" style="margin-bottom:10px">
        <div class="stat"><div class="label">DATA_DIR</div><div class="value" style="font-size:13px;font-family:monospace">{_esc(getattr(settings, 'DATA_DIR', 'data'))}</div></div>
        <div class="stat"><div class="label">Volume</div><div class="value" style="font-size:14px">{'✅ /data' if str(getattr(settings, 'DATA_DIR', '')).startswith('/data') else '⚠️ yoq (redeployda yoqoladi)'}</div></div>
        <div class="stat"><div class="label">TG token</div><div class="value" style="font-size:14px">{'✅' if getattr(settings, 'TELEGRAM_BOT_TOKEN', '') else '❌'}</div></div>
        <div class="stat"><div class="label">PRIVATE_KEY</div><div class="value" style="font-size:14px">{'✅' if getattr(settings, 'PRIVATE_KEY', '') else '❌'}</div></div>
        <div class="stat"><div class="label">Birdeye</div><div class="value" style="font-size:14px">{'✅' if getattr(settings, 'BIRDEYE_API_KEY', '') else '❌'}</div></div>
      </div>
      <p style="margin:0;font-size:13px;line-height:1.55">
        <b>API / PRIVATE_KEY</b> → Railway <b>Variables</b> (har deployda saqlanadi).<br>
        <b>Filtrlar, trade $</b> → admin panel → <code>DATA_DIR/runtime_settings.json</code>.
        Buning uchun Volume: mount <code>/data</code> + Variable <code>DATA_DIR=/data</code>.
      </p>
    </div>
    <div class="card">
      <h2>Tezkor boshqaruv</h2>
      <form class="inline" method="post" action="/dashboard/control/start"><button class="ok" type="submit">▶ Start</button></form>
      <form class="inline" method="post" action="/dashboard/control/stop"><button class="stop" type="submit">⏹ Stop</button></form>
      <form class="inline" method="post" action="/dashboard/control/paper-toggle"><button class="warn" type="submit">Paper/Live</button></form>
      <form class="inline" method="post" action="/dashboard/control/emergency-stop"><button class="stop" type="submit">🚨 Emergency</button></form>
      <form class="inline" method="post" action="/dashboard/control/emergency-clear"><button class="ghost" type="submit">Emergency OFF</button></form>
      <form class="inline" method="post" action="/dashboard/control/resume"><button class="ghost" type="submit">Resume pause</button></form>
      <form class="inline" method="post" action="/dashboard/control/cleanup"><button class="warn" type="submit">🧹 Tozalash</button></form>
    </div>
    <div class="card">
      <h2>Advanced risk</h2>
      <div class="grid">
        <div class="stat"><div class="label">Paused</div><div class="value" style="font-size:14px">{_esc(adv.get('paused'))}</div></div>
        <div class="stat"><div class="label">Consecutive losses</div><div class="value">{_esc(adv.get('consecutive_losses', 0))}</div></div>
        <div class="stat"><div class="label">Daily trades</div><div class="value">{_esc(adv.get('daily_trades', 0))}/{_esc(adv.get('max_daily_trades', '—'))}</div></div>
        <div class="stat"><div class="label">Pause reason</div><div class="value" style="font-size:12px">{_esc(adv.get('pause_reason') or '—')}</div></div>
      </div>
    </div>
  </section>

  <section id="sec-positions" class="section">
    <div class="card">
      <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:12px">
        <h2>Ochiq pozitsiyalar</h2>
        <form class="inline" method="post" action="/dashboard/positions/close-all" onsubmit="return confirm('Haqiqatdan ham barcha pozitsiyalarni yopmoqchimisiz?');">
          <button class="stop" type="submit" style="margin:0">🚨 Hammasini yopish</button>
        </form>
      </div>
      <table><thead><tr><th>Symbol</th><th>Token</th><th>Amount</th><th>Entry</th><th>Current</th><th>PnL</th><th>AI</th><th>Mode</th><th>Action</th></tr></thead>
      <tbody id="positions-tbody">{positions_rows}</tbody></table>
    </div>
  </section>

  <section id="sec-trades" class="section">
    <div class="grid">
      <div class="stat"><div class="label">Net PnL</div><div class="value" id="tr-net" style="font-size:18px">${pnl['net_pnl']:+.2f}</div></div>
      <div class="stat"><div class="label">Profit</div><div class="value" id="tr-profit" style="font-size:18px;color:var(--ok)">${pnl['profit']:.2f}</div></div>
      <div class="stat"><div class="label">Loss</div><div class="value" id="tr-loss" style="font-size:18px;color:var(--bad)">${pnl['loss']:.2f}</div></div>
      <div class="stat"><div class="label">Best / Worst</div><div class="value" id="tr-bw" style="font-size:14px">${pnl['best']:+.2f} / ${pnl['worst']:+.2f}</div></div>
    </div>
    <div class="card"><h2>Yopilgan savdolar</h2>
      <table><thead><tr><th>Time</th><th>Symbol</th><th>PnL $</th><th>PnL %</th><th>Reason</th><th>AI</th></tr></thead>
      <tbody>{trade_rows}</tbody></table>
    </div>
  </section>

  <section id="sec-filters" class="section">
    <div class="card">
      <h2>Trading + Filter sozlamalari</h2>
      <form method="post" action="/dashboard/settings">
        <div class="form-grid">
          <div class="form-row"><label>TRADE_AMOUNT_USD</label><input type="number" step="0.1" name="TRADE_AMOUNT_USD" value="{fv('TRADE_AMOUNT_USD')}"></div>
          <div class="form-row"><label>MAX_OPEN_POSITIONS</label><input type="number" name="MAX_OPEN_POSITIONS" value="{fv('MAX_OPEN_POSITIONS')}"></div>
          <div class="form-row"><label>STOP_LOSS_PCT</label><input type="number" step="0.01" name="STOP_LOSS_PCT" value="{fv('STOP_LOSS_PCT')}"></div>
          <div class="form-row"><label>TAKE_PROFIT_PCT</label><input type="number" step="0.01" name="TAKE_PROFIT_PCT" value="{fv('TAKE_PROFIT_PCT')}"></div>
          <div class="form-row"><label>TRAILING_STOP_PCT</label><input type="number" step="0.01" name="TRAILING_STOP_PCT" value="{fv('TRAILING_STOP_PCT')}"></div>
          <div class="form-row"><label>FEE_USD_ROUNDTRIP</label><input type="number" step="0.01" name="FEE_USD_ROUNDTRIP" value="{fv('FEE_USD_ROUNDTRIP', 0.25)}"></div>
          <div class="form-row"><label>FEE_PCT_ROUNDTRIP</label><input type="number" step="0.005" name="FEE_PCT_ROUNDTRIP" value="{fv('FEE_PCT_ROUNDTRIP', 0.02)}"></div>
          <div class="form-row"><label>MAX_DAILY_LOSS_USD</label><input type="number" step="0.1" name="MAX_DAILY_LOSS_USD" value="{fv('MAX_DAILY_LOSS_USD')}"></div>
          <div class="form-row"><label>SCANNER_INTERVAL_SEC</label><input type="number" name="SCANNER_INTERVAL_SEC" value="{fv('SCANNER_INTERVAL_SEC')}"></div>
          <div class="form-row"><label>SELL_RETRY_ATTEMPTS</label><input type="number" name="SELL_RETRY_ATTEMPTS" value="{fv('SELL_RETRY_ATTEMPTS', 3)}"></div>
          <div class="form-row"><label>MIN_TOKEN_AGE_MINUTES</label><input type="number" step="0.1" name="MIN_TOKEN_AGE_MINUTES" value="{fv('MIN_TOKEN_AGE_MINUTES', 1)}"></div>
          <div class="form-row"><label>MAX_TOKEN_AGE_MINUTES</label><input type="number" step="0.1" name="MAX_TOKEN_AGE_MINUTES" value="{fv('MAX_TOKEN_AGE_MINUTES', 15)}"></div>
          <div class="form-row"><label>MIN_LIQUIDITY_USD</label><input type="number" name="MIN_LIQUIDITY_USD" value="{fv('MIN_LIQUIDITY_USD')}"></div>
          <div class="form-row"><label>MIN_MARKET_CAP_USD</label><input type="number" name="MIN_MARKET_CAP_USD" value="{fv('MIN_MARKET_CAP_USD')}"></div>
          <div class="form-row"><label>MAX_MARKET_CAP_USD</label><input type="number" name="MAX_MARKET_CAP_USD" value="{fv('MAX_MARKET_CAP_USD')}"></div>
          <div class="form-row"><label>MIN_VOLUME_5M_USD</label><input type="number" name="MIN_VOLUME_5M_USD" value="{fv('MIN_VOLUME_5M_USD')}"></div>
          <div class="form-row"><label>MIN_BUY_SELL_RATIO</label><input type="number" step="0.1" name="MIN_BUY_SELL_RATIO" value="{fv('MIN_BUY_SELL_RATIO')}"></div>
          <div class="form-row"><label>MIN_HOLDERS</label><input type="number" name="MIN_HOLDERS" value="{fv('MIN_HOLDERS')}"></div>
          <div class="form-row"><label>MAX_TOP10_HOLDER_PCT</label><input type="number" step="0.01" name="MAX_TOP10_HOLDER_PCT" value="{fv('MAX_TOP10_HOLDER_PCT')}"></div>
          <div class="form-row"><label>AI_MIN_SCORE</label><input type="number" step="0.1" name="AI_MIN_SCORE" value="{fv('AI_MIN_SCORE')}"></div>
        </div>
        <button type="submit" style="margin-top:14px">💾 Saqlash</button>
      </form>
    </div>
  </section>


  <section id="sec-api" class="section">
    <div class="card">
      <h2>API kalitlari va ulanishlar</h2>
      <p class="muted" style="margin-bottom:12px">
        Qiymatlar runtime da o'zgaradi va <code>.env</code> ga yoziladi (restart dan keyin ham saqlanadi).
        Maxfiy maydonlar masklangan — yangi qiymat yozsangiz eski o'rniga yoziladi. Bo'sh qoldirsangiz o'zgarmaydi.
      </p>
      <form method="post" action="/dashboard/settings">
        <input type="hidden" name="_section" value="api">
        <div class="form-grid">
          <div class="form-row"><label>TELEGRAM_BOT_TOKEN</label>
            <input type="password" name="TELEGRAM_BOT_TOKEN" placeholder="{tg_ph}" autocomplete="off"></div>
          <div class="form-row"><label>TELEGRAM_CHAT_ID</label>
            <input type="text" name="TELEGRAM_CHAT_ID" value="{tg_chat}"></div>
          <div class="form-row"><label>BIRDEYE_API_KEY</label>
            <input type="password" name="BIRDEYE_API_KEY" placeholder="{be_ph}" autocomplete="off"></div>
          <div class="form-row"><label>HELIUS_API_KEY</label>
            <input type="password" name="HELIUS_API_KEY" placeholder="{he_ph}" autocomplete="off"></div>
          <div class="form-row"><label>JUPITER_API_KEY</label>
            <input type="password" name="JUPITER_API_KEY" placeholder="{ju_ph}" autocomplete="off"></div>
          <div class="form-row"><label>OPENAI_API_KEY</label>
            <input type="password" name="OPENAI_API_KEY" placeholder="{oa_ph}" autocomplete="off"></div>
          <div class="form-row"><label>X_API_BEARER_TOKEN (Social)</label>
            <input type="password" name="X_API_BEARER_TOKEN" placeholder="{x_ph}" autocomplete="off"></div>
          <div class="form-row"><label>RPC_URL</label>
            <input type="text" name="RPC_URL" value="{rpc}"></div>
          <div class="form-row"><label>PRIVATE_KEY (base58)</label>
            <input type="password" name="PRIVATE_KEY" placeholder="{pk_ph}" autocomplete="off"></div>
          <div class="form-row"><label>DATABASE_URL</label>
            <input type="text" name="DATABASE_URL" value="{db_url}"></div>
          <div class="form-row"><label>REDIS_URL</label>
            <input type="text" name="REDIS_URL" value="{redis_url}"></div>
          <div class="form-row"><label>ADMIN_USERNAME</label>
            <input type="text" name="ADMIN_USERNAME" value="{admin_user}"></div>
          <div class="form-row"><label>ADMIN_PASSWORD (yangi)</label>
            <input type="password" name="ADMIN_PASSWORD" placeholder="••••" autocomplete="off"></div>
          <div class="form-row"><label>ADMIN_API_KEY</label>
            <input type="password" name="ADMIN_API_KEY" placeholder="{ak_ph}" autocomplete="off"></div>
          <div class="form-row"><label>DISCORD_WEBHOOK_URL</label>
            <input type="text" name="DISCORD_WEBHOOK_URL" value="{discord}"></div>
        </div>
        <button type="submit" style="margin-top:14px">API sozlamalarini saqlash</button>
      </form>
    </div>
  </section>

  <section id="sec-rejections" class="section">
    <div class="card"><h2>Oxirgi filter radlari</h2>
      <table><thead><tr><th>Time</th><th>Symbol</th><th>Token</th><th>Stage</th><th>Reason</th></tr></thead>
      <tbody>{rej_rows}</tbody></table>
    </div>
  </section>

  <section id="sec-blacklist" class="section">
    <div class="card"><h2>Qora ro'yxat</h2>
      <table><thead><tr><th>Token</th><th>Sabab</th><th>Source</th><th></th></tr></thead>
      <tbody>{bl_rows}</tbody></table>
      <form method="post" action="/dashboard/blacklist/add" style="margin-top:14px" class="form-grid">
        <div class="form-row"><label>Token address</label><input type="text" name="token" required></div>
        <div class="form-row"><label>Reason</label><input type="text" name="reason" value="manual"></div>
        <div class="form-row" style="display:flex;align-items:flex-end"><button type="submit">Qo'shish</button></div>
      </form>
    </div>
  </section>

  <section id="sec-ai" class="section">
    <div class="card"><h2>AI weights</h2>
      <table><thead><tr><th>Factor</th><th>Weight</th></tr></thead><tbody>{w_rows}</tbody></table>
    </div>
  </section>

  <section id="sec-modules" class="section">
    <div class="card"><h2>Modullar</h2>
      <div class="grid">
        <div class="stat"><div class="label">AI</div><div class="value" style="font-size:14px">{_bool_badge(settings.AI_ENABLED)}</div></div>
        <div class="stat"><div class="label">Smart Money</div><div class="value" style="font-size:14px">{_bool_badge(settings.SMART_MONEY_ENABLED)}</div></div>
        <div class="stat"><div class="label">Whale</div><div class="value" style="font-size:14px">{_bool_badge(settings.WHALE_TRACKING_ENABLED)}</div></div>
        <div class="stat"><div class="label">MEV</div><div class="value" style="font-size:14px">{_bool_badge(settings.MEV_PROTECTION_ENABLED)}</div></div>
        <div class="stat"><div class="label">Auto BL</div><div class="value" style="font-size:14px">{_bool_badge(settings.AUTO_BLACKLIST_ENABLED)}</div></div>
        <div class="stat"><div class="label">Paper</div><div class="value" style="font-size:14px">{_bool_badge(settings.PAPER_TRADING)}</div></div>
      </div>
      <form method="post" action="/dashboard/modules" class="form-grid" style="margin-top:12px">
        <div class="form-row"><label>AI_ENABLED (1/0)</label><input type="number" min="0" max="1" name="AI_ENABLED" value="{1 if settings.AI_ENABLED else 0}"></div>
        <div class="form-row"><label>SMART_MONEY_ENABLED</label><input type="number" min="0" max="1" name="SMART_MONEY_ENABLED" value="{1 if settings.SMART_MONEY_ENABLED else 0}"></div>
        <div class="form-row"><label>WHALE_TRACKING_ENABLED</label><input type="number" min="0" max="1" name="WHALE_TRACKING_ENABLED" value="{1 if settings.WHALE_TRACKING_ENABLED else 0}"></div>
        <div class="form-row"><label>MEV_PROTECTION_ENABLED</label><input type="number" min="0" max="1" name="MEV_PROTECTION_ENABLED" value="{1 if settings.MEV_PROTECTION_ENABLED else 0}"></div>
        <div class="form-row"><label>AUTO_BLACKLIST_ENABLED</label><input type="number" min="0" max="1" name="AUTO_BLACKLIST_ENABLED" value="{1 if settings.AUTO_BLACKLIST_ENABLED else 0}"></div>
        <div class="form-row" style="display:flex;align-items:flex-end"><button type="submit">Saqlash</button></div>
      </form>
    </div>
  </section>

  <section id="sec-logs" class="section">
    <div class="card"><h2>Oxirgi loglar</h2>
      <div style="max-height:480px;overflow:auto;background:var(--bg);padding:10px;border-radius:8px">{log_html}</div>
      <p class="muted" style="margin-top:8px">F5 bilan yangilang</p>
    </div>
  </section>

  <section id="sec-control" class="section">
    <div class="card"><h2>Bot control</h2>
      <form class="inline" method="post" action="/dashboard/control/start"><button class="ok" type="submit">▶ Start</button></form>
      <form class="inline" method="post" action="/dashboard/control/stop"><button class="stop" type="submit">⏹ Stop</button></form>
      <form class="inline" method="post" action="/dashboard/control/paper-toggle"><button class="warn" type="submit">Paper/Live</button></form>
      <form class="inline" method="post" action="/dashboard/control/emergency-stop"><button class="stop" type="submit">🚨 Emergency ON</button></form>
      <form class="inline" method="post" action="/dashboard/control/emergency-clear"><button class="ghost" type="submit">Emergency OFF</button></form>
      <form class="inline" method="post" action="/dashboard/control/resume"><button class="ghost" type="submit">Resume</button></form>
      <form class="inline" method="post" action="/dashboard/control/cleanup"><button class="warn" type="submit">🧹 Tozalash (reconcile)</button></form>
      <form class="inline" method="post" action="/dashboard/control/cleanup-full"><button class="ghost" type="submit">🧹 Kuchli tozalash</button></form>
    </div>
  </section>
</main></div>
<script>
window.mbShow = function(id) {{
  try {{
    if (!id) id = 'overview';
    var sections = document.querySelectorAll('.section');
    for (var i = 0; i < sections.length; i++) {{
      sections[i].classList.remove('active');
      sections[i].style.display = 'none';
    }}
    var sec = document.getElementById('sec-' + id);
    if (sec) {{
      sec.classList.add('active');
      sec.style.display = 'block';
    }}
    var links = document.querySelectorAll('.nav a[data-section]');
    for (var j = 0; j < links.length; j++) {{
      links[j].classList.remove('active');
      if (links[j].getAttribute('data-section') === id) {{
        links[j].classList.add('active');
      }}
    }}
    try {{ history.replaceState(null, '', '#' + id); }} catch (e1) {{}}
  }} catch (e2) {{ console.error(e2); }}
  return false;
}};
(function() {{
  var hash = (location.hash || '#overview').replace('#', '') || 'overview';
  if (document.readyState === 'loading') {{
    document.addEventListener('DOMContentLoaded', function() {{ window.mbShow(hash); }});
  }} else {{
    window.mbShow(hash);
  }}
}})();

/* live stats */
(function() {{
  function money(n) {{
    if (n === null || n === undefined || isNaN(n)) return '-';
    var x = Number(n);
    return '$' + (x >= 0 ? '+' : '') + x.toFixed(2);
  }}
  function esc(s) {{
    return String(s == null ? '' : s)
      .replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
  }}
  function setTxt(id, v) {{
    var el = document.getElementById(id);
    if (el) el.textContent = v;
  }}
  function setColor(id, c) {{
    var el = document.getElementById(id);
    if (el) el.style.color = c;
  }}
  async function poll() {{
    var dot = document.getElementById('live-dot');
    try {{
      var r = await fetch('/dashboard/live', {{ credentials: 'same-origin', cache: 'no-store' }});
      if (!r.ok) {{ if (dot) dot.style.background = '#ef4444'; return; }}
      var d = await r.json();
      if (dot) {{ dot.style.background = '#22c55e'; }}
      var ts = document.getElementById('live-ts');
      if (ts) ts.textContent = 'yangilandi ' + new Date().toLocaleTimeString();
      setTxt('st-bot', d.running ? 'OK' : 'STOP');
      setTxt('st-mode', d.paper ? 'PAPER' : 'LIVE');
      setTxt('st-open', (d.open_count || 0) + '/' + (d.max_open || 5));
      if (d.unrealized_pnl == null) setTxt('st-upnl', '-');
      else {{ setTxt('st-upnl', money(d.unrealized_pnl)); setColor('st-upnl', d.unrealized_pnl >= 0 ? '#22c55e' : '#ef4444'); }}
      setTxt('st-dloss', '$' + Number(d.daily_loss || 0).toFixed(2));
      setTxt('st-net', money(d.net_pnl));
      setColor('st-net', (d.net_pnl || 0) >= 0 ? '#22c55e' : '#ef4444');
      setTxt('st-wr', (d.win_rate || 0) + '%');
      setTxt('st-trades', d.total_trades || 0);
      setTxt('st-trade$', '$' + Number(d.trade_amount || 0).toFixed(0));
      setTxt('st-sol', Number(d.wallet_sol || 0).toFixed(4));
      setTxt('st-solusd', '$' + Number(d.wallet_usd || 0).toFixed(2));
      setTxt('tr-net', money(d.net_pnl));
      setTxt('tr-profit', '$' + Number(d.profit || 0).toFixed(2));
      setTxt('tr-loss', '$' + Number(d.loss || 0).toFixed(2));
      setTxt('tr-bw', money(d.best) + ' / ' + money(d.worst));
      var cards = document.getElementById('open-pnl-cards');
      if (cards) {{
        var pos = d.positions || [];
        if (!pos.length) {{
          cards.innerHTML = '<div class="pnl-card wait"><div class="pnl-val wait">Hozircha ochiq savdo yo\'q</div></div>';
        }} else {{
          var html = '';
          for (var i = 0; i < pos.length; i++) {{
            var p = pos[i];
            var ok = (p.current_price || 0) > 0 && (p.entry_price || 0) > 0;
            var side = !ok ? 'wait' : (p.pnl_usd >= 0 ? 'pos' : 'neg');
            var absPnl = Math.abs(Number(p.pnl_usd || 0)).toFixed(2);
            var sign = (p.pnl_usd >= 0) ? '+' : '';
            var pct = (p.pnl_pct >= 0 ? '+' : '') + Number(p.pnl_pct || 0).toFixed(1) + '%';
            if (!ok) {{
              html += '<div class="pnl-card wait"><div><span class="sym">' + esc(p.symbol) +
                '</span><span class="amt">$' + Number(p.amount_usd || 0).toFixed(0) +
                '</span></div><div class="pnl-val wait">narx kutilmoqda…</div></div>';
            }} else {{
              html += '<div class="pnl-card ' + side + '"><div><span class="sym">' + esc(p.symbol) +
                '</span><span class="amt">$' + Number(p.amount_usd || 0).toFixed(0) +
                '</span></div><div class="pnl-val ' + side + '">' + sign + '$' + absPnl +
                '</div><span class="pct-pill ' + side + '">' + pct + '</span></div>';
            }}
          }}
          cards.innerHTML = html;
        }}
      }}
      var tbody = document.getElementById('positions-tbody');
      if (tbody) {{
        var pos2 = d.positions || [];
        if (!pos2.length) {{
          tbody.innerHTML = '<tr><td colspan="9" class="muted">Ochiq pozitsiya yoq</td></tr>';
        }} else {{
          var rows = '';
          for (var k = 0; k < pos2.length; k++) {{
            var p2 = pos2[k];
            var ok2 = (p2.current_price || 0) > 0 && (p2.entry_price || 0) > 0;
            var cls = !ok2 ? 'muted' : (p2.pnl_usd >= 0 ? 'pnl-pos' : 'pnl-neg');
            var pnl2 = !ok2 ? '...' : money(p2.pnl_usd) + ' (' + Number(p2.pnl_pct).toFixed(1) + '%)';
            var cur2 = ok2 ? ('$' + Number(p2.current_price).toFixed(8)) : '-';
            var tok = esc(p2.token || '');
            var copyOnclick = "navigator.clipboard.writeText('" + tok + "');this.textContent='✓';setTimeout(function(){{this.textContent='Copy';}}.bind(this),1200)";
            rows += '<tr><td><strong>' + esc(p2.symbol) + '</strong></td><td><div class="token-full">' +
              '<a href="https://solscan.io/token/' + tok + '" target="_blank" rel="noopener" title="Solscan">' + tok + '</a>' +
              '<button type="button" class="copy-btn" onclick="' + copyOnclick + '">Copy</button>' +
              '</div></td><td>$' + Number(p2.amount_usd||0).toFixed(2) +
              '</td><td class="mono">$' + Number(p2.entry_price||0).toFixed(8) +
              '</td><td class="mono">' + cur2 + '</td><td class="' + cls + '" style="font-weight:700">' +
              pnl2 + '</td><td>' + esc(p2.ai_score != null ? p2.ai_score : '-') +
              '</td><td class="muted">' + (p2.paper ? 'PAPER' : 'LIVE') +
              '</td><td><form class="inline" method="post" action="/dashboard/positions/close">' +
              '<input type="hidden" name="token" value="' + tok + '">' +
              '<button class="stop" type="submit" style="padding:4px 8px;font-size:11px">Yopish</button></form></td></tr>';
          }}
          tbody.innerHTML = rows;
        }}
      }}
    }} catch (err) {{
      if (dot) dot.style.background = '#f59e0b';
      console.warn('live', err);
    }}
  }}
  setTimeout(function() {{ poll(); setInterval(poll, 5000); }}, 500);
}})();
</script>
</body></html>"""


def create_admin_app(bot_ref=None) -> FastAPI:
    app = FastAPI(title="MemeBot Pro Admin", version="2.0.0")
    app.add_middleware(SessionMiddleware, secret_key=settings.ADMIN_SESSION_SECRET)

    @app.get("/login", response_class=HTMLResponse)
    async def login_page():
        return _login_page()

    @app.post("/login")
    async def login_submit(request: Request, username: str = Form(...), password: str = Form(...)):
        if username == settings.ADMIN_USERNAME and password == settings.ADMIN_PASSWORD:
            request.session["authenticated"] = True
            return RedirectResponse(url="/", status_code=303)
        return HTMLResponse(_login_page(error="Login yoki parol xato"), status_code=401)

    @app.get("/logout")
    async def logout(request: Request):
        request.session.clear()
        return RedirectResponse(url="/login", status_code=303)

    @app.get("/", response_class=HTMLResponse)
    async def dashboard(request: Request):
        if (r := _require_web_auth(request)):
            return r
        return await _dashboard_html(bot_ref)

    @app.get("/dashboard/live")
    async def dashboard_live(request: Request):
        """Jonli statistika — frontend har 5s da so'raydi."""
        if not _is_logged_in(request):
            raise HTTPException(status_code=401, detail="login required")
        return await _live_snapshot(bot_ref)

    async def _gate(request: Request):
        return _require_web_auth(request)

    @app.post("/dashboard/control/start")
    async def dash_start(request: Request):
        if r := await _gate(request):
            return r
        if bot_ref and hasattr(bot_ref, "risk"):
            await bot_ref.risk.set_bot_running(True)
        if bot_ref and hasattr(bot_ref, "advanced_risk"):
            bot_ref.advanced_risk.resume()
        settings.BOT_RUNNING = True
        history.add_event("info", "Bot STARTED")
        return RedirectResponse(url="/#control", status_code=303)

    @app.post("/dashboard/control/stop")
    async def dash_stop(request: Request):
        if r := await _gate(request):
            return r
        if bot_ref and hasattr(bot_ref, "risk"):
            await bot_ref.risk.set_bot_running(False)
        settings.BOT_RUNNING = False
        history.add_event("info", "Bot STOPPED")
        return RedirectResponse(url="/#control", status_code=303)

    @app.post("/dashboard/control/emergency-stop")
    async def dash_emergency(request: Request):
        if r := await _gate(request):
            return r
        if bot_ref and hasattr(bot_ref, "advanced_risk"):
            bot_ref.advanced_risk.set_emergency_stop(True)
        settings.EMERGENCY_STOP = True
        return RedirectResponse(url="/#control", status_code=303)

    @app.post("/dashboard/control/emergency-clear")
    async def dash_emergency_clear(request: Request):
        if r := await _gate(request):
            return r
        if bot_ref and hasattr(bot_ref, "advanced_risk"):
            bot_ref.advanced_risk.set_emergency_stop(False)
        settings.EMERGENCY_STOP = False
        return RedirectResponse(url="/#control", status_code=303)

    @app.post("/dashboard/control/resume")
    async def dash_resume(request: Request):
        if r := await _gate(request):
            return r
        if bot_ref and hasattr(bot_ref, "advanced_risk"):
            bot_ref.advanced_risk.resume()
        return RedirectResponse(url="/#control", status_code=303)

    @app.post("/dashboard/control/paper-toggle")
    async def dash_paper(request: Request):
        if r := await _gate(request):
            return r
        settings.PAPER_TRADING = not settings.PAPER_TRADING
        return RedirectResponse(url="/#control", status_code=303)

    @app.post("/dashboard/control/cleanup")
    async def dash_cleanup(request: Request):
        """Ghost pozitsiyalar + cooldown + scanner cache."""
        if r := await _gate(request):
            return r
        if bot_ref and hasattr(bot_ref, "cleaner"):
            try:
                await bot_ref.cleaner.full_cleanup(
                    reconcile=True,
                    clear_cooldowns=True,
                    clear_processed=True,
                    reset_daily_loss=False,
                    clear_history=False,
                    clear_positions=False,
                )
            except Exception as e:
                from utils.logger import logger as _log
                _log.warning(f"Admin cleanup xato: {e}")
        return RedirectResponse(url="/#control", status_code=303)

    @app.post("/dashboard/control/cleanup-full")
    async def dash_cleanup_full(request: Request):
        """+ kunlik zarar va tarix tozalash."""
        if r := await _gate(request):
            return r
        if bot_ref and hasattr(bot_ref, "cleaner"):
            try:
                await bot_ref.cleaner.full_cleanup(
                    reconcile=True,
                    clear_cooldowns=True,
                    clear_processed=True,
                    reset_daily_loss=True,
                    clear_history=True,
                    clear_positions=False,
                )
            except Exception as e:
                from utils.logger import logger as _log
                _log.warning(f"Admin cleanup-full xato: {e}")
        return RedirectResponse(url="/#control", status_code=303)

    @app.post("/dashboard/positions/close")
    async def dash_close_position(request: Request, token: str = Form(...)):
        if r := await _gate(request):
            return r
        if bot_ref and hasattr(bot_ref, "monitor") and hasattr(bot_ref, "risk"):
            positions = await bot_ref.risk.get_open_positions()
            pos = positions.get(token)
            if pos:
                price = await bot_ref.monitor.get_current_price(token)
                if price <= 0:
                    price = float(pos.get("current_price") or pos.get("entry_price") or 0)
                await bot_ref.monitor.close_position(token, pos, "admin_force", price)
        return RedirectResponse(url="/#positions", status_code=303)

    @app.post("/dashboard/positions/close-all")
    async def dash_close_all_positions(request: Request):
        if r := await _gate(request):
            return r
        if bot_ref and hasattr(bot_ref, "monitor") and hasattr(bot_ref, "risk"):
            positions = await bot_ref.risk.get_open_positions()
            async def _close_one(token: str, pos: dict):
                price = await bot_ref.monitor.get_current_price(token)
                if price <= 0:
                    price = float(pos.get("current_price") or pos.get("entry_price") or 0)
                await bot_ref.monitor.close_position(token, pos, "admin_force", price)
            if positions:
                await asyncio.gather(*(_close_one(token, pos) for token, pos in positions.items()))
        return RedirectResponse(url="/#positions", status_code=303)

    @app.post("/dashboard/blacklist/add")
    async def dash_bl_add(request: Request, token: str = Form(...), reason: str = Form("manual")):
        if r := await _gate(request):
            return r
        if bot_ref and hasattr(bot_ref, "blacklist"):
            bot_ref.blacklist.add(token.strip(), reason, "", source="admin")
        return RedirectResponse(url="/#blacklist", status_code=303)

    @app.post("/dashboard/blacklist/remove")
    async def dash_bl_rm(request: Request, token: str = Form(...)):
        if r := await _gate(request):
            return r
        if bot_ref and hasattr(bot_ref, "blacklist"):
            bot_ref.blacklist.remove(token)
        return RedirectResponse(url="/#blacklist", status_code=303)

    @app.post("/dashboard/settings")
    async def dash_settings(request: Request):
        if r := await _gate(request):
            return r
        form = await request.form()
        section = str(form.get("_section") or "filters")

        float_keys = {
            "TRADE_AMOUNT_USD", "STOP_LOSS_PCT", "TAKE_PROFIT_PCT", "TRAILING_STOP_PCT",
            "FEE_USD_ROUNDTRIP", "FEE_PCT_ROUNDTRIP",
            "MAX_DAILY_LOSS_USD", "MIN_TOKEN_AGE_MINUTES", "MAX_TOKEN_AGE_MINUTES",
            "MIN_LIQUIDITY_USD", "MAX_LIQUIDITY_USD", "MIN_MARKET_CAP_USD", "MAX_MARKET_CAP_USD",
            "MIN_VOLUME_5M_USD", "MIN_24H_VOLUME_USD", "MIN_BUY_SELL_RATIO", "MAX_TOP10_HOLDER_PCT",
            "MAX_DEV_WALLET_PCT", "AI_MIN_SCORE", "AI_BUY_THRESHOLD", "AI_STRONG_BUY_THRESHOLD",
            "POSITION_RISK_PCT", "MAX_RISK_PER_TOKEN_USD", "MAX_DRAWDOWN_PCT",
            "SMART_MONEY_MIN_ROI_PCT", "SMART_MONEY_MIN_WIN_RATE", "SMART_MONEY_SCORE_BOOST",
            "WHALE_BUY_SCORE_BOOST", "WHALE_SELL_SCORE_PENALTY", "MEV_SANDWICH_RISK_THRESHOLD",
        }
        int_keys = {
            "MAX_OPEN_POSITIONS", "SCANNER_INTERVAL_SEC", "SELL_RETRY_ATTEMPTS", "MIN_HOLDERS",
            "POSITION_MONITOR_INTERVAL_SEC", "COOLDOWN_MINUTES", "MAX_CONSECUTIVE_LOSSES",
            "MAX_DAILY_TRADES", "SLIPPAGE_BPS", "PRIORITY_FEE_MICROLAMPORTS",
            "SMART_MONEY_MIN_TRADES", "MEV_MAX_SLIPPAGE_BPS", "MEV_RETRY_ATTEMPTS",
            "ADMIN_API_PORT", "EMAIL_SMTP_PORT",
        }
        str_keys = {
            "TELEGRAM_CHAT_ID", "RPC_URL", "DATABASE_URL", "REDIS_URL",
            "ADMIN_USERNAME", "DISCORD_WEBHOOK_URL", "EMAIL_SMTP_HOST",
            "EMAIL_USER", "EMAIL_TO", "WHALE_THRESHOLDS_USD",
        }
        # Secret keys: empty input = keep previous value
        secret_keys = set(SECRET_SETTING_KEYS)

        updated = []
        for k in float_keys:
            if k in form and hasattr(settings, k):
                try:
                    value = float(form[k])
                    setattr(settings, k, value)
                    _persist_to_env(k, value)
                    updated.append(k)
                except (TypeError, ValueError):
                    pass
        for k in int_keys:
            if k in form and hasattr(settings, k):
                try:
                    value = int(float(form[k]))
                    setattr(settings, k, value)
                    _persist_to_env(k, value)
                    updated.append(k)
                except (TypeError, ValueError):
                    pass
        for k in str_keys:
            if k in form and hasattr(settings, k):
                value = str(form[k]).strip()
                setattr(settings, k, value)
                _persist_to_env(k, value)
                updated.append(k)
        for k in secret_keys:
            if k in form and hasattr(settings, k):
                value = str(form[k]).strip()
                if not value:
                    continue  # bo'sh = o'zgartirmaslik
                setattr(settings, k, value)
                _persist_to_env(k, value)
                updated.append(k)

        if updated:
            history.add_event("admin", f"Settings saved ({section}): {', '.join(updated)}")
        anchor = "api" if section == "api" else "filters"
        return RedirectResponse(url=f"/#{anchor}", status_code=303)


    @app.post("/dashboard/modules")
    async def dash_modules(request: Request):
        if r := await _gate(request):
            return r
        form = await request.form()
        for k in ("AI_ENABLED", "SMART_MONEY_ENABLED", "WHALE_TRACKING_ENABLED",
                  "MEV_PROTECTION_ENABLED", "AUTO_BLACKLIST_ENABLED"):
            if k in form and hasattr(settings, k):
                value = str(form[k]) in ("1", "true", "True", "on")
                setattr(settings, k, value)
                _persist_to_env(k, "1" if value else "0")
        return RedirectResponse(url="/#modules", status_code=303)

    @app.get("/health")
    async def health():
        return {"status": "ok", "paper": settings.PAPER_TRADING, "version": "2.0.0"}

    @app.get("/settings", dependencies=[Depends(_auth)])
    async def get_settings():
        data = settings.model_dump()
        for secret in ("PRIVATE_KEY", "TELEGRAM_BOT_TOKEN", "BIRDEYE_API_KEY",
                       "HELIUS_API_KEY", "OPENAI_API_KEY", "EMAIL_PASSWORD",
                       "ADMIN_API_KEY", "ADMIN_PASSWORD", "ADMIN_SESSION_SECRET"):
            if secret in data and data[secret]:
                data[secret] = "***"
        return data

    @app.post("/settings", dependencies=[Depends(_auth)])
    async def update_setting(body: SettingUpdate):
        key = body.key
        if not hasattr(settings, key):
            raise HTTPException(400, f"Unknown setting: {key}")
        value = body.value
        # empty secret => no-op
        if key in SECRET_SETTING_KEYS and (value is None or str(value).strip() == ""):
            return {"ok": True, "skipped": True, "key": key}
        try:
            cur = getattr(settings, key)
            if isinstance(cur, bool):
                value = bool(value) if not isinstance(value, str) else value.lower() in ("1", "true", "yes", "on")
            elif isinstance(cur, int) and not isinstance(cur, bool):
                value = int(value)
            elif isinstance(cur, float):
                value = float(value)
            else:
                value = value if value is not None else ""
            setattr(settings, key, value)
            _persist_to_env(key, value)
            history.add_event("admin", f"API setting {key} updated")
            return {"ok": True, "key": key}
        except Exception as e:
            raise HTTPException(400, str(e))


    @app.get("/status", dependencies=[Depends(_auth)])
    async def status():
        out: Dict[str, Any] = {
            "paper_trading": settings.PAPER_TRADING,
            "bot_running": settings.BOT_RUNNING,
            "pnl": history.pnl_summary(),
        }
        if bot_ref:
            if hasattr(bot_ref, "advanced_risk"):
                out["risk"] = bot_ref.advanced_risk.status()
            if hasattr(bot_ref, "health"):
                out["health"] = bot_ref.health.status()
            if hasattr(bot_ref, "risk"):
                positions = await bot_ref.risk.get_open_positions()
                out["open_positions"] = len(positions)
                out["positions"] = {
                    k: {"symbol": v.get("symbol"), "amount_usd": v.get("amount_usd")}
                    for k, v in positions.items()
                }
        return out

    @app.get("/rejections", dependencies=[Depends(_auth)])
    async def api_rejections(limit: int = 50):
        return history.list_rejections(limit)

    @app.get("/trades", dependencies=[Depends(_auth)])
    async def api_trades(limit: int = 50):
        return history.list_trades(limit)

    @app.post("/control/start", dependencies=[Depends(_auth)])
    async def start_bot():
        if bot_ref and hasattr(bot_ref, "risk"):
            await bot_ref.risk.set_bot_running(True)
        if bot_ref and hasattr(bot_ref, "advanced_risk"):
            bot_ref.advanced_risk.resume()
        settings.BOT_RUNNING = True
        return {"ok": True, "running": True}

    @app.post("/control/stop", dependencies=[Depends(_auth)])
    async def stop_bot():
        if bot_ref and hasattr(bot_ref, "risk"):
            await bot_ref.risk.set_bot_running(False)
        settings.BOT_RUNNING = False
        return {"ok": True, "running": False}

    @app.post("/control/cleanup", dependencies=[Depends(_auth)])
    async def api_cleanup(full: bool = False):
        """Ghost pozitsiya + cooldown + scanner cache. full=1 → + daily loss + history."""
        if not bot_ref or not hasattr(bot_ref, "cleaner"):
            return {"ok": False, "error": "cleaner not attached"}
        report = await bot_ref.cleaner.full_cleanup(
            reconcile=True,
            clear_cooldowns=True,
            clear_processed=True,
            reset_daily_loss=bool(full),
            clear_history=bool(full),
            clear_positions=False,
        )
        return {"ok": True, "report": report}

    @app.post("/control/emergency-stop", dependencies=[Depends(_auth)])
    async def emergency():
        if bot_ref and hasattr(bot_ref, "advanced_risk"):
            bot_ref.advanced_risk.set_emergency_stop(True)
        settings.EMERGENCY_STOP = True
        return {"ok": True, "emergency_stop": True}

    @app.post("/control/emergency-clear", dependencies=[Depends(_auth)])
    async def emergency_clear():
        if bot_ref and hasattr(bot_ref, "advanced_risk"):
            bot_ref.advanced_risk.set_emergency_stop(False)
        settings.EMERGENCY_STOP = False
        return {"ok": True, "emergency_stop": False}

    @app.post("/control/paper-toggle", dependencies=[Depends(_auth)])
    async def paper_toggle():
        settings.PAPER_TRADING = not settings.PAPER_TRADING
        return {"ok": True, "paper_trading": settings.PAPER_TRADING}

    @app.get("/blacklist", dependencies=[Depends(_auth)])
    async def list_blacklist():
        if bot_ref and hasattr(bot_ref, "blacklist"):
            return bot_ref.blacklist.list_all()
        return []

    @app.post("/blacklist/add", dependencies=[Depends(_auth)])
    async def add_blacklist(token: str, reason: str = "manual", details: str = ""):
        if bot_ref and hasattr(bot_ref, "blacklist"):
            bot_ref.blacklist.add(token, reason, details, source="admin")
            return {"ok": True}
        raise HTTPException(500, "Blacklist not available")

    @app.delete("/blacklist/{token}", dependencies=[Depends(_auth)])
    async def remove_blacklist(token: str):
        if bot_ref and hasattr(bot_ref, "blacklist"):
            return {"ok": bot_ref.blacklist.remove(token)}
        raise HTTPException(500, "Blacklist not available")

    @app.get("/ai/weights", dependencies=[Depends(_auth)])
    async def ai_weights():
        if bot_ref and hasattr(bot_ref, "learner"):
            return bot_ref.learner.get_weights()
        return {}

    @app.get("/modules", dependencies=[Depends(_auth)])
    async def modules():
        return {
            "ai_engine": settings.AI_ENABLED,
            "smart_money": settings.SMART_MONEY_ENABLED,
            "whale_tracking": settings.WHALE_TRACKING_ENABLED,
            "mev_protection": settings.MEV_PROTECTION_ENABLED,
            "auto_blacklist": settings.AUTO_BLACKLIST_ENABLED,
            "paper_trading": settings.PAPER_TRADING,
        }

    # ─────────── Oddiy foydalanuvchi (login yo'q) ───────────
    @app.get("/user", response_class=HTMLResponse)
    async def user_page(request: Request, token: str = ""):
        """Public sahifa: status + token tekshirish. Login talab qilinmaydi."""
        if not getattr(settings, "PUBLIC_BOT_ENABLED", True):
            return HTMLResponse(
                "<html><body style='background:#0b0e14;color:#e8eaed;font-family:sans-serif;padding:40px'>"
                "<h2>Public rejim o'chirilgan</h2><p>Admin PUBLIC_BOT_ENABLED=true qilsin.</p></body></html>",
                status_code=403,
            )
        pnl = history.pnl_summary()
        open_count = 0
        if bot_ref and hasattr(bot_ref, "risk"):
            try:
                summary = await bot_ref.risk.get_status_summary()
                open_count = summary.get("open_positions", 0)
            except Exception:
                pass
        analysis = ""
        tok = (token or "").strip()
        if tok and len(tok) >= 30 and bot_ref and getattr(bot_ref, "_session", None):
            try:
                import aiohttp
                from scanner.dexscreener import _normalize_pair
                from utils.helpers import safe_float
                url = f"https://api.dexscreener.com/latest/dex/tokens/{tok}"
                async with bot_ref._session.get(url, timeout=aiohttp.ClientTimeout(total=12)) as r:
                    if r.status == 200:
                        data = await r.json()
                        pairs = data.get("pairs") or []
                        sol = [p for p in pairs if p.get("chainId") == "solana"]
                        sol.sort(key=lambda p: safe_float((p.get("liquidity") or {}).get("usd")), reverse=True)
                        if sol:
                            pair = _normalize_pair(sol[0])
                            passed, reason, enriched = await bot_ref.filter_pipeline.run(pair, bot_ref._session)
                            ai = bot_ref.scorer.score(enriched)
                            analysis = f"""
                            <div class="card">
                              <h2>🔍 Token tahlili: {_esc(enriched.get('symbol','?'))}</h2>
                              <p><span class="muted">Nomi:</span> {_esc(enriched.get('name','?'))}</p>
                              <p><span class="muted">Narx:</span> ${enriched.get('price_usd',0):.10f}</p>
                              <p><span class="muted">Liq:</span> ${enriched.get('liquidity_usd',0):,.0f}
                                 · <span class="muted">Vol5m:</span> ${enriched.get('volume_5m',0):,.0f}
                                 · <span class="muted">MC:</span> ${enriched.get('market_cap',0):,.0f}</p>
                              <p><span class="muted">Filtr:</span> {'✅ O\'tdi' if passed else '❌ O\'tmadi'} — {_esc(reason)}</p>
                              <p><span class="muted">AI:</span> <strong>{ai.score:.1f}</strong> / 100 · {_esc(ai.recommendation.value)}</p>
                            </div>"""
                        else:
                            analysis = '<div class="card"><p class="muted">Solana juftligi topilmadi</p></div>'
                    else:
                        analysis = f'<div class="card"><p class="muted">DexScreener xato: {r.status}</p></div>'
            except Exception as e:
                analysis = f'<div class="card"><p class="muted">Xato: {_esc(str(e)[:120])}</p></div>'

        return f"""<!DOCTYPE html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>MemeBot — Foydalanuvchi</title>{PAGE_STYLE}</head><body>
<div style="max-width:720px;margin:0 auto;padding:24px">
  <div class="topbar"><h1>MemeBot Pro <span style="color:var(--muted);font-weight:400">· foydalanuvchi</span></h1>
    <a href="/login" style="font-size:13px">Admin kirish →</a></div>
  <div class="grid">
    <div class="stat"><div class="label">Bot</div><div class="value">{'✅' if settings.BOT_RUNNING else '🛑'}</div></div>
    <div class="stat"><div class="label">Mode</div><div class="value" style="font-size:15px">{'PAPER' if settings.PAPER_TRADING else 'LIVE'}</div></div>
    <div class="stat"><div class="label">Ochiq</div><div class="value">{open_count}</div></div>
    <div class="stat"><div class="label">Net PnL</div><div class="value" style="font-size:15px">${pnl['net_pnl']:+.2f}</div></div>
    <div class="stat"><div class="label">Win rate</div><div class="value" style="font-size:15px">{pnl['win_rate']}%</div></div>
    <div class="stat"><div class="label">Savdolar</div><div class="value">{pnl['total_trades']}</div></div>
  </div>
  <div class="card">
    <h2>🔍 Token tekshirish</h2>
    <form method="get" action="/user" style="display:flex;gap:8px;flex-wrap:wrap">
      <input name="token" value="{_esc(tok)}" placeholder="Solana mint address..." style="flex:1;min-width:220px;padding:10px 12px;border-radius:8px;border:1px solid var(--border);background:var(--bg);color:var(--text)">
      <button class="ok" type="submit">Tahlil qilish</button>
    </form>
  </div>
  {analysis}
  <p class="muted" style="margin-top:20px;font-size:12px">Bu sahifa oddiy foydalanuvchilar uchun. Savdo va sozlamalar faqat admin panelda.</p>
</div></body></html>"""

    return app
