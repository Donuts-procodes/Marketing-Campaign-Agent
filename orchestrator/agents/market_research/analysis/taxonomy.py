"""
Dynamic Parameter Taxonomy reasoning, parameter refinement, and density evaluation.
"""

from __future__ import annotations

import logging
from typing import Any

from orchestrator.agents.market_research.analysis.archetype import (
    CREATOR as ARCH_CREATOR,
    ECOMMERCE as ARCH_ECOMMERCE,
    LOCAL as ARCH_LOCAL,
    SAAS as ARCH_SAAS,
    SERVICE as ARCH_SERVICE,
    resolve as resolve_archetype,
)
from orchestrator.core.clock import today_iso
from orchestrator.schemas.research import CompetitorProfile, DynamicParameterTaxonomy

logger = logging.getLogger(__name__)


async def reason_dynamic_parameters(
    merchant_context: dict[str, Any],
    llm: Any = None,
) -> DynamicParameterTaxonomy:
    """
    Reasons over merchant context, campaign goal, business model, and customer profiles
    to synthesize 4 to 8 Critical JTBD Drivers and 15 to 25 Minor Attributes tailored
    dynamically for any campaign type (B2B SaaS, D2C eCommerce, Local Services, Creators, etc.).
    """
    product_name = merchant_context.get("product_name", "Product")
    category = merchant_context.get("category", "General")
    value_prop = merchant_context.get("primary_value_prop", "")
    goal = merchant_context.get("goal", "")
    campaign_type = merchant_context.get("campaign_type", "")
    business_model = merchant_context.get("business_model", "")
    target_geography = merchant_context.get("target_geography", "")
    price_model = merchant_context.get("price_model", "")
    customers = merchant_context.get("existing_customer_profiles", [])
    dossier = merchant_context.get("dossier", "")

    if llm is not None:
        try:
            structured_llm = llm.with_structured_output(DynamicParameterTaxonomy)
            prompt = (
                f"Today's date is {today_iso()}; treat it as the reference point for what counts as "
                f"current in this market, rather than your training data.\n\n"
                f"Analyze this offering and construct the dynamic competitive evaluation framework for this campaign:\n"
                f"Offering / Brand: {product_name}\n"
                f"Category / Market: {category}\n"
                f"Primary Value Proposition: {value_prop}\n"
                f"Campaign Goal: {goal or 'Competitive positioning and market acquisition'}\n"
                f"Campaign Type: {campaign_type or 'Growth & Performance'}\n"
                f"Business Model: {business_model or 'Not specified'}\n"
                f"Target Geography: {target_geography or 'Global / Unrestricted'}\n"
                f"Pricing Structure: {price_model or 'Standard market rates'}\n"
                f"Target Customer Profiles: {', '.join(customers) if customers else 'Standard ICP'}\n"
                f"Dossier / Brief Notes: {dossier[:1500] if dossier else 'None'}\n\n"
                f"Generate:\n"
                f"1. Exactly 4 to 8 Critical JTBD Drivers (dealbreakers that dictate buyer choice in this specific market).\n"
                f"2. Exactly 15 to 25 Minor Attributes (technical specs, commercial terms, delivery, and features)."
            )
            taxonomy = await structured_llm.ainvoke(prompt)
            validated = (
                taxonomy
                if isinstance(taxonomy, DynamicParameterTaxonomy)
                else DynamicParameterTaxonomy.model_validate(taxonomy)
            )
            # Guarantee strict 4 to 8 critical dealbreaker drivers
            drivers = [d.strip() for d in validated.critical_jtbd_drivers if d.strip()]
            if len(drivers) < 4:
                # Top up from minor attributes if LLM returned fewer than 4
                for minor in validated.minor_attributes:
                    if minor not in drivers:
                        drivers.append(minor)
                    if len(drivers) >= 4:
                        break
            drivers = drivers[:8]
            validated.critical_jtbd_drivers = drivers
            return validated
        except Exception as exc:
            logger.warning("LLM dynamic parameter generation failed, using intelligent baseline: %s", exc)

    # Archetype comes from the shared resolver, so the parameter framework cannot disagree
    # with the search queries built for the same merchant.
    context_corpus = f"{category} {business_model} {value_prop} {goal} {campaign_type}".lower()
    archetype = resolve_archetype(merchant_context, context_corpus)

    is_services = archetype in (ARCH_SERVICE, ARCH_LOCAL)
    is_saas = archetype == ARCH_SAAS
    is_d2c = archetype == ARCH_ECOMMERCE
    is_creator_course = archetype == ARCH_CREATOR

    if is_services:
        return DynamicParameterTaxonomy(
            critical_jtbd_drivers=[
                "service_area_coverage",
                "client_reputation_reviews",
                "pricing_and_retainer_structure",
                "response_and_turnaround_time",
                "credential_and_licensing",
                "portfolio_case_studies",
            ],
            minor_attributes=[
                "hourly_rate_estimate",
                "consultation_policy",
                "team_seniority",
                "custom_proposal_speed",
                "contract_length_flexibility",
                "emergency_support_availability",
                "industry_specialization",
                "reporting_and_communication_cadence",
                "client_retention_rate",
                "payment_milestones",
                "guarantees_or_sla",
                "tools_and_tech_stack",
                "client_portal_access",
                "onboarding_kickoff_timeline",
                "case_study_metrics",
            ],
        )

    if is_d2c:
        return DynamicParameterTaxonomy(
            critical_jtbd_drivers=[
                "product_efficacy_quality",
                "price_point_and_bundles",
                "shipping_speed_and_costs",
                "brand_aesthetic_social_proof",
                "return_and_warranty_policy",
                "materials_or_ingredients",
            ],
            minor_attributes=[
                "shipping_lead_time_days",
                "return_window_days",
                "subscription_discount_pct",
                "packaging_and_sustainability",
                "customer_review_rating",
                "variant_selection_range",
                "origin_and_manufacturing",
                "free_shipping_threshold",
                "loyalty_rewards_program",
                "influencer_and_press_mentions",
                "stock_availability",
                "bundle_savings_rate",
                "unboxing_experience_rating",
                "cruelty_free_or_organic_certs",
                "first_order_discount",
            ],
        )

    if is_saas:
        return DynamicParameterTaxonomy(
            critical_jtbd_drivers=[
                "pricing_tier_per_seat",
                "integration_ecosystem",
                "security_and_compliance",
                "deployment_architecture",
                "onboarding_time_to_value",
                "enterprise_sla_support",
            ],
            minor_attributes=[
                "sso_saml_support",
                "audit_logging",
                "uptime_sla_guarantee",
                "api_rate_limits",
                "webhook_events",
                "data_retention_policy",
                "export_data_formats",
                "rbac_permissions",
                "custom_domain_support",
                "mobile_app_parity",
                "soc2_gdpr_compliance",
                "free_tier_allowance",
                "annual_discount_percentage",
                "sdk_language_support",
                "self_serve_onboarding",
            ],
        )

    if is_creator_course:
        return DynamicParameterTaxonomy(
            critical_jtbd_drivers=[
                "instructor_authority_credibility",
                "curriculum_depth_and_structure",
                "community_and_peer_access",
                "price_and_payment_plans",
                "student_outcomes_transformation",
                "money_back_guarantee",
            ],
            minor_attributes=[
                "course_duration_hours",
                "live_coaching_frequency",
                "templates_and_assets_included",
                "completion_certificate",
                "refund_window_days",
                "student_community_platform",
                "lifetime_access_policy",
                "update_frequency",
                "accreditation_or_badges",
                "one_on_one_support_access",
                "prerequisite_skill_level",
                "homework_review_policy",
                "student_testimonial_count",
                "affiliate_program_available",
                "installment_options",
            ],
        )

    # General Dynamic Fallback (Extracts tokens directly from merchant value prop & category)
    category_tokens = [w.lower() for w in category.replace("/", " ").replace("-", " ").split() if len(w) > 2]
    value_prop_tokens = [w.lower() for w in value_prop.replace("/", " ").replace("-", " ").split() if len(w) > 3]

    custom_drivers = [
        f"{tok}_performance" for tok in (value_prop_tokens[:2] + category_tokens[:2])
    ]
    base_critical = [
        "core_value_proposition",
        "pricing_and_commercial_tier",
        "primary_use_case_fit",
        "target_buyer_segment",
        "performance_and_reliability",
        "ecosystem_compatibility",
    ]
    critical_drivers = list(dict.fromkeys(custom_drivers + base_critical))[:6]

    base_minor = [
        "specifications_and_capacity",
        "pricing_tiers_and_discounts",
        "build_quality_and_materials",
        "deployment_and_setup_complexity",
        "warranty_and_sla_guarantee",
        "customer_support_quality",
        "user_sentiment_score",
        "security_and_compliance",
        "customization_depth",
        "maintenance_and_running_costs",
        "integration_breadth",
        "availability_and_shipping",
        "feature_completeness",
        "community_adoption",
        "onboarding_time_to_value",
    ]

    return DynamicParameterTaxonomy(
        critical_jtbd_drivers=critical_drivers,
        minor_attributes=base_minor,
    )


def refine_parameters_from_findings(
    taxonomy: DynamicParameterTaxonomy,
    extracted_text: list[str],
) -> DynamicParameterTaxonomy:
    """
    Dynamically refines parameters based on observations mined from crawled web pages.
    Parses specification tables, technical bullet points, and key-value pairs without hardcoded product lists.
    """
    import re

    combined = "\n".join(extracted_text)
    updated_minor = list(taxonomy.minor_attributes)

    # 1. Dynamic regex extraction for specification table rows: | Spec Name | Value |
    table_specs = re.findall(r"\|\s*([A-Za-z0-9\s]{3,24})\s*\|\s*[^\|\n]{2,50}\s*\|", combined)
    for raw_spec in table_specs:
        cleaned = re.sub(r"\s+", "_", raw_spec.strip().lower())
        if cleaned and cleaned not in ("parameter", "specification", "attribute", "feature", "name", "metric"):
            if cleaned not in updated_minor and len(cleaned) >= 4:
                updated_minor.append(cleaned)

    # 2. Dynamic regex extraction for spec key-value bullet points: - Battery: 500mAh
    bullet_specs = re.findall(r"(?:^|\n)[\-\*•]\s*([A-Za-z0-9\s]{3,20}):\s*([^\n]{2,50})", combined)
    for raw_spec, _ in bullet_specs:
        cleaned = re.sub(r"\s+", "_", raw_spec.strip().lower())
        if cleaned and cleaned not in ("note", "warning", "tip", "source", "http", "https"):
            if cleaned not in updated_minor and len(cleaned) >= 4:
                updated_minor.append(cleaned)

    return DynamicParameterTaxonomy(
        critical_jtbd_drivers=taxonomy.critical_jtbd_drivers,
        minor_attributes=updated_minor[:25],
    )


def _param_key(name: str) -> str:
    """Normalizes parameter names so 'Sensor DPI', 'sensor-dpi' and 'sensor_dpi' match."""
    return "_".join("".join(c.lower() if c.isalnum() else " " for c in name).split())


def calculate_attribute_density(
    competitors: list[CompetitorProfile],
    taxonomy: DynamicParameterTaxonomy | None,
) -> float:
    """
    Calculates percentage of tracked parameters populated across discovered competitors.
    Returns 0.0 when no competitor or taxonomy data exists.
    """
    if not competitors or not taxonomy:
        return 0.0

    all_params = taxonomy.critical_jtbd_drivers + taxonomy.minor_attributes
    if not all_params:
        return 0.0

    total_cells = len(competitors) * len(all_params)
    populated_cells = 0
    for comp in competitors:
        filled_keys = {_param_key(k) for k, v in comp.dynamic_attributes.items() if v}
        claims_text = " ".join(comp.core_claims).lower()
        for param in all_params:
            key = _param_key(param)
            if key in filled_keys or key.replace("_", " ") in claims_text:
                populated_cells += 1

    return round(min(populated_cells / total_cells, 1.0), 4)
