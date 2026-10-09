from __future__ import annotations

from typing import Any
from orchestrator.schemas.research import SWOTReportDelta
from orchestrator.schemas.strategy import ChannelAllocation, StrategicAngle


def synthesize_strategic_angles(
    merchant_context: dict[str, Any],
    swot_report: SWOTReportDelta | None,
) -> list[StrategicAngle]:
    """
    Loop 2: Correlates merchant value proposition with competitor positioning gaps
    and weaknesses to derive high-converting messaging angles.
    """
    brand = (merchant_context.get("product_name") or "Our Solution").strip()
    category = (merchant_context.get("category") or "Technology").strip()
    value_prop = (
        merchant_context.get("primary_value_prop")
        or merchant_context.get("goal")
        or "Rapid enterprise deployment and lower operational overhead"
    ).strip()

    angles: list[StrategicAngle] = []

    # If upstream research generated ad angles, leverage them
    if swot_report and swot_report.suggested_ad_angles:
        for i, a in enumerate(swot_report.suggested_ad_angles[:4]):
            angles.append(
                StrategicAngle(
                    angle_title=f"Strategic Angle {i+1}: {a.format_hint or 'Wedge Displacement'}",
                    target_wedge=merchant_context.get("target_geography") or "Mid-Market & Enterprise Accounts",
                    competitor_weakness=a.based_on_weakness or "Rigid incumbent lock-in and high rollout friction",
                    hook=a.hook,
                    messaging_pillar=a.body or value_prop,
                )
            )

    # If fewer than 3 angles, synthesize from competitor weaknesses
    top_competitors = swot_report.competitors if swot_report else []
    top_comp = top_competitors[0] if top_competitors else None
    rival_name = (top_comp.product_name or top_comp.brand_name) if top_comp else "Legacy Incumbents"
    raw_weaknesses = getattr(top_comp, "weaknesses_mined", None) or getattr(top_comp, "weaknesses", None) or []
    rival_weakness = (
        raw_weaknesses[0]
        if raw_weaknesses
        else "Protracted implementation cycles and unpredictable retainers"
    )

    if len(angles) < 1:
        angles.append(
            StrategicAngle(
                angle_title="Angle 1: Speed to Operational Impact",
                target_wedge="VP Engineering & Product Leaders evaluating replacements",
                competitor_weakness=rival_weakness,
                hook=f"Why fast-moving teams are choosing {brand} over {rival_name}",
                messaging_pillar=f"{brand} delivers guaranteed rollout velocity without legacy onboarding delays.",
            )
        )
    if len(angles) < 2:
        angles.append(
            StrategicAngle(
                angle_title="Angle 2: Zero Migration Friction",
                target_wedge="Enterprise Teams stalled by contract overhead",
                competitor_weakness="Opaque pricing and multi-quarter lock-in agreements",
                hook=f"Deploy enterprise-grade {category} without the 6-month consulting tax",
                messaging_pillar=f"Transparent milestone delivery with guaranteed security and continuity.",
            )
        )
    if len(angles) < 3:
        angles.append(
            StrategicAngle(
                angle_title="Angle 3: Proven Category Modernization",
                target_wedge="Procurement & Technology decision-makers seeking modern alternatives",
                competitor_weakness="Outdated architecture and sluggish response times",
                hook=f"The modern standard in {category} built for 2026 demands",
                messaging_pillar=f"Tailored architecture engineered specifically to outpace legacy competitors.",
            )
        )

    return angles


def derive_channel_matrix(
    merchant_context: dict[str, Any],
    swot_report: SWOTReportDelta | None,
) -> list[ChannelAllocation]:
    """
    Loop 2: Derives optimal channel allocations based on audience behavior,
    category price points, and competitor blind spots.
    """
    category = (merchant_context.get("category") or "").lower()
    is_b2b_or_enterprise = (
        "enterprise" in category or "b2b" in category or "agency" in category or "development" in category
    )

    if is_b2b_or_enterprise:
        return [
            ChannelAllocation(
                channel="linkedin",
                budget_percentage=40,
                recommended_spend_usd=4000.0,
                rationale="Primary decision-maker dwell channel. High-conviction thought leadership and sponsored InMail.",
                projected_roi="3.4x Pipeline Return",
            ),
            ChannelAllocation(
                channel="email",
                budget_percentage=25,
                recommended_spend_usd=2500.0,
                rationale="Direct account-based outreach to evaluated wedge accounts migrating off legacy tools.",
                projected_roi="4.8x Pipeline Return",
            ),
            ChannelAllocation(
                channel="retarget",
                budget_percentage=20,
                recommended_spend_usd=2000.0,
                rationale="High-intent capture of visitors viewing competitor comparisons and pricing case studies.",
                projected_roi="3.1x Conversion Return",
            ),
            ChannelAllocation(
                channel="search",
                budget_percentage=15,
                recommended_spend_usd=1500.0,
                rationale="Targeting high-intent brand-alternative search queries ('rival alternative', 'switch from rival').",
                projected_roi="2.9x Conversion Return",
            ),
        ]
    else:
        return [
            ChannelAllocation(
                channel="search",
                budget_percentage=35,
                recommended_spend_usd=3500.0,
                rationale="Captures active category search demand with targeted solution keywords.",
                projected_roi="3.2x ROAS",
            ),
            ChannelAllocation(
                channel="retarget",
                budget_percentage=25,
                recommended_spend_usd=2500.0,
                rationale="Multi-touch retargeting across Meta and Display to reduce funnel abandonment.",
                projected_roi="3.8x ROAS",
            ),
            ChannelAllocation(
                channel="email",
                budget_percentage=25,
                recommended_spend_usd=2500.0,
                rationale="Lifecycle nurturing sequences to convert trials and warm leads into paid contracts.",
                projected_roi="5.0x LTV Return",
            ),
            ChannelAllocation(
                channel="content",
                budget_percentage=15,
                recommended_spend_usd=1500.0,
                rationale="Educational guides and migration benchmarks driving compounding organic discovery.",
                projected_roi="2.5x Organic Return",
            ),
        ]
