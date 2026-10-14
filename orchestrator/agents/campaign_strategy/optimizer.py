from __future__ import annotations

from typing import Any
from orchestrator.agents.campaign_strategy.promotions import get_static_promotions
from orchestrator.schemas.research import SWOTReportDelta
from orchestrator.schemas.strategy import (
    CampaignStrategyBrief,
    CampaignStrategyOption,
    ChannelAllocation,
    CompetitorCampaignIntel,
    PhaseMilestone,
    StrategicAngle,
    SubagentDeployment,
    TacticalOutreachBlueprint,
    TargetMetric,
)


def build_execution_calendar(
    campaign_days: int = 90,
    campaign_type: str = "general",
    core_goal: str = "",
    sub_goals: list[str] | None = None,
) -> list[PhaseMilestone]:
    """
    Loop 3: Builds the dynamically scaled phased execution roadmap and dependencies
    tailored to campaign days, campaign archetype, and merchant sub-goals.
    """
    days = max(campaign_days, 7)
    ctype = (campaign_type or "").lower()
    sub_goals_list = [g.strip() for g in (sub_goals or []) if g and g.strip()]

    # Dynamic phase timeframe windows
    if days <= 14:
        p1_time = "Days 1 - 3"
        p2_time = "Days 4 - 10"
        p3_time = f"Days 11 - {days}"
    elif days <= 45:
        p1_time = "Days 1 - 7"
        p2_time = "Days 8 - 21"
        p3_time = f"Days 22 - {days}"
    elif days <= 75:
        p1_time = "Weeks 1 - 2"
        p2_time = "Weeks 3 - 6"
        p3_time = f"Weeks 7 - {max(7, round(days / 7))}"
    else:
        p1_time = "Weeks 1 - 3"
        p2_time = "Weeks 4 - 8"
        p3_time = f"Weeks 9 - {max(9, round(days / 7))}"

    # Tailor focus and deliverables based on campaign archetype
    if "launch" in ctype:
        p1_name = "Phase 1: Pre-Launch Readiness & Audience Seeding"
        p1_focus = "Deploy teaser landing pages, seed core early-adopter communities, and verify tracking attribution."
        p1_delivs = [
            "High-converting launch landing page & waitlist funnel",
            "Early adopter email sequence drafted and QA-approved",
            "Pixel & conversion tracking pipelines verified",
        ]

        p2_name = "Phase 2: Public Launch Ingress & High-Intent Flight"
        p2_focus = f"Unleash core campaign to hit primary milestone: {core_goal or 'rapid customer acquisition'}."
        p2_delivs = [
            "Active multi-channel launch campaigns running with CPA guardrails",
            "Creative hook A/B delta testing and daily budget pacing",
            "Initial conversion cohort onboarding and feedback loops",
        ]

        p3_name = "Phase 3: Scale, Social Proof & Expansion"
        p3_focus = f"Amplify winning creative angles, deploy dynamic retargeting, and secure long-term conversion momentum over {days} days."
        p3_delivs = [
            "Dynamic retargeting flight active across multi-touch channels",
            f"Full {days}-day CPA, CAC, and conversion ROI performance audit",
            "Post-launch continuous optimization handoff",
        ]
    elif "ecommerce" in ctype or "d2c" in ctype or "sales" in ctype:
        p1_name = "Phase 1: Creative Teardown & Catalog Feed Sync"
        p1_focus = "Optimize product landing pages, audit shopping feeds, and deploy cart abandonment retargeting triggers."
        p1_delivs = [
            "High-converting promotional landing pages and bundle offers",
            "Automated abandoned cart & SMS/email flow activation",
            "Ad network attribution & server-side conversion API verified",
        ]

        p2_name = "Phase 2: High-ROAS Traffic Acquisition"
        p2_focus = f"Scale top-performing shopping, search, and social ad sets focused on {core_goal or 'driving profitable revenue'}."
        p2_delivs = [
            "High-intent search and social ads running with strict ROAS thresholds",
            "Weekly creative refreshes and visual hooks testing",
            "First cohort of repeat buyers and promotional purchasers secured",
        ]

        p3_name = "Phase 3: Retargeting Flight & Lifetime Value Expansion"
        p3_focus = f"Maximize repeat orders, scale VIP loyalty incentives, and lock in profit margins over {days} days."
        p3_delivs = [
            "High-frequency dynamic retargeting active for cart drop-offs",
            f"Full {days}-day blended ROAS and unit economics reconciliation",
            "Handoff to automated evergreen media rotation",
        ]
    elif "brand" in ctype or "awareness" in ctype:
        p1_name = "Phase 1: Brand Anchor & Narrative Positioning"
        p1_focus = "Establish authoritative category narrative, produce hero content assets, and set up audience brand-lift tracking."
        p1_delivs = [
            "Hero category narrative & interactive asset published",
            "Multi-platform video & carousel creative packs QA-approved",
            "Brand search query baselines and tracking benchmarks established",
        ]

        p2_name = "Phase 2: High-Reach Engagement Flight"
        p2_focus = f"Distribute high-impact story angles to maximize category mindshare around {core_goal or 'brand recognition'}."
        p2_delivs = [
            "High-reach social, PR, and community distribution active",
            "Weekly engagement velocity and earned media monitoring",
            "Audience pool enrichment across mid-funnel touchpoints",
        ]

        p3_name = "Phase 3: Mid-Funnel Retargeting & Brand Equity Capture"
        p3_focus = f"Convert high-engagement brand viewers into qualified pipeline and active subscribers over {days} days."
        p3_delivs = [
            "Mid-funnel retargeting capturing high-dwell brand visitors",
            f"Full {days}-day brand search volume & reach velocity audit",
            "Long-term category authority playbook finalized",
        ]
    else:
        # Default / Competitor Displacement / Lead Gen
        p1_name = "Phase 1: Foundation & Positioning Validation"
        p1_focus = "Establish verified category wedge messaging, deploy comparison teardowns, and configure tracking."
        p1_delivs = [
            "High-converting comparative landing page vs key rivals",
            "Email sequences (Angles 1 & 2) drafted and QA-approved",
            "Conversion tracking & attribution pipelines verified",
        ]

        p2_name = "Phase 2: Alpha Wedge Ingress & Pipeline Acceleration"
        p2_focus = f"Launch paid search and targeted outreach focused on achieving {core_goal or 'qualified customer acquisition'}."
        p2_delivs = [
            "Active search and targeted outreach running with strict CPA guardrails",
            "Weekly creative delta testing and ad hook optimization",
            "First cohort of qualified pipeline opportunities conducted",
        ]

        p3_name = "Phase 3: Scale & Retargeting Flight"
        p3_focus = f"Shift budget into winning strategic angles and scale retargeting over the {days}-day window."
        p3_delivs = [
            "Dynamic retargeting flight active across multi-touch channels",
            f"Full {days}-day CAC and pipeline ROI performance audit",
            "Handoff to automated continuous monitoring",
        ]

    # Incorporate user sub-goals directly into deliverables
    if sub_goals_list:
        for idx, sg in enumerate(sub_goals_list[:3]):
            if idx == 0:
                p1_delivs.append(f"Sub-goal milestone: Setup {sg}")
            elif idx == 1:
                p2_delivs.append(f"Sub-goal milestone: Validate {sg}")
            else:
                p3_delivs.append(f"Sub-goal milestone: Achieve {sg}")

    return [
        PhaseMilestone(
            phase_name=p1_name,
            weeks=p1_time,
            focus=p1_focus,
            deliverables=p1_delivs,
        ),
        PhaseMilestone(
            phase_name=p2_name,
            weeks=p2_time,
            focus=p2_focus,
            deliverables=p2_delivs,
        ),
        PhaseMilestone(
            phase_name=p3_name,
            weeks=p3_time,
            focus=p3_focus,
            deliverables=p3_delivs,
        ),
    ]


def build_subagents_roster(
    merchant_context: dict[str, Any],
    channel_matrix: list[ChannelAllocation],
) -> list[SubagentDeployment]:
    """
    Loop 3: Provisions the specialized autonomous subagents that execute the campaign,
    eliminating human agency retainers, copywriters, and media-buying overhead.
    """
    return [
        SubagentDeployment(
            agent_id="subagent_ad_creative",
            name="Ad Creative & Copywriting Subagent",
            role="Drafts high-converting headline hooks, sponsored LinkedIn carousels, and multi-variant landing page copy.",
            status="ready",
            target_channels=["LinkedIn", "Search", "Email"],
            deliverables=[
                "Multi-variant ad copy hooks",
                "Sponsored document carousel slides",
                "Comparative landing page copy",
            ],
            estimated_hours_saved="18 hrs/wk (Replaces Senior Copywriter)",
        ),
        SubagentDeployment(
            agent_id="subagent_search_conquest",
            name="Search Conquest & Keyword Bidder Subagent",
            role="Builds competitor alternative keyword clusters, negative match lists, and quality-score campaign structures.",
            status="ready",
            target_channels=["Google Search"],
            deliverables=[
                "Conquest keyword bid matrices",
                "Negative keyword exclusion lists",
                "High-intent sitelink extensions",
            ],
            estimated_hours_saved="12 hrs/wk (Replaces Google Ads Specialist)",
        ),
        SubagentDeployment(
            agent_id="subagent_outbound_enricher",
            name="B2B Outbound Enrichment & Inbox Subagent",
            role="Discovers verified decision-maker work emails, provisions secondary sending domains, and monitors inbox deliverability.",
            status="ready",
            target_channels=["Cold Outbound Email"],
            deliverables=[
                "Verified decision-maker contact records",
                "SPF/DKIM/DMARC secondary mailbox configs",
                "Automated inbox warmup monitors",
            ],
            estimated_hours_saved="25 hrs/wk (Replaces Outbound SDR)",
        ),
        SubagentDeployment(
            agent_id="subagent_retargeting_pixel",
            name="Retargeting & Pixel Orchestrator Subagent",
            role="Constructs comparison-drop-off custom audiences across Meta and Google Display to minimize funnel leakage.",
            status="ready",
            target_channels=["Retargeting (Meta & Display)"],
            deliverables=[
                "Drop-off visitor audience pixel rules",
                "Dynamic social proof testimonial schedules",
            ],
            estimated_hours_saved="10 hrs/wk (Replaces Media Buyer)",
        ),
        SubagentDeployment(
            agent_id="subagent_intel_miner",
            name="Competitive Intelligence & Offer Mining Subagent",
            role="Continuously monitors rival ad libraries, pricing shifts, and customer complaint vectors across web search and scrapers.",
            status="ready",
            target_channels=["Market Intelligence", "Search"],
            deliverables=[
                "Live rival ad hook extracts",
                "Pricing shift alerts",
                "Market displacement opportunity reports",
            ],
            estimated_hours_saved="15 hrs/wk (Replaces Market Research Analyst)",
        ),
        SubagentDeployment(
            agent_id="subagent_telemetry_rebalancer",
            name="Telemetry Cockpit & Budget Rebalancer Subagent",
            role="Monitors live CPC, CPA, and conversion velocity; autonomously pauses underperforming angles and scales winning variants.",
            status="ready",
            target_channels=["All Campaign Channels"],
            deliverables=[
                "Real-time pipeline ROI tracking",
                "Automated budget reallocation triggers",
                "Weekly performance delta audit",
            ],
            estimated_hours_saved="10 hrs/wk (Replaces Growth Director)",
        ),
    ]


def build_budget_assumptions(
    merchant_context: dict[str, Any],
    channel_matrix: list[ChannelAllocation],
    user_budget: float | None = None,
) -> list[str]:
    """
    Loop 3: Flags explicit budget assumptions, constraints, and safety guardrails.
    """
    from orchestrator.agents.campaign_strategy.money import currency_of, fmt_money

    total_spend = user_budget if user_budget is not None else sum(c.recommended_spend_usd or 0 for c in channel_matrix)
    ccy = currency_of(merchant_context)
    return [
        f"Campaign budget: {fmt_money(total_spend, ccy)} ({ccy}), covering media, creator fees, content assets and tools.",
        "Excludes employee salaries, inventory, manufacturing, order shipping and website build unless stated otherwise.",
        "Phase budgets are ceilings, not targets: spend moves to the next phase only when the previous phase's test shows buying intent.",
        "No return or acquisition-cost projection is made without the merchant's own sales data; the first test flight sets the baseline.",
    ]


def build_outreach_blueprint(
    merchant_context: dict[str, Any],
    channel_matrix: list[ChannelAllocation],
    user_budget: float | None = None,
    top_rival: str = "Legacy Competitors",
    campaign_days: int = 90,
) -> list[TacticalOutreachBlueprint]:
    """
    Loop 3: Generates an actionable 5W/1H outreach blueprint answering:
    - Who to reach out to (ICP titles, company profile, pain triggers)
    - Where to reach out (Platforms, networks, inboxes)
    - How to reach out (Sequences, hooks, offers, teardowns)
    - In what budget (Allocated USD spend, share %, target CPA)
    - For how long & cadence (Flight duration, touch intervals, frequency caps)
    - Assigned autonomous AI subagent
    """
    base_budget = user_budget if user_budget is not None and user_budget > 0 else 10000.0
    brand = (merchant_context.get("product_name") or "Our Solution").strip()
    category = (merchant_context.get("category") or "Technology").strip()
    value_prop = (merchant_context.get("primary_value_prop") or "industry-leading performance and transparent pricing").strip()
    target_audience = (merchant_context.get("target_audience") or "").strip()
    campaign_type = (merchant_context.get("campaign_type") or "").lower()
    days = max(campaign_days, 7)

    channel_budgets: dict[str, tuple[float, int]] = {}
    for ch in channel_matrix:
        spend = (
            ch.recommended_spend_usd
            if ch.recommended_spend_usd is not None
            else round(base_budget * (ch.budget_percentage / 100.0), 2)
        )
        channel_budgets[ch.channel] = (spend, ch.budget_percentage)

    blueprints: list[TacticalOutreachBlueprint] = []

    # Audience profile customization
    is_ecommerce = "ecommerce" in campaign_type or "d2c" in campaign_type or "sales" in campaign_type
    if target_audience:
        who_p1 = f"{target_audience} decision-makers evaluating alternatives to {top_rival}"
        who_p2 = f"Active evaluators from {target_audience} searching for '{top_rival} alternative' or '{category} solutions'"
        who_p3 = f"Target accounts within {target_audience} dissatisfied with {top_rival} support and pricing"
        who_p4 = f"High-intent website visitors from {target_audience} who viewed comparison pages but dropped off"
    elif is_ecommerce:
        who_p1 = f"Category enthusiasts and high-intent consumers looking for {value_prop}"
        who_p2 = f"Active shoppers searching for '{category}' or '{top_rival}' alternatives"
        who_p3 = f"High-value shopper segments and subscribers looking for promotional releases"
        who_p4 = f"Browsing visitors who viewed product pages or added to cart without checking out"
    else:
        who_p1 = f"Key decision-makers and technology leaders at growth firms evaluating {category} solutions"
        who_p2 = f"Active solution evaluators searching for '{top_rival} alternative', '{top_rival} pricing', or '{category} switcher migration'"
        who_p3 = f"Directors and Operational Leads dissatisfied with {top_rival} implementation delays and opaque support tiers"
        who_p4 = f"High-intent website visitors who viewed comparison pricing pages or initiated demo signups but dropped off"

    # 1. Primary Targeted Outreach Play (LinkedIn / Sponsored Ingress)
    li_spend, li_pct = channel_budgets.get("linkedin", (round(base_budget * 0.40, 2), 40))
    blueprints.append(
        TacticalOutreachBlueprint(
            playbook_id="play_linkedin_decision_makers",
            channel_name="LinkedIn Sponsored Updates & InMail" if not is_ecommerce else "Meta & Social Acquisition Play",
            who_target_profile=who_p1,
            where_platform="LinkedIn Ads Network (Matched Audiences & Sponsored InMail Ingress)" if not is_ecommerce else "Meta Ads (Instagram & Facebook Feeds / Stories)",
            how_mechanism=f"Sponsored Document Carousel comparing {brand} vs {top_rival} on {value_prop} + Free Feasibility Audit hook",
            budget_allocation_usd=li_spend,
            budget_share_pct=li_pct,
            duration_and_cadence=f"{days}-day campaign flight: 3–5 impressions/week frequency cap; creative angle refresh every 14 days",
            expected_cpa="Set from the first test flight's cost per result",
            assigned_subagent="Ad Creative & Copywriting Subagent (subagent_ad_creative)",
        )
    )

    # 2. High-Intent Search Conquesting Play
    search_spend, search_pct = channel_budgets.get("search", (round(base_budget * 0.15, 2), 15))
    blueprints.append(
        TacticalOutreachBlueprint(
            playbook_id="play_search_conquesting",
            channel_name="Google Ads High-Intent Search",
            who_target_profile=who_p2,
            where_platform="Google Search Engine Results Pages (High-Intent Phrase & Exact Match Auctions)",
            how_mechanism=f"Dedicated comparison landing page featuring side-by-side benchmark matrix, instant ROI calculator, and Switcher Onboarding Rebate for {brand}",
            budget_allocation_usd=search_spend,
            budget_share_pct=search_pct,
            duration_and_cadence=f"{days}-day continuous auction flight: Daily spend cap paced evenly with automated dayparting",
            expected_cpa="Set from the first test flight's cost per result",
            assigned_subagent="Search Conquest & Bidder Subagent (subagent_search_conquest)",
        )
    )

    # 3. Direct Outbound & Inbox Play
    email_spend, email_pct = channel_budgets.get("email", (round(base_budget * 0.25, 2), 25))
    blueprints.append(
        TacticalOutreachBlueprint(
            playbook_id="play_outbound_inbox_flight",
            channel_name="Cold Outbound Email & Secondary Domains" if not is_ecommerce else "Automated Lifecycle & SMS Flows",
            who_target_profile=who_p3,
            where_platform="Verified secondary inbox domains via Instantly / Apollo.io" if not is_ecommerce else "Automated Marketing Platform (Klaviyo / Customer.io)",
            how_mechanism=f"3-touch hyper-personalized sequence: Touch 1 ({top_rival} migration pain point), Touch 2 ({value_prop} proof point), Touch 3 (Direct offer for 14-day POC)",
            budget_allocation_usd=email_spend,
            budget_share_pct=email_pct,
            duration_and_cadence=f"{days}-day continuous flight: Multi-touch sequence paced across key decision intervals with warmup safeguards",
            expected_cpa="Set from the first test flight's cost per result",
            assigned_subagent="B2B Outbound Enrichment Subagent (subagent_outbound_enricher)",
        )
    )

    # 4. Multi-Touch Retargeting & Drop-Off Re-engagement Play
    retarget_spend, retarget_pct = channel_budgets.get("retarget", (round(base_budget * 0.20, 2), 20))
    blueprints.append(
        TacticalOutreachBlueprint(
            playbook_id="play_pixel_retargeting_flight",
            channel_name="Dynamic Retargeting (Meta & Google Display)",
            who_target_profile=who_p4,
            where_platform="Meta Custom Audiences (Instagram/Facebook feeds) & Google Display Network",
            how_mechanism=f"Sequential 3-stage social proof proof-points (Customer video testimonials -> {value_prop} guarantees -> Limited-time switch incentive)",
            budget_allocation_usd=retarget_spend,
            budget_share_pct=retarget_pct,
            duration_and_cadence=f"{days}-day flight: 0–7 day post-visit window for high-urgency hook; 8–30 day window for case study proof; 2 impressions/day max cap",
            expected_cpa="Set from the first test flight's cost per result",
            assigned_subagent="Retargeting & Pixel Orchestrator (subagent_retargeting_pixel)",
        )
    )

    return blueprints


def consolidate_strategy_brief(
    merchant_context: dict[str, Any],
    swot_report: SWOTReportDelta | None,
    target_metrics: list[TargetMetric],
    channel_matrix: list[ChannelAllocation],
    strategic_angles: list[StrategicAngle],
    competitor_intel: list[CompetitorCampaignIntel] | None = None,
    campaign_options: list[CampaignStrategyOption] | None = None,
    user_budget: float | None = None,
    selected_option_id: str | None = None,
    campaign_days: int | None = None,
    sub_goals: list[str] | None = None,
    campaign_type: str | None = None,
    core_goal: str | None = None,
) -> CampaignStrategyBrief:
    """
    Loop 3: Consolidates the complete execution-ready Campaign Strategy Brief,
    deeply tailored to the merchant's core idea, core goal, campaign duration, and archetype.
    """
    brand = (merchant_context.get("product_name") or "Our Solution").strip()
    category = (merchant_context.get("category") or "Technology").strip()
    top_competitors = swot_report.competitors if swot_report else []
    top_rival = (top_competitors[0].product_name or top_competitors[0].brand_name) if top_competitors else "incumbent solutions"

    days = int(campaign_days or merchant_context.get("campaign_days") or 90)
    resolved_sub_goals = list(sub_goals if sub_goals is not None else merchant_context.get("sub_goals") or [])
    ctype = str(campaign_type or merchant_context.get("campaign_type") or "general").lower().strip()
    cgoal = str(core_goal or merchant_context.get("goal") or "Accelerate high-converting customer acquisition").strip()
    core_idea = str(merchant_context.get("primary_value_prop") or "differentiated product capabilities, transparent unit economics, and rapid implementation").strip()

    if "launch" in ctype:
        executive_summary = (
            f"{days}-day product launch strategy engineered to propel {brand} into {category}. "
            f"Centered on {core_idea}, the campaign focuses on achieving {cgoal} by mobilizing "
            f"early-adopter demand, out-positioning {top_rival}, and establishing high-conviction conversion velocity."
        )
        primary_positioning_pillar = f"Launch {brand} in {category} powered by {core_idea} to achieve {cgoal}."
    elif "ecommerce" in ctype or "d2c" in ctype or "sales" in ctype:
        executive_summary = (
            f"{days}-day high-conversion growth campaign engineered for {brand} in {category}. "
            f"Leveraging {core_idea}, the strategy drives toward {cgoal} by deploying high-ROAS "
            f"acquisition channels, capturing high-intent shoppers, and out-converting {top_rival}."
        )
        primary_positioning_pillar = f"Accelerate profitable sales for {brand} via {core_idea}."
    elif "brand" in ctype or "awareness" in ctype:
        executive_summary = (
            f"{days}-day brand awareness and category leadership campaign for {brand} in {category}. "
            f"Spotlighting {core_idea}, the campaign is designed to fulfill {cgoal} by dominating "
            f"category mindshare, establishing narrative authority, and differentiating against {top_rival}."
        )
        primary_positioning_pillar = f"Establish {brand} as the benchmark in {category} through {core_idea}."
    else:
        executive_summary = (
            f"{days}-day performance strategy engineered to position {brand} as the category leader in {category}. "
            f"Anchored in {core_idea} and driven to achieve {cgoal}, the campaign targets "
            f"vulnerabilities in {top_rival} to accelerate deal velocity and maximize capital efficiency."
        )
        primary_positioning_pillar = f"Differentiate {brand} via {core_idea} to deliver {cgoal}."

    # Determine suggested_channels and promotion_means
    selected_opt = None
    if campaign_options:
        for opt in campaign_options:
            if opt.option_id == selected_option_id:
                selected_opt = opt
                break
        if not selected_opt and campaign_options:
            selected_opt = campaign_options[0]

    static_promos = get_static_promotions(
        business_model=str(merchant_context.get("business_model") or ""),
        campaign_type=ctype,
        category=category,
    )
    suggested_channels = (
        selected_opt.suggested_channels
        if selected_opt and selected_opt.suggested_channels
        else static_promos["suggested_channels"]
    )
    promotion_means = (
        selected_opt.promotion_means
        if selected_opt and selected_opt.promotion_means
        else static_promos["promotion_means"]
    )

    subagents_roster = build_subagents_roster(merchant_context, channel_matrix)
    outreach_blueprint = build_outreach_blueprint(
        merchant_context=merchant_context,
        channel_matrix=channel_matrix,
        user_budget=user_budget,
        top_rival=top_rival,
        campaign_days=days,
    )

    execution_calendar = build_execution_calendar(
        campaign_days=days,
        campaign_type=ctype,
        core_goal=cgoal,
        sub_goals=resolved_sub_goals,
    )

    return CampaignStrategyBrief(
        executive_summary=executive_summary,
        primary_positioning_pillar=primary_positioning_pillar,
        target_metrics=target_metrics,
        channel_matrix=channel_matrix,
        suggested_channels=suggested_channels,
        promotion_means=promotion_means,
        strategic_angles=strategic_angles,
        execution_calendar=execution_calendar,
        budget_assumptions=build_budget_assumptions(merchant_context, channel_matrix, user_budget),
        user_budget=user_budget,
        competitor_campaign_intel=competitor_intel or [],
        campaign_options=campaign_options or [],
        selected_option_id=selected_option_id or (campaign_options[0].option_id if campaign_options else None),
        subagents_roster=subagents_roster,
        outreach_blueprint=outreach_blueprint,
        approval_status="PENDING_APPROVAL",
        campaign_days=days,
        sub_goals=resolved_sub_goals,
        core_goal=cgoal,
        campaign_type=ctype if ctype != "general" else None,
    )
