from __future__ import annotations

import re
from typing import Any
from orchestrator.schemas.strategy import TargetMetric


def decompose_objectives(
    merchant_context: dict[str, Any],
    goal_text: str | None = None,
) -> list[TargetMetric]:
    """
    Loop 1: Decomposes high-level business objectives and constraints
    into measurable, quantifiable target metrics.
    """
    goal = (goal_text or merchant_context.get("goal") or merchant_context.get("primary_value_prop") or "").strip()
    category = (merchant_context.get("category") or "Technology").lower()
    price_model = (merchant_context.get("price_model") or "retainer_or_project").lower()

    metrics: list[TargetMetric] = []

    # 1. CAC / Acquisition Cost
    if "enterprise" in category or "consulting" in category or "b2b" in category:
        metrics.append(
            TargetMetric(
                name="Cost Per Qualified Opportunity (CPQO)",
                target_value="< $1,200",
                baseline="Industry benchmark $1,800 - $2,500",
                measurement_window="90 days",
            )
        )
        metrics.append(
            TargetMetric(
                name="Enterprise Sales Pipeline Added",
                target_value="$250,000+ pipeline value",
                baseline="$0 baseline",
                measurement_window="60 days",
            )
        )
    elif "saas" in category or "software" in category:
        metrics.append(
            TargetMetric(
                name="Customer Acquisition Cost (CAC)",
                target_value="< $180 per paying account",
                baseline="SaaS median $280",
                measurement_window="60 days",
            )
        )
        metrics.append(
            TargetMetric(
                name="Trial / Demo to Paid Conversion",
                target_value="> 14% conversion rate",
                baseline="Category baseline 8-10%",
                measurement_window="90 days",
            )
        )
    else:
        metrics.append(
            TargetMetric(
                name="Blended Target CPA",
                target_value="< $95 per conversion",
                baseline="Market average $140",
                measurement_window="60 days",
            )
        )
        metrics.append(
            TargetMetric(
                name="Campaign ROAS (Return on Ad Spend)",
                target_value="> 3.2x ROAS",
                baseline="1.8x - 2.2x benchmark",
                measurement_window="90 days",
            )
        )

    # 2. Conversion Velocity / Time to Value
    metrics.append(
        TargetMetric(
            name="Lead-to-Discussion Sales Velocity",
            target_value="< 14 days cycle time",
            baseline="Incumbent average 45+ days",
            measurement_window="90 days",
        )
    )

    # 3. Payback Period
    metrics.append(
        TargetMetric(
            name="Marketing Spend Payback Period",
            target_value="< 3.5 months",
            baseline="6 - 9 months industry norm",
            measurement_window="180 days",
        )
    )

    return metrics
