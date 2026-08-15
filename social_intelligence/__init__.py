"""Social Intelligence (X.com, rasmiy API) — section 5.

Faqat ``GET /2/tweets/search/recent`` (rasmiy X API v2, Bearer Token)
ishlatiladi. Scraping yo'q. ``SOCIAL_INTELLIGENCE_ENABLED=false`` yoki
``X_API_BEARER_TOKEN`` bo'sh bo'lsa, modul avtomatik neytral ball
qaytaradi va botning qolgan qismiga hech qanday ta'sir qilmaydi.
"""
from social_intelligence.analyzer import SocialAnalyzer, SocialMetrics
from social_intelligence.client import XApiClient

__all__ = ["SocialAnalyzer", "SocialMetrics", "XApiClient"]
