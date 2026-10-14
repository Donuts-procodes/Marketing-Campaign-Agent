"""
Comparative Campaign Strategy Options Generator.

Synthesizes three tailored, mathematically scaled marketing campaign options
incorporating user budget, mined competitor intelligence, advantages, disadvantages,
constraints, opportunities, static promotion channels, promotion means, and quantified predictions.
"""

from __future__ import annotations

from typing import Any
from orchestrator.agents.campaign_strategy.money import currency_of, fmt_money
from orchestrator.agents.campaign_strategy.promotions import (
    get_option_promotions,
    get_static_promotions,
)
from orchestrator.schemas.strategy import (
    CampaignStrategyOption,
    ChannelAllocation,
    CompetitorCampaignIntel,
    StrategyPrediction,
)


def generate_campaign_options(
    merchant_context: dict[str, Any],
    competitor_intel: list[CompetitorCampaignIntel],
    user_budget: float,
    campaign_days: int | None = None,
    sub_goals: list[str] | None = None,
) -> list[CampaignStrategyOption]:
    """
    Generates 3 tailored campaign strategy options scaled to the user's budget,
    duration, campaign type, and core goal, with static, battle-tested channels,
    promotion means, and channel tactics.
    """
    if not user_budget or user_budget <= 0:
        user_budget = 5000.0

    product_name = str(merchant_context.get("product_name") or "Our Solution").strip()
    category = str(merchant_context.get("category") or "Technology Solutions").strip()
    business_model = str(merchant_context.get("business_model") or "").strip()
    campaign_type = str(merchant_context.get("campaign_type") or "").strip()
    days = int(campaign_days or merchant_context.get("campaign_days") or 90)
    ctype = (campaign_type or "").lower()
    value_prop = str(merchant_context.get("primary_value_prop") or "differentiated performance").strip()
    goal = str(merchant_context.get("goal") or "rapid market acquisition").strip()

    ccy = currency_of(merchant_context)

    def m(share: float) -> str:
        return fmt_money(user_budget * share, ccy)

    top_competitor_name = competitor_intel[0].competitor_name if competitor_intel else "incumbent rivals"
    top_blindspot = (
        competitor_intel[0].blindspots[0]
        if competitor_intel and competitor_intel[0].blindspots
        else "Opaque pricing and high onboarding friction"
    )

    static_promos = get_static_promotions(business_model, campaign_type, category)
    tactics_map = static_promos.get("tactics_by_channel", {})

    # ──────────────────────────────────────────────────────────────────────────
    # OPTION A: Aggressive Incumbent Disrupter (Wedge Displacement)
    # ──────────────────────────────────────────────────────────────────────────
    opt_a_channels, opt_a_means = get_option_promotions("opt_disrupter", top_competitor_name, category)
    opt_a_channel_matrix = [
        ChannelAllocation(
            channel="linkedin",
            budget_percentage=40,
            recommended_spend_usd=round(user_budget * 0.40, 2),
            rationale=f"Target decision-makers actively evaluating or dissatisfied with {top_competitor_name}.",
            payee_platform="LinkedIn Ads (Microsoft Advertising)",
            purchased_inventory="Sponsored Document & InMail impressions delivered to verified CTO/VP decision-makers",
            spend_type="ad_spend",
            promotion_tactics=tactics_map.get("linkedin", [
                "Sponsored document carousel teardowns comparing old vs modern architecture",
                "Executive thought leadership posts citing industry benchmark data",
            ]),
        ),
        ChannelAllocation(
            channel="email",
            budget_percentage=25,
            recommended_spend_usd=round(user_budget * 0.25, 2),
            rationale="Cold account-based outreach offering seamless migration teardowns and guaranteed velocity.",
            payee_platform="Apollo.io / Clay & Secondary Domains (Instantly/Smartlead)",
            purchased_inventory="Verified B2B contact records, secondary sending domains, and mailbox warmup infrastructure",
            spend_type="data_tooling",
            promotion_tactics=tactics_map.get("email", [
                "Hyper-personalized 4-step cold outreach to verified switch candidate accounts",
                "Interactive case study teardowns demonstrating 3x velocity improvement",
            ]),
        ),
        ChannelAllocation(
            channel="retarget",
            budget_percentage=20,
            recommended_spend_usd=round(user_budget * 0.20, 2),
            rationale="Multi-touch retargeting highlighting competitor comparison matrix and switch incentives.",
            payee_platform="Meta Ads & Google Display Network",
            purchased_inventory="Dynamic retargeting ad impressions shown to comparison landing page drop-offs",
            spend_type="ad_spend",
            promotion_tactics=tactics_map.get("retarget", [
                "Dynamic social proof video testimonials targeted at pricing page drop-offs",
                "Feature-gap checklist ad creatives highlighting what rivals lack",
            ]),
        ),
        ChannelAllocation(
            channel="search",
            budget_percentage=15,
            recommended_spend_usd=round(user_budget * 0.15, 2),
            rationale=f"High-intent conquest keywords ('{top_competitor_name} alternative', 'switch from {top_competitor_name}').",
            payee_platform="Google Ads (Alphabet)",
            purchased_inventory="Pay-per-click (PPC) keyword auction bids on competitor brand and alternative search queries",
            spend_type="ad_spend",
            promotion_tactics=tactics_map.get("search", [
                "Conquest bidding on rival brand keywords ('rival alternative', 'switch from rival')",
                "High-intent solution problem terms with dedicated comparison landing pages",
            ]),
        ),
    ]

    # ──────────────────────────────────────────────────────────────────────────
    # OPTION B Channel Matrix
    # ──────────────────────────────────────────────────────────────────────────
    opt_b_channels, opt_b_means = get_option_promotions("opt_search_harvester", top_competitor_name, category)
    opt_b_channel_matrix = [
        ChannelAllocation(
            channel="search",
            budget_percentage=45,
            recommended_spend_usd=round(user_budget * 0.45, 2),
            rationale="Captures buyers in active procurement phase searching for solution categories and reviews.",
            payee_platform="Google Ads (Alphabet)",
            purchased_inventory="High-intent search ad clicks for category problem and competitor review searches",
            spend_type="ad_spend",
            promotion_tactics=tactics_map.get("search", [
                "Conquest bidding on rival brand keywords",
                "High-intent category solution terms with dedicated landing pages",
            ]),
        ),
        ChannelAllocation(
            channel="retarget",
            budget_percentage=30,
            recommended_spend_usd=round(user_budget * 0.30, 2),
            rationale="High-frequency retargeting across Google Display and Meta to prevent funnel leakage.",
            payee_platform="Meta Ads & Google Display Network",
            purchased_inventory="Multi-touch retargeting banner and video ad impressions for website visitors",
            spend_type="ad_spend",
            promotion_tactics=tactics_map.get("retarget", [
                "Dynamic social proof video testimonials targeted at pricing drop-offs",
                "Feature comparison checklist ads",
            ]),
        ),
        ChannelAllocation(
            channel="email",
            budget_percentage=25,
            recommended_spend_usd=round(user_budget * 0.25, 2),
            rationale="Automated 5-part comparative email sequence converting trial signups and demo downloads.",
            payee_platform="Marketing Automation (Klaviyo / Customer.io / ConvertKit)",
            purchased_inventory="Email dispatch bandwidth, automated lead nurturing drip workflows, and engagement analytics",
            spend_type="data_tooling",
            promotion_tactics=tactics_map.get("email", [
                "Automated comparative email sequence",
                "Interactive case study teardowns demonstrating ROI",
            ]),
        ),
    ]

    # ──────────────────────────────────────────────────────────────────────────
    # OPTION C Channel Matrix
    # ──────────────────────────────────────────────────────────────────────────
    opt_c_channels, opt_c_means = get_option_promotions("opt_abm_authority", top_competitor_name, category)
    opt_c_channel_matrix = [
        ChannelAllocation(
            channel="content",
            budget_percentage=35,
            recommended_spend_usd=round(user_budget * 0.35, 2),
            rationale="Deep technical teardowns, category benchmarks, and authoritative case study assets.",
            payee_platform="Technical Research & Content Tooling (Webflow/Vercel/Design)",
            purchased_inventory="Interactive calculator software, ungated benchmark PDF production, and case study teardowns",
            spend_type="asset_production",
            promotion_tactics=tactics_map.get("content", [
                "Deep-dive technical architectural blueprints and migration frameworks",
                "Cost comparison guides: Legacy Retainer vs. Modern Dedicated Sprint Teams",
            ]),
        ),
        ChannelAllocation(
            channel="linkedin",
            budget_percentage=35,
            recommended_spend_usd=round(user_budget * 0.35, 2),
            rationale="Executive persona thought leadership and sponsored document carousel ads.",
            payee_platform="LinkedIn Ads (Microsoft Advertising)",
            purchased_inventory="Sponsored Document carousel ads and executive thought leadership promotions targeting C-suite",
            spend_type="ad_spend",
            promotion_tactics=tactics_map.get("linkedin", [
                "Partner-level breakdown of successful enterprise digital transformations",
                "Direct messaging to CTOs and VP Engineers with tailored teardowns",
            ]),
        ),
        ChannelAllocation(
            channel="email",
            budget_percentage=30,
            recommended_spend_usd=round(user_budget * 0.30, 2),
            rationale="High-touch personal outreach from founder/executive to hand-curated account list.",
            payee_platform="Apollo.io / Clay B2B Intelligence & Dedicated Sending Mailboxes",
            purchased_inventory="Verified enterprise company lists, contact data enrichment credits, and deliverability infrastructure",
            spend_type="data_tooling",
            promotion_tactics=tactics_map.get("email", [
                "Multi-touch account-based outreach offering targeted technology audits",
                "Quarterly industry benchmarking trends report sent to key decision-makers",
            ]),
        ),
    ]

    # Dynamic titles, themes, and taglines based on campaign archetype
    if "launch" in ctype:
        title_a = "Option A: Velocity Launch & Early Adopter Wave"
        theme_a = "Early Adopter Activation & Launch Momentum"
        tagline_a = f"Ignite rapid category adoption for {product_name} centered on {value_prop}."
        title_b = "Option B: High-Intent Search & Consideration Harvester"
        theme_b = "Search & Consideration Ingress"
        tagline_b = f"Capture active solution evaluators searching for solutions like {product_name}."
        title_c = "Option C: Community, Influence & Category Authority"
        theme_c = "High-Authority Launch Wedge"
        tagline_c = f"Establish {product_name} as the undisputed innovation leader in {category}."
    elif "ecommerce" in ctype or "d2c" in ctype or "sales" in ctype:
        title_a = "Option A: Conversion Accelerator & Flash Acquisition"
        theme_a = "Direct-Response Scaling & ROAS Maximization"
        tagline_a = f"Drive immediate revenue velocity for {product_name} through high-converting offers."
        title_b = "Option B: Shopping, Search & Catalog Harvester"
        theme_b = "High-Intent In-Market Capture"
        tagline_b = f"Capture active shoppers searching for {category} solutions."
        title_c = "Option C: VIP Retention, Community & High-LTV Scaling"
        theme_c = "Customer Lifetime Value Expansion"
        tagline_c = f"Build enduring customer loyalty, subscription models, and repeat purchase momentum."
    elif "brand" in ctype or "awareness" in ctype:
        title_a = "Option A: High-Reach Storytelling & Category Spotlight"
        theme_a = "Mass Category Mindshare"
        tagline_a = f"Position {product_name} as the definitive standard in {category}."
        title_b = "Option B: Educational Problem-Aware Search Hub"
        theme_b = "Inbound Category Education"
        tagline_b = f"Educate prospects on category challenges and position {product_name}."
        title_c = "Option C: Executive Authority & PR Thought Leadership"
        theme_c = "High-Status Industry Dominance"
        tagline_c = f"Dominate industry conversation with breakthrough research and executive insight."
    else:
        title_a = "Option A: Aggressive Incumbent Disrupter"
        theme_a = "Wedge Displacement & Migration Velocity"
        tagline_a = f"Target and displace dissatisfied {top_competitor_name} accounts with guaranteed migration speed."
        title_b = "Option B: High-Intent Search & Comparison Harvester"
        theme_b = "Organic & Paid Demand Capture"
        tagline_b = "Maximize immediate inbound conversions by capturing buyers actively searching for alternatives."
        title_c = "Option C: Account-Based Trust & Thought Leadership Wedge"
        theme_c = "High-Contract Enterprise Authority"
        tagline_c = "Position as the premium tier category authority for high-ticket enterprise contracts."

    # Extract competitor spend, platform costs, flagship clients, and consumer feedback
    top_comp = competitor_intel[0] if competitor_intel else None
    spend_est = getattr(top_comp, "estimated_monthly_ad_spend", None)
    platform_benchmarks = getattr(top_comp, "platform_cost_benchmarks", {}) or {}
    flagship_logos = getattr(top_comp, "competitor_flagship_clients", []) or []
    consumer_feedback = getattr(top_comp, "competitor_consumer_feedback", []) or []

    # Dynamic sub-goal advantages
    sub_goal_bullets = [f"Directly advances sub-goal: {sg}" for sg in (sub_goals or []) if sg.strip()][:3]


    opt_a_advantages = [
        f"Directly attacks {top_competitor_name}'s primary vulnerability: {top_blindspot}.",
        f"Directly aligns media spend to achieve core milestone: {goal}.",
        f"Accelerates decision velocity by spotlighting {value_prop}.",
    ]
    if spend_est:
        opt_a_advantages.append(f"Counters rival ad spend ({spend_est}) by targeting switchers instead of head-to-head auctions.")
    if flagship_logos:
        opt_a_advantages.append(f"Targets accounts evaluating {top_competitor_name}'s marquee client tier ({', '.join(flagship_logos[:2])}) with zero-downtime migration hooks.")
    if consumer_feedback:
        opt_a_advantages.append(f"Capitalizes on switcher dissatisfaction drivers: {', '.join(consumer_feedback[:2])}.")
    opt_a_advantages.extend(sub_goal_bullets)

    platform_constraint = (
        f"Optimized for media spend benchmarks ({', '.join([f'{k}: {v}' for k, v in list(platform_benchmarks.items())[:2]])})."
        if platform_benchmarks
        else f"Calibrated for at most {m(0.60)} of paid media over {days} days; scale only after tests prove intent."
    )

    opt_a = CampaignStrategyOption(
        option_id="opt_disrupter",
        title=title_a,
        theme=theme_a,
        tagline=tagline_a,
        recommended=True,
        budget_allocation_summary=f"{m(0.40)} Primary Channel (40%) • {m(0.25)} Direct Outbound (25%) • {m(0.20)} Retargeting (20%) • {m(0.15)} Search (15%)",
        channel_matrix=opt_a_channel_matrix,
        suggested_channels=opt_a_channels,
        promotion_means=opt_a_means,
        advantages=opt_a_advantages,
        disadvantages=[
            "Higher initial cost per click on competitive keyword auctions and sponsored feeds.",
            "Requires responsive handling to turn high-intent interest into completed conversions.",
        ],
        constraints=[
            platform_constraint,
            "Requires clear value proposition proof points and verified landing page assets.",
        ],
        opportunities=[
            f"Captures market share during key decision cycles by positioning against {top_competitor_name}.",
            f"Establishes {product_name} as the modern, high-velocity choice in {category}.",
        ],
        prediction=StrategyPrediction(risk_level="Medium"),
    )

    opt_b = CampaignStrategyOption(
        option_id="opt_search_harvester",
        title=title_b,
        theme=theme_b,
        tagline=tagline_b,
        recommended=False,
        budget_allocation_summary=f"{m(0.45)} Google Search (45%) • {m(0.30)} Retargeting (30%) • {m(0.25)} Nurture Sequences (25%)",
        channel_matrix=opt_b_channel_matrix,
        suggested_channels=opt_b_channels,
        promotion_means=opt_b_means,
        advantages=[
            "Immediate inbound conversion momentum with the shortest time-to-first-lead.",
            "Highly measurable conversion attribution with lower CPC than pure outbound ABM.",
            f"Captures buyers already convinced of the problem and seeking {value_prop}.",
            *sub_goal_bullets,
        ],
        disadvantages=[
            "Search volume for niche queries can be capped, limiting ultimate monthly scale.",
            "Higher competition on broad keywords can drive up bid prices if negative keywords aren't strictly tuned.",
        ],
        constraints=[
            "Requires dedicated, high-converting side-by-side landing pages for ad traffic.",
            f"Daily ad spend must be monitored across the {days}-day flight to avoid budget exhaustion.",
        ],
        opportunities=[
            "Capitalize on competitor brand search volume without paying for legacy brand awareness.",
            "Convert high-intent comparison shoppers looking for transparent pricing.",
        ],
        prediction=StrategyPrediction(risk_level="Low"),
    )

    opt_c = CampaignStrategyOption(
        option_id="opt_abm_authority",
        title=title_c,
        theme=theme_c,
        tagline=tagline_c,
        recommended=False,
        budget_allocation_summary=f"{m(0.35)} Content & Benchmarks (35%) • {m(0.35)} Executive Presence (35%) • {m(0.30)} Account Outbound (30%)",
        channel_matrix=opt_c_channel_matrix,
        suggested_channels=opt_c_channels,
        promotion_means=opt_c_means,
        advantages=[
            "Highest Average Contract Value (ACV) and strongest customer lifetime value (LTV).",
            "Builds long-term organic defensibility through compounding thought leadership assets.",
            "Minimal reliance on volatile ad networks or rising bidding auction wars.",
            *sub_goal_bullets,
        ],
        disadvantages=[
            "Longer lead gestation period before first deals close (requires patience).",
            "Requires high-quality technical proof points and executive involvement in early pitches.",
        ],
        constraints=[
            "Requires founder or tech lead time for case studies and executive webinars.",
            f"Minimum {max(14, round(days * 0.6))}-{days} days runway needed before full pipeline conversion reflects.",
        ],
        opportunities=[
            f"Preempt competitors who rely solely on generic sales reps rather than engineering depth.",
            "Win premium tier RFP opportunities that disqualifies cheap freelancers or low-end providers.",
        ],
        prediction=StrategyPrediction(risk_level="Medium"),
    )

    return [opt_a, opt_b, opt_c]
