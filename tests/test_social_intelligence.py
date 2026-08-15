import pytest

from social_intelligence.analyzer import SocialAnalyzer, _score_sentiment, _fake_hype_and_bot_scores
from social_intelligence.client import XApiClient


@pytest.mark.asyncio
async def test_disabled_returns_neutral(monkeypatch):
    """SOCIAL_INTELLIGENCE_ENABLED=false bo'lsa, hech qanday tarmoq
    so'rovisiz neytral ball qaytishi kerak."""
    from config.settings import settings

    monkeypatch.setattr(settings, "SOCIAL_INTELLIGENCE_ENABLED", False, raising=False)
    analyzer = SocialAnalyzer(client=XApiClient(bearer_token=None))
    score = await analyzer.get_social_score("TokenAddr111", "TEST")
    assert score == 0.5


@pytest.mark.asyncio
async def test_no_bearer_token_returns_neutral(monkeypatch):
    from config.settings import settings

    monkeypatch.setattr(settings, "SOCIAL_INTELLIGENCE_ENABLED", True, raising=False)
    analyzer = SocialAnalyzer(client=XApiClient(bearer_token=None))
    score = await analyzer.get_social_score("TokenAddr111", "TEST")
    assert score == 0.5


def test_sentiment_heuristic_positive():
    pos_pct, neg_pct, neu_pct = _score_sentiment(["this coin is going to moon 🚀", "bullish af, lfg"])
    assert pos_pct > neg_pct


def test_sentiment_heuristic_negative():
    pos_pct, neg_pct, neu_pct = _score_sentiment(["looks like a rugpull, avoid this scam", "dumped hard, dead"])
    assert neg_pct > pos_pct


def test_fake_hype_detects_duplicate_spam():
    spam = ["buy now to the moon!!"] * 8 + ["organic comment here"]
    fake_hype, bot_activity = _fake_hype_and_bot_scores(spam)
    assert fake_hype > 0.5


def test_fake_hype_low_for_organic_variety():
    organic = [
        "just found this token, liquidity looks decent",
        "holder count growing steadily",
        "not sure about this one yet",
        "checked the contract, looks clean",
    ]
    fake_hype, bot_activity = _fake_hype_and_bot_scores(organic)
    assert fake_hype < 0.3
