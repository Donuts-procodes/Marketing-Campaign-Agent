"""
Campaign archetype classification.

The intake form collects only product name, category, value prop, goal, price and
competitors — it deliberately has no campaign-type selector. The archetype fields that
drive every downstream adaptation (pricing terminology, complaint venues, parameter
taxonomy, peer-scale anchoring) are inferred here instead, by the model, from whatever
context the merchant supplied.

Only absent fields are filled: anything the caller already set is authoritative and is
never overwritten.
"""

from __future__ import annotations

import logging
from typing import Any

from orchestrator.core.clock import today_iso
from orchestrator.schemas.research import CampaignClassification

logger = logging.getLogger(__name__)

CLASSIFIER_SYSTEM_PROMPT = """\
You classify a marketing campaign from the merchant's own context, so downstream research \
can adapt its search strategy to the right kind of business.

Infer each field from the evidence given. Use the vocabulary in the field descriptions when \
it fits; coin a short snake_case label when the business is a kind the examples do not cover. \
Never force a bad fit.

- business_model: how this business actually makes money, not what it sells.
- campaign_type: what THIS campaign is trying to achieve. Read the stated goal first.
- price_model: how the customer is charged. Infer from the price and category when unstated \
(e.g. a five-figure figure for an agency implies fixed_project or retainer, not a one-time SKU).
- target_geography: only when the context states or clearly implies one; otherwise return "".
- rationale: one sentence naming the specific context that drove your answer.

Base every field on the provided context. Do not invent facts about the merchant.
"""

# Keyword fallbacks, used only when no LLM is available. Ordered: first match wins.
_BUSINESS_MODEL_RULES: tuple[tuple[tuple[str, ...], str], ...] = (
    (("dental", "clinic", "salon", "restaurant", "hvac", "plumb", "roofing", "contractor",
      "realtor", "local service", "law firm", "medical practice"), "local_service"),
    (("agency", "consulting", "consultancy", "studio", "development services", "dev shop",
      "software house", "it services", "freelance"), "professional_services"),
    (("course", "coaching", "creator", "membership", "mastermind", "infoproduct", "newsletter"),
     "creator_infoproduct"),
    (("marketplace", "two-sided", "platform connecting"), "marketplace"),
    (("ecommerce", "e-commerce", "d2c", "dtc", "apparel", "skincare", "cosmetic", "supplement",
      "beverage", "retail", "consumer goods", "merch"), "d2c_ecommerce"),
    (("mobile app", "ios app", "android app"), "mobile_app"),
    (("saas", "software", "platform", "api", "cloud", "dashboard", "b2b"), "b2b_saas"),
)

_CAMPAIGN_TYPE_RULES: tuple[tuple[tuple[str, ...], str], ...] = (
    (("take share", "switch from", "competitor takeover", "win against", "displace"),
     "competitor_takeover"),
    (("launch", "introduce", "new product", "go to market", "go-to-market"), "product_launch"),
    (("rebrand", "reposition", "refresh the brand"), "rebrand"),
    (("retention", "churn", "win back", "winback", "renew"), "retention"),
    (("sell", "sales", "revenue", "conversion", "roas", "purchase"), "ecommerce_sales"),
    (("lead", "demo", "booking", "enquiry", "inquiry", "consultation", "pipeline"), "lead_gen"),
    (("awareness", "brand"), "brand_launch"),
)

#: Explicit charging language only. Deliberately excludes what the business *builds*
#: ("custom SaaS builds" is an agency charging per project, not a subscription).
_PRICE_MODEL_RULES: tuple[tuple[tuple[str, ...], str], ...] = (
    (("per hour", "hourly rate", "/hr", "per-hour"), "hourly_rate"),
    (("retainer",), "retainer"),
    (("per project", "fixed price", "fixed-price", "project-based", "statement of work"),
     "fixed_project"),
    (("per month", "monthly subscription", "/mo", "subscription", "per seat", "per user"),
     "monthly_subscription"),
    (("usage-based", "per request", "metered", "pay as you go", "pay-as-you-go"), "usage_based"),
    (("free quote", "custom pricing", "request a quote", "contact sales"), "free_quote"),
)

#: How each business model charges, when nothing in the text says so outright.
_PRICE_MODEL_BY_BUSINESS_MODEL: dict[str, str] = {
    "b2b_saas": "monthly_subscription",
    "d2c_ecommerce": "one_time",
    "marketplace": "usage_based",
    "creator_infoproduct": "one_time",
    "mobile_app": "monthly_subscription",
}


def _context_corpus(merchant_context: dict[str, Any]) -> str:
    parts = [
        str(merchant_context.get("category", "")),
        str(merchant_context.get("product_name", "")),
        str(merchant_context.get("primary_value_prop", "")),
        str(merchant_context.get("goal", "")),
        " ".join(str(p) for p in merchant_context.get("existing_customer_profiles", []) or []),
        str(merchant_context.get("dossier", ""))[:4000],
    ]
    return " ".join(parts).lower()


def _first_match(corpus: str, rules: tuple[tuple[tuple[str, ...], str], ...]) -> str:
    for keywords, label in rules:
        if any(kw in corpus for kw in keywords):
            return label
    return ""


def classify_heuristically(merchant_context: dict[str, Any]) -> CampaignClassification:
    """Keyword-based classification used when no LLM is configured."""
    corpus = _context_corpus(merchant_context)
    business_model = _first_match(corpus, _BUSINESS_MODEL_RULES)

    price_model = _first_match(corpus, _PRICE_MODEL_RULES)
    if not price_model:
        price = merchant_context.get("price_usd")
        if business_model in ("professional_services", "local_service"):
            # Service work: a large headline figure is a project fee, a small one a visit/rate.
            if isinstance(price, (int, float)):
                price_model = "fixed_project" if price >= 5000 else "hourly_rate"
            else:
                price_model = "free_quote"
        else:
            price_model = _PRICE_MODEL_BY_BUSINESS_MODEL.get(business_model, "")
        if not price_model and isinstance(price, (int, float)):
            price_model = "fixed_project" if price >= 5000 else "one_time"

    return CampaignClassification(
        business_model=business_model,
        campaign_type=_first_match(corpus, _CAMPAIGN_TYPE_RULES) or "lead_gen",
        price_model=price_model,
        target_geography="",
        rationale="Heuristic keyword classification (no LLM available).",
    )


async def classify_campaign_context(
    merchant_context: dict[str, Any],
    llm: Any = None,
) -> tuple[dict[str, Any], CampaignClassification, list[str]]:
    """
    Infers the campaign archetype and returns (enriched_context, classification, filled_fields).

    Fields the caller already supplied are preserved verbatim; only blanks are filled. The
    returned context is a copy — the caller's dict is not mutated.
    """
    enriched = dict(merchant_context)
    target_fields = ("business_model", "campaign_type", "price_model", "target_geography")
    missing = [f for f in target_fields if not str(enriched.get(f) or "").strip()]

    if not missing:
        return enriched, CampaignClassification(
            business_model=str(enriched.get("business_model") or ""),
            campaign_type=str(enriched.get("campaign_type") or ""),
            price_model=str(enriched.get("price_model") or ""),
            target_geography=str(enriched.get("target_geography") or ""),
            rationale="All archetype fields supplied by the caller.",
        ), []

    classification: CampaignClassification | None = None
    if llm is not None:
        try:
            price = merchant_context.get("price_usd")
            dossier = str(merchant_context.get("dossier") or "")
            prompt = (
                f"Today's date: {today_iso()} (use this for any timing or seasonality judgement, "
                f"not your training data).\n\n"
                f"Offering / Brand: {merchant_context.get('product_name', '') or 'Not stated'}\n"
                f"Category / Market: {merchant_context.get('category', '') or 'Not stated'}\n"
                f"Primary Value Proposition: {merchant_context.get('primary_value_prop', '') or 'Not stated'}\n"
                f"Campaign Goal: {merchant_context.get('goal', '') or 'Not stated'}\n"
                f"Stated Price (USD): {price if price is not None else 'Not stated'}\n"
                f"Known Competitors: "
                f"{', '.join(merchant_context.get('known_competitors', []) or []) or 'None given'}\n"
                f"Target Customer Profiles: "
                f"{', '.join(merchant_context.get('existing_customer_profiles', []) or []) or 'Not stated'}\n"
                f"Dossier / Brief Notes:\n{dossier[:3000] if dossier else 'None'}\n\n"
                f"Classify this campaign."
            )
            result = await llm.with_structured_output(CampaignClassification).ainvoke([
                {"role": "system", "content": CLASSIFIER_SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ])
            classification = (
                result if isinstance(result, CampaignClassification)
                else CampaignClassification.model_validate(result)
            )
        except Exception as exc:
            logger.warning("Campaign classification LLM call failed, using heuristics: %s", exc)

    if classification is None:
        classification = classify_heuristically(merchant_context)

    filled: list[str] = []
    for field in missing:
        value = str(getattr(classification, field, "") or "").strip()
        if value:
            enriched[field] = value
            filled.append(field)

    return enriched, classification, filled
