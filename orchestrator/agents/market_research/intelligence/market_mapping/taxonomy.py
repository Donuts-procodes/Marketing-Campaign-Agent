"""
Dynamic Parameter Taxonomy reasoning, parameter refinement, and density evaluation.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from orchestrator.agents.market_research.intelligence.advisory.archetype import (
    CREATOR as ARCH_CREATOR,
    ECOMMERCE as ARCH_ECOMMERCE,
    LOCAL as ARCH_LOCAL,
    SAAS as ARCH_SAAS,
    SERVICE as ARCH_SERVICE,
    resolve as resolve_archetype,
)
from orchestrator.core.clock import today_iso
from orchestrator.schemas.research import CompetitorProfile, DynamicParameterTaxonomy

_MAX_MINOR_ATTRIBUTES = 25

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
    user_intent = merchant_context.get("user_intent", "")
    capabilities = merchant_context.get("marketing_capabilities", [])

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
                + (f"User Strategic Intent: {user_intent}\n" if user_intent else "")
                + (f"Target Capabilities: {', '.join(capabilities)}\n" if capabilities else "")
                + f"Campaign Type: {campaign_type or 'Growth & Performance'}\n"
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


REVISE_TAXONOMY_PROMPT = """\
You are auditing a competitive evaluation framework against evidence gathered after it was \
written. The framework was drafted from the merchant's brief alone, before any competitor had \
been looked at, so it may name parameters this market does not actually use, and it may be \
missing the ones every rival competes on.

Rewrite it to match the vocabulary the evidence actually uses.

RULES:
1. Critical JTBD Drivers are the 4 to 8 dealbreakers that decide who buys. Drop any driver the \
evidence shows is irrelevant in this market. Promote an attribute the competitors clearly \
compete on, even if the original framework listed it as minor or not at all.
2. Minor Attributes are 15 to 25 concrete, comparable specs or commercial terms. Prefer terms \
that literally appear across competitor pages over abstract categories.
3. Name parameters as the market names them. If competitors say "SOC 2 compliance" or \
"dedicated squad", use that, not a generic synonym.
4. Only include a parameter if the evidence suggests competitors can be compared on it. A \
parameter no page ever mentions produces an empty column and is worse than no parameter.
5. Never invent facts. You are choosing what to measure, not recording values.

{untrusted_protocol}
"""


async def revise_taxonomy_from_evidence(
    taxonomy: DynamicParameterTaxonomy,
    merchant_context: dict[str, Any],
    evidence_text: list[str],
    llm: Any = None,
    max_evidence_chars: int = 40_000,
) -> DynamicParameterTaxonomy:
    """
    Re-derives the parameter framework once real competitor evidence exists.

    The initial framework is reasoned from the merchant's brief before a single search has
    run, and `refine_parameters_from_findings` only ever adjusted the minor attributes -- the
    critical drivers were fixed for the whole run no matter what the evidence said. When those
    drivers do not match the market's vocabulary, synthesis cannot populate dynamic_attributes
    against them, which is how attribute density ends up at zero.

    Returns the original taxonomy unchanged on any failure: a worse framework is a real risk,
    so this only ever replaces one when the call succeeds and returns a usable result.
    """
    if llm is None or not evidence_text:
        return taxonomy

    from orchestrator.agents.market_research.intelligence.validation.untrusted import (
        UNTRUSTED_CONTENT_PROTOCOL,
        fence_untrusted,
    )

    corpus: list[str] = []
    spent = 0
    for i, chunk in enumerate(evidence_text):
        if not chunk:
            continue
        excerpt = chunk[:2000]
        if spent + len(excerpt) > max_evidence_chars:
            break
        corpus.append(fence_untrusted(excerpt, url="", index=i))
        spent += len(excerpt)
    if not corpus:
        return taxonomy

    try:
        structured_llm = llm.with_structured_output(DynamicParameterTaxonomy)
        prompt = (
            f"## Market\n"
            f"{merchant_context.get('product_name', 'Product')} in "
            f"{merchant_context.get('category', 'General')}\n\n"
            f"## Current Framework (drafted before any evidence)\n"
            f"Critical JTBD Drivers: {', '.join(taxonomy.critical_jtbd_drivers)}\n"
            f"Minor Attributes: {', '.join(taxonomy.minor_attributes)}\n\n"
            f"## Evidence Gathered From Competitors\n" + "\n\n".join(corpus) + "\n\n"
            f"Return the corrected framework."
        )
        revised = await structured_llm.ainvoke([
            {
                "role": "system",
                "content": REVISE_TAXONOMY_PROMPT.format(
                    untrusted_protocol=UNTRUSTED_CONTENT_PROTOCOL
                ),
            },
            {"role": "user", "content": prompt},
        ])
        validated = (
            revised
            if isinstance(revised, DynamicParameterTaxonomy)
            else DynamicParameterTaxonomy.model_validate(revised)
        )

        drivers = [d.strip() for d in validated.critical_jtbd_drivers if d and d.strip()]
        minors = [m.strip() for m in validated.minor_attributes if m and m.strip()]
        # Too thin to be an improvement: keep what we had rather than degrade the framework.
        if len(drivers) < 4 or len(minors) < 5:
            logger.warning(
                "Taxonomy revision returned %d drivers / %d attributes; keeping the original",
                len(drivers),
                len(minors),
            )
            return taxonomy

        validated.critical_jtbd_drivers = drivers[:8]
        validated.minor_attributes = minors[:_MAX_MINOR_ATTRIBUTES]
        return validated
    except Exception as exc:
        logger.warning("Taxonomy revision failed, keeping the original framework: %s", exc)
        return taxonomy


def refine_parameters_from_findings(
    taxonomy: DynamicParameterTaxonomy,
    extracted_text: list[str],
) -> DynamicParameterTaxonomy:
    """
    Dynamically refines parameters based on observations mined from crawled web pages.
    Parses specification tables, technical bullet points, and key-value pairs without hardcoded product lists.
    """
    original_minor = list(taxonomy.minor_attributes)
    existing_keys = {_param_key(a) for a in original_minor}
    stopwords = {
        "parameter", "specification", "attribute", "feature", "name", "metric",
        "note", "warning", "tip", "source", "http", "https",
    }

    def _candidate(raw: str) -> str | None:
        cleaned = re.sub(r"\s+", "_", raw.strip().lower())
        if len(cleaned) < 4 or cleaned in stopwords:
            return None
        # Page furniture, not product attributes: opening-hours tables, comment bylines
        # ("tungnt620 9 months ago"), dated rows. Real attribute names carry no digits.
        if any(ch.isdigit() for ch in cleaned) or _CALENDAR_RE.search(cleaned):
            return None
        return cleaned

    # Document frequency: an attribute is kept only when at least two separate pages use it.
    # A single page's table rows are that page's layout; a label several sites share is how
    # the market describes the product.
    doc_freq: dict[str, int] = {}
    display: dict[str, str] = {}
    for text in extracted_text:
        found: set[str] = set()
        # 1. Specification table rows: | Spec Name | Value |
        for raw in re.findall(r"\|\s*([A-Za-z0-9\s]{3,24})\s*\|\s*[^\|\n]{2,50}\s*\|", text):
            if (c := _candidate(raw)) is not None:
                found.add(c)
        # 2. Key-value bullets: - Battery: 500mAh
        for raw, _ in re.findall(r"(?:^|\n)[\-\*•]\s*([A-Za-z0-9\s]{3,20}):\s*([^\n]{2,50})", text):
            if (c := _candidate(raw)) is not None:
                found.add(c)
        for c in found:
            key = _param_key(c)
            if key in existing_keys:
                continue
            display.setdefault(key, c)
            doc_freq[key] = doc_freq.get(key, 0) + 1

    observed = [
        display[k]
        for k, n in sorted(doc_freq.items(), key=lambda kv: -kv[1])
        if n >= _MIN_ATTRIBUTE_DOC_FREQ
    ]

    # Attributes observed in the market outrank the ones the LLM guessed from the brief alone,
    # so they are placed first and the guesses fill what is left. Appending them instead made
    # this function a no-op whenever the initial taxonomy already filled the cap, which is the
    # normal case: the guesses survived every round and nothing observed ever got in.
    merged = observed[:_MAX_MINOR_ATTRIBUTES]
    for attr in original_minor:
        if len(merged) >= _MAX_MINOR_ATTRIBUTES:
            break
        merged.append(attr)

    return DynamicParameterTaxonomy(
        critical_jtbd_drivers=taxonomy.critical_jtbd_drivers,
        minor_attributes=merged,
    )


_MIN_ATTRIBUTE_DOC_FREQ = 2

# Substring match on purpose: scraped tables glue cells into tokens like "ttuesday".
_CALENDAR_RE = re.compile(
    r"monday|tuesday|wednesday|thursday|friday|saturday|sunday|january|february|march|april"
    r"|june|july|august|september|october|november|december|_ago$|^ago_|yesterday|today"
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
