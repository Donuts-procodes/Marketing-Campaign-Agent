from __future__ import annotations

import re
from typing import Any
from orchestrator.schemas.strategy import TargetMetric


def decompose_objectives(
    merchant_context: dict[str, Any],
    goal_text: str | None = None,
    campaign_days: int | None = None,
    sub_goals: list[str] | None = None,
) -> list[TargetMetric]:
    """
    Loop 1: Decomposes the merchant's core business goal, campaign type,
    user-specified sub-goals, and custom campaign duration into quantifiable target metrics.
    """
    raw_goal = (goal_text or merchant_context.get("goal") or "").strip()
    primary_value_prop = str(merchant_context.get("primary_value_prop") or "").strip()
    goal = raw_goal or primary_value_prop or "Drive profitable customer acquisition"
    category = (merchant_context.get("category") or "Technology").lower()
    product_name = str(merchant_context.get("product_name") or "Product").strip()

    # Determine campaign duration in days (default 90)
    days = campaign_days or int(merchant_context.get("campaign_days") or 90)
    days = max(3, min(days, 365))

    # Collect sub-goals
    user_sub_goals: list[str] = []
    if sub_goals:
        user_sub_goals.extend(sub_goals)
    elif merchant_context.get("sub_goals"):
        user_sub_goals.extend(merchant_context.get("sub_goals"))

    # Detect or normalize campaign type
    raw_type = str(merchant_context.get("campaign_type") or "").lower()
    goal_lower = goal.lower()
    if raw_type:
        campaign_type = raw_type
    elif "launch" in goal_lower or "release" in goal_lower or "pre-order" in goal_lower:
        campaign_type = "product_launch"
    elif "sale" in goal_lower or "ecom" in category or "d2c" in category or "store" in category or "retail" in category:
        campaign_type = "ecommerce_sales"
    elif "aware" in goal_lower or "reach" in goal_lower or "brand" in goal_lower:
        campaign_type = "brand_awareness"
    elif "competitor" in goal_lower or "displace" in goal_lower or "switch" in goal_lower or "takeover" in goal_lower:
        campaign_type = "competitor_takeover"
    elif "lead" in goal_lower or "b2b" in category or "consulting" in category or "enterprise" in category:
        campaign_type = "lead_gen"
    else:
        campaign_type = "performance_growth"

    metrics: list[TargetMetric] = []

    # 1. Incorporate User-Specified Sub-Goals First
    for idx, sg in enumerate(user_sub_goals):
        clean_sg = sg.strip()
        if not clean_sg:
            continue
        metrics.append(
            TargetMetric(
                name=f"Sub-Goal {idx + 1}: {clean_sg[:45]}",
                target_value=f"Target: Complete within {days} days",
                baseline="Pre-campaign baseline (0%)",
                measurement_window=f"{days} days",
                is_sub_goal=True,
            )
        )

    # 2. Derive Core Metrics Grounded in Campaign Type & Duration
    short_window = f"{max(7, days // 3)} days"
    mid_window = f"{max(14, (days * 2) // 3)} days"
    full_window = f"{days} days"

    if campaign_type == "product_launch":
        metrics.append(
            TargetMetric(
                name=f"Launch Velocity ({product_name})",
                target_value="Initial adoption target reached",
                baseline=None,
                measurement_window=short_window,
            )
        )
        metrics.append(
            TargetMetric(
                name="Blended Launch CAC",
                target_value="Set from the Phase 1 test baseline",
                baseline=None,
                measurement_window=mid_window,
            )
        )
        metrics.append(
            TargetMetric(
                name="Early Customer Retention & Referrals",
                target_value="Set from the Phase 1 test baseline",
                baseline=None,
                measurement_window=full_window,
            )
        )
    elif campaign_type == "ecommerce_sales":
        metrics.append(
            TargetMetric(
                name="Target Blended ROAS",
                target_value="Set from the Phase 1 test baseline",
                baseline=None,
                measurement_window=full_window,
            )
        )
        metrics.append(
            TargetMetric(
                name="Cost Per Purchase (CPA)",
                target_value="Set from the Phase 1 test baseline",
                baseline=None,
                measurement_window=mid_window,
            )
        )
        metrics.append(
            TargetMetric(
                name="Checkout Funnel Conversion Rate",
                target_value="Set from the Phase 1 test baseline",
                baseline=None,
                measurement_window=full_window,
            )
        )
    elif campaign_type == "brand_awareness":
        metrics.append(
            TargetMetric(
                name="Verified Target Reach & Impressions",
                target_value="Set from the Phase 1 test baseline",
                baseline=None,
                measurement_window=full_window,
            )
        )
        metrics.append(
            TargetMetric(
                name="Branded Search Volume Lift",
                target_value="Set from the Phase 1 test baseline",
                baseline=None,
                measurement_window=mid_window,
            )
        )
        metrics.append(
            TargetMetric(
                name="Cost Per High-Intent Engagement (CPE)",
                target_value="Set from the Phase 1 test baseline",
                baseline=None,
                measurement_window=short_window,
            )
        )
    elif campaign_type == "competitor_takeover":
        metrics.append(
            TargetMetric(
                name="Competitor Switcher Conversions",
                target_value="Capture switchers migrating from incumbent rivals",
                baseline=None,
                measurement_window=full_window,
            )
        )
        metrics.append(
            TargetMetric(
                name="Cost Per Displaced Opportunity",
                target_value="Set from the Phase 1 test baseline",
                baseline=None,
                measurement_window=mid_window,
            )
        )
        metrics.append(
            TargetMetric(
                name="Migration Cycle Velocity",
                target_value="Set from the Phase 1 test baseline",
                baseline=None,
                measurement_window=full_window,
            )
        )
    else:  # lead_gen / performance_growth / default
        metrics.append(
            TargetMetric(
                name="Cost Per Qualified Opportunity (CPQO)",
                target_value="Set from the Phase 1 test baseline",
                baseline=None,
                measurement_window=mid_window,
            )
        )
        metrics.append(
            TargetMetric(
                name="Qualified Pipeline Added",
                target_value="Direct contribution to core business goal",
                baseline=None,
                measurement_window=full_window,
            )
        )
        metrics.append(
            TargetMetric(
                name="Lead-to-Discussion Conversion Velocity",
                target_value="Set from the Phase 1 test baseline",
                baseline=None,
                measurement_window=short_window,
            )
        )

    # Payback needs unit economics; it is computed in the brief's economics when cost is known.
    metrics.append(
        TargetMetric(
            name="Marketing Spend Payback Period",
            target_value="Computed once unit cost is known (see unknowns)",
            baseline=None,
            measurement_window=full_window,
        )
    )

    return metrics


async def hydrate_campaign_context_from_mongo(
    merchant_context: dict[str, Any],
    swot_report: Any | None = None,
    job_id: str | None = None,
) -> tuple[dict[str, Any], Any | None, dict[str, Any]]:
    """
    Hydrates campaign strategy with user client data, product sales, competitor client data,
    consumer lists, merchant ICP, and competitor ICP.
    Fetches completed research runs from MongoDB if state data is incomplete.
    """
    from orchestrator.core.storage import get_storage
    from orchestrator.schemas.research import SWOTReportDelta

    hydrated_context = dict(merchant_context)
    hydrated_swot = swot_report
    storage = get_storage()

    product_name = str(hydrated_context.get("product_name") or "").strip()
    category = str(hydrated_context.get("category") or "").strip()

    # 1. If swot_report or competitors missing, attempt to retrieve finished research from MongoDB
    if (not hydrated_swot or not getattr(hydrated_swot, "competitors", None)) and storage:
        doc = None
        if job_id:
            try:
                doc = await storage.load_run(job_id)
            except Exception:
                pass
        if not doc and product_name:
            try:
                doc = await storage.find_latest_run_by_product(product_name, category)
            except Exception:
                pass

        if doc:
            if not hydrated_swot and doc.get("report"):
                try:
                    hydrated_swot = SWOTReportDelta.model_validate(doc["report"])
                except Exception:
                    pass
            # Backfill merchant context details from MongoDB document
            stored_mc = doc.get("merchant_context") or {}
            for k, v in stored_mc.items():
                if k not in hydrated_context or not hydrated_context[k]:
                    hydrated_context[k] = v

    # 2. Extract User Client Data & Product Sales
    user_clients = (
        hydrated_context.get("client_data")
        or hydrated_context.get("clients")
        or hydrated_context.get("existing_customer_profiles")
        or hydrated_context.get("client_dossier")
        or []
    )
    product_sales = (
        hydrated_context.get("product_sales")
        or hydrated_context.get("sales_data")
        or hydrated_context.get("revenue_data")
        or hydrated_context.get("price_usd")
        or ""
    )

    # 3. Extract Merchant ICP
    merchant_icp = (
        hydrated_context.get("target_audience")
        or hydrated_context.get("merchant_icp")
        or hydrated_context.get("ideal_customer_profile")
        or hydrated_context.get("icp")
        or ""
    )

    # 4. Extract Competitor Client Data, Consumer Lists, and Competitor ICPs
    competitor_client_map: dict[str, list[str]] = {}
    competitor_consumer_map: dict[str, list[str]] = {}
    competitor_icp_map: dict[str, str] = {}

    if hydrated_swot and getattr(hydrated_swot, "competitors", None):
        for comp in hydrated_swot.competitors:
            c_name = comp.product_name or comp.brand_name
            # Flagship marquee enterprise/client lists
            flagship_clients: list[str] = []
            if getattr(comp, "leap_benchmark", None) and comp.leap_benchmark.flagship_clients:
                flagship_clients.extend(comp.leap_benchmark.flagship_clients)
            competitor_client_map[c_name] = flagship_clients

            # Consumer reviews, buyer personas, and pain points
            consumer_personas: list[str] = []
            if getattr(comp, "review_context", None):
                if comp.review_context.buyer_personas:
                    consumer_personas.extend(comp.review_context.buyer_personas)
                if comp.review_context.top_complaint_drivers:
                    consumer_personas.extend([c.topic for c in comp.review_context.top_complaint_drivers[:3]])
            elif getattr(comp, "weaknesses_mined", None):
                consumer_personas.extend(comp.weaknesses_mined[:3])
            competitor_consumer_map[c_name] = consumer_personas

            # Synthesize competitor ICP
            pricing_desc = comp.pricing_model or "Standard market tier"
            personas_str = ", ".join(consumer_personas[:2]) if consumer_personas else "general buyers"
            competitor_icp_map[c_name] = f"Buyers seeking {personas_str} at {pricing_desc}"

    extracted_intelligence = {
        "user_client_data": user_clients,
        "product_sales": product_sales,
        "merchant_icp": merchant_icp,
        "competitor_clients": competitor_client_map,
        "competitor_consumers": competitor_consumer_map,
        "competitor_icps": competitor_icp_map,
    }

    # Enrich merchant_context with extracted ICP and audience if missing
    if merchant_icp and not hydrated_context.get("target_audience"):
        hydrated_context["target_audience"] = merchant_icp

    return hydrated_context, hydrated_swot, extracted_intelligence

