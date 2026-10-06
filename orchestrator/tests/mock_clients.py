"""
Deterministic mock clients for the unit test suite ONLY.

Lives under tests/: the application never imports it, so live runs cannot fall back to it.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

from orchestrator.agents.market_research.discovery.search import TavilySearchResult
from orchestrator.schemas.research import (
    CompetitorProfile,
    DynamicParameterTaxonomy,
    MarketPositioningGap,
    SWOTAnalysis,
    SWOTReportDelta,
)

def create_standalone_mock_clients():
    """Generates mock tools and LLM for standalone deterministic CLI runs."""
    mock_search = [
        TavilySearchResult(
            vector="alternative_discovery",
            title="Logitech Lift Vertical Ergonomic Mouse",
            url="https://www.logitech.com/en-us/products/mice/lift-vertical-ergonomic-mouse.html",
            snippet="Best for small to medium hands. 57-degree angle promotes natural posture.",
            score=0.92,
        ),
        TavilySearchResult(
            vector="alternative_discovery",
            title="Logitech MX Master 3S Performance Wireless Mouse",
            url="https://www.logitech.com/en-us/products/mice/mx-master-3s.html",
            snippet="Quiet clicks, 8000 DPI track-on-glass sensor, electromagnetic MagSpeed scroll wheel.",
            score=0.88,
        ),
        TavilySearchResult(
            vector="pricing_scrape",
            title="Logitech Lift Pricing and Tech Specs",
            url="https://www.logitech.com/en-us/products/mice/lift-vertical-ergonomic-mouse.html#pricing",
            snippet="MSRP $69.99 USD. Standard commercial discount available for bulk orders.",
            score=0.85,
        ),
        TavilySearchResult(
            vector="pricing_scrape",
            title="Logitech MX Master 3S Pricing",
            url="https://www.logitech.com/en-us/products/mice/mx-master-3s.html#specs",
            snippet="MSRP $99.99 USD with 1-year limited hardware warranty.",
            score=0.84,
        ),
        TavilySearchResult(
            vector="gripe_mining",
            title="Reddit r/MouseReview: Lift vs MX Master 3S",
            url="https://www.reddit.com/r/MouseReview/comments/lift_ergonomics_complaints/",
            snippet="Logitech Lift lacks mechanical switches and feels mushy. MX Master 3S is too heavy for RSI sufferers.",
            score=0.79,
        ),
        TavilySearchResult(
            vector="messaging_claims",
            title="Logitech Ergo Series - Posture and Productivity",
            url="https://www.logitech.com/en-us/ergo.html",
            snippet="Feel better, do better. Certified by United States Ergonomics.",
            score=0.75,
        ),
        TavilySearchResult(
            vector="ad_intelligence",
            title="Logitech Lift Ad: Rest Easy at Your Desk",
            url="https://www.facebook.com/ads/library/?id=logi_lift_01",
            snippet="Say goodbye to wrist pain. The 57-degree vertical posture designed for all-day comfort.",
            score=0.88,
        ),
    ]

    mock_taxonomy = DynamicParameterTaxonomy(
        critical_jtbd_drivers=[
            "posture_angle",
            "switch_mechanism",
            "pricing_tier",
            "hand_size_ergonomics",
            "connectivity_ecosystem",
        ],
        minor_attributes=[
            "weight_grams",
            "sensor_dpi",
            "scroll_wheel_mechanism",
            "battery_life_days",
            "click_acoustics_db",
            "os_compatibility",
            "thumb_rest_angle",
            "warranty_period",
        ],
    )

    mock_report = SWOTReportDelta(
        competitors=[
            CompetitorProfile(
                brand_name="Logitech",
                product_name="Lift Vertical Ergonomic Mouse",
                pricing_model="one-time $69.99 USD",
                core_claims=["57-degree natural vertical posture", "whisper-quiet clicks"],
                weaknesses_mined=["membrane switch feel is mushy", "too small for large hands"],
                dynamic_attributes={
                    "posture_angle": "57 degrees vertical",
                    "switch_mechanism": "Silent membrane switches",
                    "weight_grams": "125g",
                    "sensor_dpi": "4000 DPI",
                    "hand_size_ergonomics": "Small to Medium only",
                },
                ad_hooks=[
                    'Campaign Hook: "Say goodbye to wrist pain with Lift"',
                    'Ad Creative: "Ergonomist approved 57-degree natural angle"',
                ],
                factual_evidence=[
                    'MSRP $69.99 USD. Standard commercial discount available for bulk orders.',
                    'Best for small to medium hands. 57-degree angle promotes natural posture.',
                    'Reddit r/MouseReview: "Logitech Lift lacks mechanical switches and feels mushy."',
                ],
                sources=["https://www.logitech.com/en-us/products/mice/lift-vertical-ergonomic-mouse.html"],
            ),
            CompetitorProfile(
                brand_name="Logitech",
                product_name="MX Master 3S",
                pricing_model="one-time $99.99 USD",
                core_claims=["8000 DPI track-on-glass", "MagSpeed electromagnetic scroll"],
                weaknesses_mined=["heavy weight (141g) exacerbates wrist strain", "not a pure vertical posture"],
                dynamic_attributes={
                    "posture_angle": "Semi-ergonomic (not vertical)",
                    "switch_mechanism": "Quiet click switches",
                    "weight_grams": "141g (Heavy)",
                    "sensor_dpi": "8000 DPI track-on-glass",
                    "hand_size_ergonomics": "Medium to Large",
                },
                ad_hooks=[
                    'Campaign Hook: "Master your flow with 8K DPI precision"',
                    'Ad Creative: "Electromagnetic MagSpeed scrolling for developers"',
                ],
                factual_evidence=[
                    'MSRP $99.99 USD with 1-year limited hardware warranty.',
                    'Quiet clicks, 8000 DPI track-on-glass sensor, electromagnetic MagSpeed scroll wheel.',
                    'Reddit r/MouseReview: "MX Master 3S is too heavy for RSI sufferers."',
                ],
                sources=["https://www.logitech.com/en-us/products/mice/mx-master-3s.html"],
            ),
        ],
        swot=SWOTAnalysis(
            strengths=[
                "Patented 57-degree neutral wrist posture",
                "Tactile mechanical switches absent in competitor ergonomic models",
            ],
            weaknesses=[
                "Higher price tier ($129.00 vs $69.99 Lift)",
                "New market entrant with unproven enterprise IT fleet reliability",
            ],
            opportunities=[
                "Target software engineering teams demanding mechanical tactile feedback with RSI prevention",
                "Bundle with ergonomic enterprise wellness procurement budgets",
            ],
            threats=[
                "Established enterprise vendor relationships dominated by Logitech",
                "Price sensitivity in bulk hardware procurement cycles",
            ],
        ),
        positioning_gap=MarketPositioningGap(
            quadrant="Tactile-Performance-Ergonomic",
            hook_angle="The only 57° vertical ergonomic mouse engineered with genuine mechanical switches for all-day coders.",
        ),
        attribute_density=0.85,
        dqs_score=0.88,
        assumptions_tagged=False,
        source_urls=[
            "https://www.logitech.com/en-us/products/mice/lift-vertical-ergonomic-mouse.html",
            "https://www.logitech.com/en-us/products/mice/mx-master-3s.html",
            "https://www.reddit.com/r/MouseReview/comments/lift_ergonomics_complaints/",
            "https://www.logitech.com/en-us/ergo.html",
        ],
        dynamic_taxonomy=mock_taxonomy,
    )

    tavily_client = AsyncMock()
    tavily_client.search = AsyncMock(
        return_value={
            "results": [
                {
                    "title": r.title,
                    "url": r.url,
                    "content": r.snippet,
                    "score": r.score,
                }
                for r in mock_search
            ]
        }
    )

    crawl_client = MagicMock()
    crawl_client.configured = True
    crawl_client.can_render_js = False
    crawl_client.fetch = AsyncMock(
        return_value={
            "url": "https://www.logitech.com/en-us/products/mice/lift-vertical-ergonomic-mouse.html",
            "status": 200,
            "body": (
                "# Logitech Lift Vertical Ergonomic Mouse\n\n"
                "Price: $69.99 USD. The 57-degree vertical angle lifts your wrist into a natural handshake position.\n"
                "Silent clicks, 4000 DPI sensor, Bluetooth and Logi Bolt receiver support.\n"
            )
        }
    )

    llm = AsyncMock()
    llm.ainvoke = AsyncMock(return_value=mock_report)

    def _structured(schema, **kwargs):
        wrapper = MagicMock()
        output = mock_taxonomy if schema is DynamicParameterTaxonomy else mock_report
        wrapper.ainvoke = AsyncMock(return_value=output)
        return wrapper

    llm.with_structured_output = MagicMock(side_effect=_structured)

    return tavily_client, crawl_client, llm
