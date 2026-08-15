"""Social Intelligence — X.com postlaridan token uchun ijtimoiy signal.

Muhim cheklovlar (ataylab):
- Sentiment/fake-hype/bot-activity baholari ODDIY LEKSIKON/EVRISTIKA
  asosida hisoblanadi (bag-of-words + oddiy heuristika), haqiqiy NLP/ML
  modeli EMAS. Bu section 5 dagi "Sentiment", "Fake Hype Score", "Bot
  Activity Detection" talablarini boshlang'ich, ishlaydigan darajada
  qondiradi; keyinchalik shu funksiyalarni chin ML model bilan
  almashtirish mumkin (interfeys — kirish/chiqish shakli — o'zgarmaydi).
- X API bepul/quyi tariflarda juda kam so'rovga ruxsat beradi. Shuning
  uchun kunlik byudjet (``SOCIAL_MAX_CALLS_PER_DAY``) va keshlash
  (``SOCIAL_CACHE_TTL_MIN``) qo'llaniladi — kvota tugasa yangi so'rov
  yuborilmaydi, faqat neytral ball qaytadi.
- Har qanday xato/limit/o'chirilgan holatda ``get_social_score`` HECH
  QACHON exception tashlamaydi — botning skanerlash oqimini
  to'xtatmaydi.
"""
from __future__ import annotations

import re
import time
from collections import Counter
from dataclasses import dataclass
from datetime import date
from typing import Any, Optional

from config.settings import settings
from utils.logger import logger
from utils.helpers import safe_float, safe_int
from social_intelligence.client import XApiClient

try:
    from database.repository import social_score_repo
except Exception:  # DB qatlami o'rnatilmagan bo'lishi mumkin
    social_score_repo = None


_POSITIVE_WORDS = {
    "moon", "mooning", "pump", "pumping", "bullish", "gem", "gems", "based",
    "lfg", "send", "sending", "hodl", "hold", "buy", "accumulate", "breakout",
    "strong", "solid", "safe", "legit", "chad", "king", "print", "printing",
    "ath", "🚀", "📈", "💎", "🔥",
}
_NEGATIVE_WORDS = {
    "rug", "rugged", "rugpull", "scam", "dump", "dumping", "bearish", "dead",
    "honeypot", "avoid", "warning", "sus", "suspicious", "fake", "ponzi",
    "exit", "dumped", "crash", "🚨", "⚠️", "💀", "📉",
}


@dataclass
class SocialMetrics:
    mention_count: int = 0
    engagement: int = 0
    like_count: int = 0
    reply_count: int = 0
    repost_count: int = 0
    verified_mentions: int = 0
    influencer_mentions: int = 0
    sentiment_positive_pct: float = 0.0
    sentiment_negative_pct: float = 0.0
    sentiment_neutral_pct: float = 0.0
    trend_score: float = 0.0
    virality_score: float = 0.0
    fake_hype_score: float = 0.0
    bot_activity_score: float = 0.0
    social_confidence: float = 0.0
    social_score: float = 0.0  # 0..1, AI Score ichiga qo'shiladigan yakuniy qiymat


def _tokenize(text: str) -> list[str]:
    return re.findall(r"[a-z0-9🚀📈💎🔥🚨⚠️💀📉]+", text.lower())


def _score_sentiment(texts: list[str]) -> tuple[float, float, float]:
    """Oddiy leksikon asosidagi sentiment — haqiqiy NLP model emas."""
    pos = neg = neu = 0
    for t in texts:
        words = set(_tokenize(t))
        has_pos = bool(words & _POSITIVE_WORDS)
        has_neg = bool(words & _NEGATIVE_WORDS)
        if has_pos and not has_neg:
            pos += 1
        elif has_neg and not has_pos:
            neg += 1
        else:
            neu += 1
    total = max(1, pos + neg + neu)
    return pos / total, neg / total, neu / total


def _fake_hype_and_bot_scores(texts: list[str]) -> tuple[float, float]:
    """Evristika: matnlarning ko'p qismi deyarli bir xil bo'lsa (copy-paste
    hype/bot kampaniyasi belgisi), fake_hype/bot_activity ball yuqori chiqadi."""
    if len(texts) < 3:
        return 0.0, 0.0
    normalized = [re.sub(r"\s+", " ", t.strip().lower()) for t in texts]
    counts = Counter(normalized)
    most_common_count = counts.most_common(1)[0][1]
    duplicate_ratio = most_common_count / len(normalized)
    # Ko'p postlar deyarli bir xil matn bo'lsa — hype/bot ehtimoli yuqori
    fake_hype = min(1.0, max(0.0, (duplicate_ratio - 0.2) / 0.6))
    bot_activity = fake_hype  # xuddi shu signal, hozircha bir xil evristika
    return fake_hype, bot_activity


class SocialAnalyzer:
    def __init__(self, client: Optional[XApiClient] = None):
        self.client = client or XApiClient()
        self._cache: dict[str, tuple[float, SocialMetrics]] = {}  # token -> (ts, metrics)
        self._budget_date: date = date.today()
        self._budget_used: int = 0

    async def close(self) -> None:
        await self.client.close()

    def _reset_budget_if_needed(self) -> None:
        today = date.today()
        if today != self._budget_date:
            self._budget_date = today
            self._budget_used = 0

    def _budget_available(self) -> bool:
        self._reset_budget_if_needed()
        return self._budget_used < settings.SOCIAL_MAX_CALLS_PER_DAY

    def _cached(self, token: str) -> Optional[SocialMetrics]:
        entry = self._cache.get(token)
        if not entry:
            return None
        ts, metrics = entry
        if time.time() - ts > settings.SOCIAL_CACHE_TTL_MIN * 60:
            return None
        return metrics

    def _neutral(self) -> SocialMetrics:
        return SocialMetrics(social_score=0.5, sentiment_neutral_pct=1.0)

    async def analyze(self, token_address: str, symbol: str) -> SocialMetrics:
        """Token/symbol uchun ijtimoiy metrikalarni qaytaradi. Hech qachon
        exception tashlamaydi — muvaffaqiyatsizlikda neytral ball beradi."""
        if not settings.SOCIAL_INTELLIGENCE_ENABLED or not self.client.configured:
            return self._neutral()

        cached = self._cached(token_address)
        if cached is not None:
            return cached

        if not self._budget_available():
            logger.debug("Social Intelligence kunlik byudjeti tugadi — neytral ball")
            return self._neutral()

        query_symbol = (symbol or "").lstrip("$").strip()
        if not query_symbol:
            return self._neutral()
        query = f"(${query_symbol} OR {token_address}) -is:retweet lang:en"

        try:
            self._budget_used += 1
            raw = await self.client.search_recent(query, max_results=25)
        except Exception as e:
            logger.debug(f"Social Intelligence so'rovida kutilmagan xato: {e}")
            return self._neutral()

        if not raw or "data" not in raw:
            metrics = self._neutral()
            self._cache[token_address] = (time.time(), metrics)
            return metrics

        tweets: list[dict[str, Any]] = raw.get("data", [])
        users_by_id = {u["id"]: u for u in raw.get("includes", {}).get("users", [])}

        texts = [t.get("text", "") for t in tweets]
        like = reply = repost = 0
        verified_mentions = 0
        influencer_mentions = 0
        for t in tweets:
            pm = t.get("public_metrics", {}) or {}
            like += safe_int(pm.get("like_count"))
            reply += safe_int(pm.get("reply_count"))
            repost += safe_int(pm.get("retweet_count")) + safe_int(pm.get("quote_count"))
            author = users_by_id.get(t.get("author_id"))
            if author:
                if author.get("verified"):
                    verified_mentions += 1
                followers = safe_int((author.get("public_metrics") or {}).get("followers_count"))
                if followers >= settings.SOCIAL_INFLUENCER_FOLLOWER_THRESHOLD:
                    influencer_mentions += 1

        mention_count = len(tweets)
        engagement = like + reply + repost
        pos_pct, neg_pct, neu_pct = _score_sentiment(texts)
        fake_hype, bot_activity = _fake_hype_and_bot_scores(texts)

        # Virality: engagement zichligi (post boshiga), 0..1 ga siqilgan
        virality = min(1.0, engagement / max(1, mention_count) / 200.0)
        # Trend: mentions soni yetarli bo'lsa signal beradi
        trend = min(1.0, mention_count / 50.0)
        confidence = min(
            1.0,
            mention_count / max(1, settings.SOCIAL_MIN_MENTIONS_FOR_SIGNAL) / 5.0,
        )

        # Yakuniy 0..1 ball: ijobiy sentiment + virality + trend, salbiy
        # sentiment/fake-hype/bot-activity uni pasaytiradi.
        raw_score = (
            0.35 * pos_pct
            + 0.20 * virality
            + 0.15 * trend
            + 0.10 * min(1.0, verified_mentions / 3.0)
            + 0.10 * min(1.0, influencer_mentions / 2.0)
            - 0.35 * neg_pct
            - 0.25 * fake_hype
            - 0.15 * bot_activity
        )
        social_score = max(0.0, min(1.0, 0.5 + raw_score))

        if mention_count < settings.SOCIAL_MIN_MENTIONS_FOR_SIGNAL:
            # Yetarli ma'lumot yo'q — neytralga yaqinlashtiramiz, lekin
            # butunlay bekor qilmaymiz (ozgina signal saqlanadi)
            social_score = 0.5 + (social_score - 0.5) * 0.3
            confidence *= 0.3

        metrics = SocialMetrics(
            mention_count=mention_count,
            engagement=engagement,
            like_count=like,
            reply_count=reply,
            repost_count=repost,
            verified_mentions=verified_mentions,
            influencer_mentions=influencer_mentions,
            sentiment_positive_pct=pos_pct,
            sentiment_negative_pct=neg_pct,
            sentiment_neutral_pct=neu_pct,
            trend_score=trend,
            virality_score=virality,
            fake_hype_score=fake_hype,
            bot_activity_score=bot_activity,
            social_confidence=confidence,
            social_score=social_score,
        )
        self._cache[token_address] = (time.time(), metrics)

        if social_score_repo is not None:
            try:
                await social_score_repo.add(
                    token_address=token_address,
                    mention_count=mention_count,
                    engagement=engagement,
                    like_count=like,
                    reply_count=reply,
                    repost_count=repost,
                    verified_mentions=verified_mentions,
                    influencer_mentions=influencer_mentions,
                    sentiment_positive_pct=pos_pct,
                    sentiment_negative_pct=neg_pct,
                    sentiment_neutral_pct=neu_pct,
                    trend_score=trend,
                    virality_score=virality,
                    fake_hype_score=fake_hype,
                    bot_activity_score=bot_activity,
                    social_confidence=confidence,
                    social_score=social_score,
                    raw={"mention_count": mention_count},
                )
            except Exception as e:
                logger.debug(f"Social score DB'ga yozilmadi: {e}")

        return metrics

    async def get_social_score(self, token_address: str, symbol: str) -> float:
        """filters/pipeline.py chaqiradigan qisqa metod — faqat 0..1 ball."""
        try:
            metrics = await self.analyze(token_address, symbol)
            return metrics.social_score
        except Exception as e:
            logger.warning(f"Social Intelligence kutilmagan xato (neytral ball beriladi): {e}")
            return 0.5
