"""
The one place that decides what kind of business the merchant is.

Query building, complaint-venue selection, peer-scale anchoring and the parameter taxonomy
all branch on business type. Each used to carry its own keyword list, and those lists had
drifted apart: a "Veterinary Clinic" matched the services list in `build_search_queries`
(asking for rates and retainers) but not the shorter one in `build_missing_data_queries`,
so the retry round asked for its MSRP.

So the matching happens once, here, and everything else keys its own config off the label
this returns. Modules keep their own data -- a complaint venue is not a search term is not a
JTBD driver -- but they no longer each decide, separately, what the merchant *is*.

The classifier (`classification.py`) fills `business_model` on every run, so `resolve()`
normally just canonicalises that. Keyword inference is the fallback for when it is absent or
the model coined a label of its own.
"""

from __future__ import annotations

from typing import Any

#: Canonical archetype labels. `OTHER` is a real answer, not a failure.
SERVICE = "service"
LOCAL = "local"
ECOMMERCE = "ecommerce"
SAAS = "saas"
CREATOR = "creator"
OTHER = "other"

ARCHETYPES = (SERVICE, LOCAL, ECOMMERCE, SAAS, CREATOR, OTHER)

#: Canonical labels the classifier emits -> archetype. Checked before keywords, because an
#: explicit classification beats guessing from a category string.
_BUSINESS_MODEL_TO_ARCHETYPE: dict[str, str] = {
    "professional_services": SERVICE,
    "agency": SERVICE,
    "consulting": SERVICE,
    "local_service": LOCAL,
    "d2c_ecommerce": ECOMMERCE,
    "ecommerce": ECOMMERCE,
    "retail": ECOMMERCE,
    "b2b_saas": SAAS,
    "saas": SAAS,
    "mobile_app": SAAS,
    "marketplace": SAAS,
    "creator_infoproduct": CREATOR,
}

#: The single keyword table. Order matters: the first archetype whose keywords appear wins,
#: so the narrower categories are checked before the broader ones ("dental clinic" is local
#: before it is a service; "software house" is a service before it is saas).
_KEYWORD_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    (LOCAL, (
        "local", "dental", "dentist", "clinic", "medical", "veterinary", "vet ", "salon",
        "restaurant", "plumb", "hvac", "roofing", "contractor", "realtor", "law firm",
        "legal", "law ", "accounting", "repair", "landscaping", "locksmith",
    )),
    (CREATOR, (
        "course", "coaching", "creator", "membership", "mastermind", "infoproduct",
        "newsletter", "community", "bootcamp",
    )),
    (ECOMMERCE, (
        "ecommerce", "e-commerce", "d2c", "dtc", "apparel", "clothing", "skincare",
        "cosmetic", "supplement", "beverage", "food", "retail", "consumer goods", "merch",
    )),
    (SERVICE, (
        "agency", "consult", "studio", "develop", "software house", "it services",
        "digital", "design", "marketing", "freelance", "web ", "services",
    )),
    (SAAS, (
        "saas", "software", "platform", "api", "cloud", "dashboard", "b2b", "app", "tech",
    )),
)


def context_corpus(merchant_context: dict[str, Any]) -> str:
    """The text archetype inference reads when no business model was classified."""
    return " ".join(
        str(merchant_context.get(field, "") or "")
        for field in ("category", "business_model", "product_name", "primary_value_prop")
    ).lower()


def resolve(merchant_context: dict[str, Any] | None = None, context_str: str | None = None) -> str:
    """
    Returns one of `ARCHETYPES`.

    Prefers the classified `business_model`; falls back to keyword inference over the
    merchant's category and value proposition. Pass `context_str` directly when the caller
    has already assembled it.
    """
    merchant_context = merchant_context or {}

    business_model = str(merchant_context.get("business_model") or "").strip().lower()
    if business_model in _BUSINESS_MODEL_TO_ARCHETYPE:
        return _BUSINESS_MODEL_TO_ARCHETYPE[business_model]

    corpus = context_str if context_str is not None else context_corpus(merchant_context)
    corpus = corpus.lower()
    # An unrecognised classifier label is still evidence; keep it in the text being matched.
    if business_model and business_model not in corpus:
        corpus = f"{business_model} {corpus}"

    for archetype, keywords in _KEYWORD_RULES:
        if any(kw in corpus for kw in keywords):
            return archetype
    return OTHER


def is_service_like(archetype: str) -> bool:
    """True for businesses that sell time and expertise rather than a unit of product."""
    return archetype in (SERVICE, LOCAL)
