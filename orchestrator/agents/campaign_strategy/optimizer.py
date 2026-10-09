from __future__ import annotations

from typing import Any
from orchestrator.schemas.research import SWOTReportDelta
from orchestrator.schemas.strategy import (
    CampaignStrategyBrief,
    ChannelAllocation,
    PhaseMilestone,
    StrategicAngle,
    TargetMetric,
)


def build_execution_calendar() -> list[PhaseMilestone]:
    """
    Loop 3: Builds the 90-day phased execution roadmap and dependencies.
    """
    return [
        PhaseMilestone(
            phase_name="Phase 1: Foundation & Positioning Validation",
            weeks="Weeks 1 - 3",
            focus="Establish verified category wedge messaging, deploy landing page comparison teardowns, and configure tracking.",
            deliverables=[
                "High-converting comparative landing page vs top 2 rivals",
                "Email sequences (Angles 1 & 2) drafted and QA-approved",
                "Conversion tracking & UTM attribution pipelines verified",
            ],
        ),
        PhaseMilestone(
            phase_name="Phase 2: Alpha Wedge Ingress",
            weeks="Weeks 4 - 8",
            focus="Launch paid B2B search and cold LinkedIn account-based campaigns targeted at high-friction incumbent accounts.",
            deliverables=[
                "Active LinkedIn and search ads running with strict CPA guardrails",
                "Weekly creative delta testing and ad hook optimization",
                "First cohort of warm MQL discussions conducted",
            ],
        ),
        PhaseMilestone(
            phase_name="Phase 3: Scale & Retargeting Flight",
            weeks="Weeks 9 - 12",
            focus="Shift budget into top-performing strategic angle; scale retargeting to maximize funnel completion.",
            deliverables=[
                "Dynamic retargeting flight active across multi-touch channels",
                "Full 90-day CAC and pipeline ROI performance audit",
                "Handoff to automated continuous monitoring",
            ],
        ),
    ]


def build_budget_assumptions(
    merchant_context: dict[str, Any],
    channel_matrix: list[ChannelAllocation],
) -> list[str]:
    """
    Loop 3: Flags explicit budget assumptions, constraints, and safety guardrails.
    """
    total_spend = sum(c.recommended_spend_usd or 0 for c in channel_matrix)
    return [
        f"Initial test flight calibrated on an indicative ${total_spend:,.0f} 90-day deployment window.",
        "Budgets should be scaled dynamically only after Phase 1 CPA / CPQO thresholds are validated.",
        "Creative assets are produced in-house using the integrated Content Studio.",
        "Zero long-term agency retainer commitments assumed; 100% autonomous orchestrator routing.",
    ]


def consolidate_strategy_brief(
    merchant_context: dict[str, Any],
    swot_report: SWOTReportDelta | None,
    target_metrics: list[TargetMetric],
    channel_matrix: list[ChannelAllocation],
    strategic_angles: list[StrategicAngle],
) -> CampaignStrategyBrief:
    """
    Loop 3: Consolidates the complete execution-ready Campaign Strategy Brief.
    """
    brand = (merchant_context.get("product_name") or "Our Solution").strip()
    category = (merchant_context.get("category") or "Technology").strip()
    top_competitors = swot_report.competitors if swot_report else []
    top_rival = (top_competitors[0].product_name or top_competitors[0].brand_name) if top_competitors else "incumbent solutions"

    executive_summary = (
        f"Campaign strategy engineered to position {brand} as the trusted category leader in {category}. "
        f"By attacking {top_rival}'s high onboarding friction, complex enterprise agreements, and sluggish support, "
        f"the campaign deploys high-conviction messaging across targeted high-ROI channels to compress sales cycles "
        f"and capture dissatisfied switchers."
    )

    primary_positioning_pillar = (
        f"Displace {top_rival} through guaranteed deployment velocity, transparent pricing, and zero migration downtime."
    )

    return CampaignStrategyBrief(
        executive_summary=executive_summary,
        primary_positioning_pillar=primary_positioning_pillar,
        target_metrics=target_metrics,
        channel_matrix=channel_matrix,
        strategic_angles=strategic_angles,
        execution_calendar=build_execution_calendar(),
        budget_assumptions=build_budget_assumptions(merchant_context, channel_matrix),
        approval_status="PENDING_APPROVAL",
    )
