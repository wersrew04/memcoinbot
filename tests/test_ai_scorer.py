"""Unit tests for AI Scorer."""
import pytest
from ai_engine.scorer import AIScorer, AIRecommendation


def test_score_basic(monkeypatch):
    from config.settings import settings
    monkeypatch.setattr(settings, "AI_ENABLED", True)
    monkeypatch.setattr(settings, "AI_MIN_SCORE", 55.0)
    monkeypatch.setattr(settings, "AI_BUY_THRESHOLD", 65.0)
    monkeypatch.setattr(settings, "AI_STRONG_BUY_THRESHOLD", 80.0)
    scorer = AIScorer()
    data = {
        "liquidity_usd": 200_000,
        "volume_24h": 300_000,
        "holder_count": 2000,
        "security": {"is_honeypot": False, "mint_authority": None, "freeze_authority": None},
        "volume_5m": 50_000,
        "volume_1h": 100_000,
    }
    result = scorer.score(data)
    assert 0 <= result.score <= 100
    assert result.recommendation in list(AIRecommendation)


def test_honeypot_low_score(monkeypatch):
    from config.settings import settings
    monkeypatch.setattr(settings, "AI_ENABLED", True)
    monkeypatch.setattr(settings, "AI_MIN_SCORE", 55.0)
    monkeypatch.setattr(settings, "AI_BUY_THRESHOLD", 65.0)
    monkeypatch.setattr(settings, "AI_STRONG_BUY_THRESHOLD", 80.0)
    scorer = AIScorer()
    data = {
        "liquidity_usd": 200_000,
        "volume_24h": 300_000,
        "holder_count": 2000,
        "security": {"is_honeypot": True},
    }
    result = scorer.score(data)
    assert result.score < 50
    assert result.recommendation == AIRecommendation.AVOID


def test_passes_threshold(monkeypatch):
    from config.settings import settings
    monkeypatch.setattr(settings, "AI_MIN_SCORE", 55.0)
    scorer = AIScorer()
    from ai_engine.scorer import AIScoreResult
    ok = AIScoreResult(score=70, recommendation=AIRecommendation.BUY)
    assert scorer.passes_threshold(ok)
    bad = AIScoreResult(score=30, recommendation=AIRecommendation.AVOID)
    assert not scorer.passes_threshold(bad)
