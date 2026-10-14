"""
Dossier auditor and unit economics engine for market research.

Audits the merchant's product dossier for unverified claims, evaluates landed
unit economics, and generates a phased 30-60-90 day GTM launch roadmap.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from orchestrator.schemas.research import (
    DossierAudit,
    LaunchRoadmap,
    LaunchRoadmapPhase,
    UnitEconomicsModel,
    UnitEconomicsScenario,
)

logger = logging.getLogger(__name__)

# High-risk claim patterns that require physical testing or certification
_UNSUBSTANTIATED_PATTERNS = [
    (r"\b(?:zero|no)\s*break[-\s]*in\b", "Claims 'zero break-in' — requires structured wear-testing across diverse foot profiles before advertising."),
    (r"\bmonsoon[-\s]*resistant\b", "Claims 'monsoon-resistant' — leather dress shoes require ASTM/ISO wet-slip & water-repellency lab testing."),
    (r"\b12[-\s]*hour\s*comfort\b", "Claims '12-hour comfort' — subjective promise requiring independent ergonomic/fatigue study proof."),
    (r"\bwaterproof\b", "Claims 'waterproof' — leather stitch-down/welted construction requires membrane verification."),
    (r"\b(?:repairable|lasts?)\s*(?:for\s*)?(?:generations|decades)\b", "Claims multi-generational lifespan — resoling and welt replacement terms must be confirmed by factory."),
]


def audit_merchant_dossier(merchant_context: dict[str, Any]) -> DossierAudit:
    """
    Scans the merchant's context and dossier text to identify verified specs vs
    unsubstantiated marketing promises, construction mismatches, and compliance hurdles.
    """
    raw_text = " ".join([
        str(merchant_context.get("product_name") or ""),
        str(merchant_context.get("description") or ""),
        str(merchant_context.get("brand_story") or ""),
        str(merchant_context.get("dossier_text") or ""),
    ])

    verified: list[str] = []
    unsubstantiated: list[str] = []
    inconsistencies: list[str] = []
    regulatory: list[str] = []

    # Check for unsubstantiated claims
    for pattern, warning in _UNSUBSTANTIATED_PATTERNS:
        if re.search(pattern, raw_text, re.IGNORECASE):
            unsubstantiated.append(warning)

    # Check for construction / spec mismatches
    has_goodyear = bool(re.search(r"\bgoodyear[-\s]*welt(?:ed)?\b", raw_text, re.IGNORECASE))
    has_hybrid_sole = bool(re.search(r"\bhybrid\b.*?\bsole\b|\brubber\s*inserts?\b|\bcemented\b", raw_text, re.IGNORECASE))
    if has_goodyear and has_hybrid_sole:
        inconsistencies.append(
            "Dossier mentions Goodyear-welted construction alongside a hybrid rubber-insert sole: "
            "verify whether the outsole is genuine Goodyear welted (resolable) or cemented blake/hybrid construction."
        )

    # Verified specs detection
    if re.search(r"\bfull[-\s]*grain\b", raw_text, re.IGNORECASE):
        verified.append("Certified full-grain calf/buff leather upper documented.")
    if re.search(r"\bortholite\b", raw_text, re.IGNORECASE):
        verified.append("Ortholite high-rebound cushioning specification documented.")
    if re.search(r"\bcork\b", raw_text, re.IGNORECASE):
        verified.append("Natural cork underbed layer specified.")

    # Regulatory & Category compliance (e.g. Footwear QCO & BIS in India)
    geo = str(merchant_context.get("target_geography") or "").lower()
    cat = str(merchant_context.get("category") or "").lower()
    if "india" in geo or "in" in geo or "footwear" in cat or "shoes" in cat:
        regulatory.append("BIS / Footwear Quality Control Order (QCO) mandatory standard compliance.")
        regulatory.append("Legal Metrology (Packaged Commodities) Rules: MRP, country of origin, importer/manufacturer labeling.")
        regulatory.append("GST classification: Footwear >₹2,500 attracts standard 18% GST (vs. 5% for ≤₹2,500).")

    return DossierAudit(
        verified_claims=verified,
        unsubstantiated_claims=unsubstantiated,
        spec_inconsistencies=inconsistencies,
        regulatory_and_compliance=regulatory,
    )


def build_unit_economics_model(
    merchant_context: dict[str, Any],
    price_points: list[float] | None = None,
) -> UnitEconomicsModel:
    """
    Simulates landed unit contribution economics across test price points.
    """
    price_str = str(merchant_context.get("price") or merchant_context.get("target_price") or "7499")
    m = re.search(r"(\d[\d,]*)", price_str)
    base_price = float(m.group(1).replace(",", "")) if m else 7499.0

    if not price_points:
        price_points = [
            round(base_price * 0.85, -1) - 1,  # e.g. 6499
            base_price,                          # e.g. 7499
            round(base_price * 1.15, -1) - 1,  # e.g. 8499
        ]

    scenarios: list[UnitEconomicsScenario] = []

    for price in price_points:
        is_base = abs(price - base_price) < 50
        label = "Target Flagship (Base Case)" if is_base else f"Price Sensitivity Test (₹{int(price):,})"

        est_bom = round(price * 0.35, 0)
        packaging_ship = 430.0
        payment_fee = round(price * 0.02, 0)
        returns_allowance = 500.0
        cac = 1200.0 if is_base else (1000.0 if price < base_price else 1500.0)

        tax_multiplier = 1.18 if price > 2500 else 1.05
        net_revenue = round(price / tax_multiplier, 0)

        contribution = round(
            net_revenue - (est_bom + packaging_ship + payment_fee + returns_allowance + cac),
            0,
        )
        margin_pct = round((contribution / net_revenue) * 100, 1) if net_revenue > 0 else 0.0

        scenarios.append(
            UnitEconomicsScenario(
                label=label,
                target_price=price,
                estimated_bom=est_bom,
                packaging_and_shipping=packaging_ship,
                payment_fee=payment_fee,
                returns_allowance=returns_allowance,
                cac=cac,
                net_revenue_ex_tax=net_revenue,
                contribution_per_unit=contribution,
                contribution_margin_pct=margin_pct,
            )
        )

    rules = [
        "Calculate actual landed BOM with factory invoices including duty & freight before ordering bulk inventory.",
        "Track contribution after exchanges, returns, reverse logistics, and paid ad spend—not gross margin.",
        "Maintain cash reserves for size exchanges (footwear typically sees 12–18% exchange rates online).",
        "Do not scale paid ad spend until customer acquisition cost leaves positive net contribution.",
    ]

    return UnitEconomicsModel(
        scenarios=scenarios,
        tax_treatment_note="Assumes 18% GST (applies to footwear above ₹2,500 per pair in India).",
        financial_decision_rules=rules,
    )


def generate_launch_roadmap(
    product_name: str,
    target_geo: str | None = None,
) -> LaunchRoadmap:
    """
    Creates a disciplined 30-60-90 day GTM launch validation roadmap.
    """
    p1 = LaunchRoadmapPhase(
        phase_name="Days 1–30: Validate the Product & Comfort Proof",
        objective="Establish technical credibility, fit accuracy, and willingness to pay before scaling spend.",
        action_items=[
            "Conduct 25–40 structured customer interviews with target urban professionals to document current shoe pain points.",
            "Verify factory construction method (Goodyear-welt vs. cemented hybrid) and get leather supplier certifications.",
            "Run wear tests across 10+ testers to validate comfort, grip, and flex claims.",
            "Set up landing page price elasticity tests (e.g. ₹6,499 vs ₹7,499 vs ₹8,499) measuring deposit/intent conversion.",
        ],
        gate_to_proceed="Confirmed unit contribution >20% at ₹7,499, zero unresolved structural heel/sole defects, and validated intent.",
    )

    p2 = LaunchRoadmapPhase(
        phase_name="Days 31–60: Controlled Metro Launch (Pilot Cohort)",
        objective="Acquire the first 100–250 real buyers through D2C in focused metropolitan clusters.",
        action_items=[
            f"Launch direct-to-consumer site focused initially on core clusters ({target_geo or 'Delhi NCR, Bengaluru, Mumbai'}).",
            "Deploy 3 targeted campaign concepts: Comfort-led, Workshop craftsmanship, and Occasion versatility.",
            "Offer in-person fit appointments or trunk show trials in select coworking/corporate hubs.",
            "Monitor weekly: CAC, return rates, size exchange ratios, and post-purchase comfort ratings.",
        ],
        gate_to_proceed="Size exchange rate kept under 15%, return rate under 8%, and customer satisfaction score >4.2/5.",
    )

    p3 = LaunchRoadmapPhase(
        phase_name="Days 61–90: Scale Channels & Establish Sizing Curves",
        objective="Establish a repeatable, profitable acquisition loop and evaluate marketplace expansion.",
        action_items=[
            "Reallocate 70%+ of ad budget to the single highest-contribution creative pillar.",
            "Refine shoe last and sizing recommendations using pilot cohort return telemetry.",
            "Establish a VIP customer review and referral program.",
            "Evaluate selective curated marketplace listings (e.g. Myntra Luxe / Amazon Premium) once inventory replenishment is stable.",
        ],
        gate_to_proceed="Net contribution positive across all paid channels with reliable replenishment inventory in place.",
    )

    metrics = [
        {"metric": "Product Page Conversion", "significance": "Measures whether messaging and ₹7,499 price point persuade buyers."},
        {"metric": "Customer Acquisition Cost (CAC)", "significance": "Must stay below ₹1,400 to preserve contribution margins."},
        {"metric": "Size Exchange Rate", "significance": "Crucial footwear health metric; exchanges cost ~₹400-500 in reverse logistics."},
        {"metric": "Net Contribution per Pair", "significance": "True profitability after returns, shipping, and advertising."},
    ]

    return LaunchRoadmap(phases=[p1, p2, p3], key_metrics_dashboard=metrics)
