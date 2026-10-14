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
import re
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

CRITICAL DIRECTIVE FILTER: The user context may contain conversational instructions to you as an AI \
(e.g. "find me competitors and strategy", "give me competitors", "help me scale", "analyze rivals"). \
These are requests for YOUR research task, NOT what the merchant sells! NEVER classify the business model \
or normalized_category as "Competitor Analysis", "Competitor Research", or "Market Strategy" unless \
the context explicitly shows the merchant is an external agency selling competitor intelligence to clients. \
If the user mentions "my saas", "my software", "my app", "my product", or "my services", identify \
the actual commercial product/service domain they sell to their customers.

- business_model: how this business actually makes money, not what it sells.
- campaign_type: what THIS campaign is trying to achieve. Read the stated goal first.
- price_model: how the customer is charged. Infer from the price and category when unstated \
(e.g. a five-figure figure for an agency implies fixed_project or retainer, not a one-time SKU).
- target_geography: only when the context states or clearly implies one; otherwise return "".
- normalized_category: if the caller's stated category or product is phrased as a conversational goal, problem statement, \
or sentence (e.g. "i want to increase my connections to attract more customers"), extract or infer a clean, concise \
2-4 word industry/service category (e.g. "B2B SaaS Platform" or "B2B Lead Generation & Networking Agency"). \
Strip all prompt commands like "find me competitors" or "give me strategy". Otherwise return "".
- normalized_product_name: if the caller's stated product name is conversational or identical to the goal sentence, \
infer a clean brand or offering title (e.g. "SaaS Platform" or "Client Acquisition Service"). Otherwise return "".
- user_intent: synthesize a clear, concise 1-2 sentence understanding of what the user specifically wants the AI engine to do \
(e.g. 'Uncover competitor lead generation methods and pricing models to increase client acquisitions and networking connections').
- marketing_capabilities: select 1 to 4 relevant marketing capabilities the user wants activated to satisfy their goal: \
['competitor_intelligence', 'lead_generation', 'pricing_analysis', 'positioning_strategy', 'ad_copywriting', 'audience_personas', 'retention_tactics'].
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


_CONVERSATIONAL_PREFIX_RE = re.compile(
    r"^(i\s+(want|need|am|wish)|we\s+(want|need|are|wish)|how\s+to|looking\s+to|help\s+me|try(ing)?\s+to|increase|grow|attract)\b",
    re.IGNORECASE,
)

_FIRST_PERSON_TERMS = {"i", "my", "we", "our", "me", "us"}
_ACTION_VERBS = {"want", "increase", "grow", "attract", "get", "need", "scale", "boost", "find", "build"}

_INTENT_CATEGORY_RULES: tuple[tuple[tuple[str, ...], str], ...] = (
    (("connection", "connect", "networking", "customer", "customers", "lead", "leads", "pipeline", "outreach", "prospect", "prospects"),
     "B2B Lead Generation & Networking Agency"),
    (("follower", "followers", "audience", "brand", "awareness", "traffic", "visitor", "visitors"),
     "Digital Marketing & Brand Agency"),
    (("sales", "conversion", "revenue", "order", "orders", "roas", "e-commerce", "ecommerce"),
     "Sales Growth & E-commerce Optimization"),
    (("hire", "recruit", "recruiting", "talent", "staffing"),
     "Recruiting & Staffing Services"),
    (("software", "code", "app", "develop", "saas", "platform"),
     "Software Development Services"),
)


def is_conversational_statement(text: str) -> bool:
    """True when text is phrased as a personal intent/goal sentence rather than an entity or category."""
    s = str(text or "").strip()
    if not s:
        return False
    if _CONVERSATIONAL_PREFIX_RE.search(s):
        return True
    words = s.split()
    low_set = {w.lower().strip(".,!?;:") for w in words}
    return (
        len(words) >= 4
        and bool(low_set & _FIRST_PERSON_TERMS)
        and bool(low_set & _ACTION_VERBS)
    )


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

    cat_raw = str(merchant_context.get("category") or "")
    prod_raw = str(merchant_context.get("product_name") or "")

    normalized_cat = ""
    normalized_prod = ""

    if is_conversational_statement(cat_raw) or is_conversational_statement(prod_raw):
        for kws, cat_label in _INTENT_CATEGORY_RULES:
            if any(kw in corpus for kw in kws):
                normalized_cat = cat_label
                break
        if not normalized_cat:
            normalized_cat = "Professional & Business Services Agency"
        if not business_model:
            business_model = "professional_services"
        normalized_prod = "Client Acquisition Service"

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

    user_intent = ""
    capabilities: list[str] = ["competitor_intelligence", "positioning_strategy"]
    goal_val = str(merchant_context.get("goal") or "")
    if any(k in corpus for k in ("lead", "connect", "customer", "prospect", "pipeline", "outreach")):
        capabilities.append("lead_generation")
    if any(k in corpus for k in ("ad", "copy", "hook", "creative", "campaign", "social")):
        capabilities.append("ad_copywriting")
    if any(k in corpus for k in ("price", "pricing", "cost", "tier", "rate", "fee")):
        capabilities.append("pricing_analysis")
    if any(k in corpus for k in ("persona", "icp", "audience", "profile", "demographic")):
        capabilities.append("audience_personas")

    # Deduplicate while preserving order
    seen: set[str] = set()
    capabilities = [c for c in capabilities if not (c in seen or seen.add(c))]

    if goal_val:
        user_intent = f"Analyze market and execute strategy to achieve: {goal_val}"
    elif normalized_cat:
        user_intent = f"Conduct competitive benchmarking and positioning for {normalized_cat}"

    return CampaignClassification(
        business_model=business_model,
        campaign_type=_first_match(corpus, _CAMPAIGN_TYPE_RULES) or "lead_gen",
        price_model=price_model,
        target_geography="",
        rationale="Heuristic keyword classification (no LLM available).",
        normalized_category=normalized_cat,
        normalized_product_name=normalized_prod,
        user_intent=user_intent,
        marketing_capabilities=capabilities,
    )


async def classify_campaign_context(
    merchant_context: dict[str, Any],
    llm: Any = None,
) -> tuple[dict[str, Any], CampaignClassification, list[str]]:
    """
    Infers the campaign archetype and returns (enriched_context, classification, filled_fields).

    Fields the caller already supplied are preserved verbatim; only blanks are filled, EXCEPT
    when category or product_name contains a conversational goal statement, in which case
    normalized_category and normalized_product_name are populated and the goal is preserved.
    The returned context is a copy — the caller's dict is not mutated.
    """
    enriched = dict(merchant_context)
    target_fields = ("business_model", "campaign_type", "price_model", "target_geography")
    missing = [f for f in target_fields if not str(enriched.get(f) or "").strip()]

    raw_cat = str(enriched.get("category") or "")
    raw_prod = str(enriched.get("product_name") or "")
    cat_is_conversational = is_conversational_statement(raw_cat)
    prod_is_conversational = is_conversational_statement(raw_prod)

    if not missing and not cat_is_conversational and not prod_is_conversational:
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

    # Disambiguate conversational goal input into clean category and product
    norm_cat = str(getattr(classification, "normalized_category", "") or "").strip()
    if not norm_cat and cat_is_conversational:
        heur = classify_heuristically(merchant_context)
        norm_cat = heur.normalized_category

    if norm_cat and (cat_is_conversational or raw_cat == raw_prod):
        if not str(enriched.get("goal") or "").strip() or enriched.get("goal") == raw_cat:
            enriched["goal"] = raw_cat
        enriched["category"] = norm_cat
        if "category" not in filled:
            filled.append("category")

    norm_prod = str(getattr(classification, "normalized_product_name", "") or "").strip()
    if not norm_prod and (prod_is_conversational or raw_prod == raw_cat):
        heur = classify_heuristically(merchant_context)
        norm_prod = heur.normalized_product_name

    if norm_prod and (prod_is_conversational or raw_prod == raw_cat):
        enriched["product_name"] = norm_prod
        if "product_name" not in filled:
            filled.append("product_name")

    if classification.user_intent:
        enriched["user_intent"] = classification.user_intent
    if classification.marketing_capabilities:
        enriched["marketing_capabilities"] = classification.marketing_capabilities

    return enriched, classification, filled
