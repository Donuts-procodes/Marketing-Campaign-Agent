"""
Autofill: reads the campaign form fields out of uploaded documents (briefs, pitch decks).

Only what the documents state is returned. After the LLM extraction, names and prices are
checked against the document text and dropped when they do not appear in it.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from orchestrator.core.config import get_settings
from orchestrator.schemas.api import AutofillFields, BYOKConfig

logger = logging.getLogger(__name__)


class AutofillUnavailableError(Exception):
    """Raised when no working LLM is available to read the documents."""


AUTOFILL_SYSTEM_PROMPT = """\
You fill a marketing campaign intake form from the merchant's own documents.
Extract ONLY what the documents explicitly state about the merchant's product.
- If a field is not stated, leave it null (or an empty list). Never guess or invent.
- product_name: the merchant's product or brand name exactly as written.
- known_competitors: only competitor names that appear in the documents.
- price_usd: only if a USD price for the merchant's product is written; otherwise null.
- primary_value_prop and goal: stay close to the documents' own wording.
- target_geography: specific target city, state, country, or service region if explicitly stated (e.g. 'Delhi', 'Austin, TX', 'United States', 'Global').
"""


def _verify(fields: AutofillFields, text: str) -> AutofillFields:
    """Drops names and prices the documents do not actually contain."""
    lower = text.lower()
    clean_text = re.sub(r"[^\w\s]", " ", lower)
    if fields.product_name:
        prod_lower = fields.product_name.lower()
        clean_prod = re.sub(r"[^\w\s]", " ", prod_lower).strip()
        tokens = [t for t in clean_prod.split() if len(t) >= 3]
        if prod_lower not in lower and clean_prod not in clean_text and not (tokens and all(t in clean_text for t in tokens)):
            fields.product_name = None

    verified_competitors = []
    for c in fields.known_competitors:
        if not c.strip():
            continue
        c_lower = c.strip().lower()
        clean_c = re.sub(r"[^\w\s]", " ", c_lower).strip()
        tokens = [t for t in clean_c.split() if len(t) >= 3]
        if c_lower in lower or clean_c in clean_text or (tokens and all(t in clean_text for t in tokens)):
            verified_competitors.append(c.strip())
    fields.known_competitors = verified_competitors[:20]

    fields.existing_customer_profiles = [p for p in fields.existing_customer_profiles if p.strip()][:20]
    if fields.price_usd is not None:
        digits = re.sub(r"(?<=\d),(?=\d)", "", text)
        price = fields.price_usd
        forms = {f"{price:.2f}", f"{price:g}", str(int(price)) if price == int(price) else f"{price:g}"}
        if not any(re.search(rf"(?<![\d.]){re.escape(f)}(?![\d])", digits) for f in forms):
            fields.price_usd = None
    return fields


def _heuristic_extract_from_text(text: str) -> AutofillFields:
    """Best-effort heuristic parser for dossiers when LLM is unavailable or fails."""
    fields = AutofillFields()
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return fields

    # Attempt to extract product/brand name from first lines or headers
    for line in lines[:10]:
        clean = re.sub(r"^[#\*\-=\s]+", "", line).strip()
        if not clean or clean.lower().startswith("sheet:") or len(clean) > 80:
            continue
        # Check brand patterns like "Brand: XYZ" or "Product: XYZ" or "Dossier: XYZ"
        match_brand = re.search(r"(?:brand|product|company|client|dossier)\s*[:\-–]\s*([A-Za-z0-9\s&'\.]+)", clean, re.I)
        if match_brand:
            fields.product_name = match_brand.group(1).strip()
            break
        # Or a standalone capitalized title like "Aurelius Footwear Dossier"
        if not fields.product_name and 3 <= len(clean.split()) <= 6:
            fields.product_name = clean
            break

    # Target geography
    geo_patterns = [
        r"(?:geography|target market|region|country|territory|market)\s*[:\-–]\s*([A-Za-z\s,]+)",
        r"\b(India|United States|USA|UK|Europe|Australia|Canada|Global)\b"
    ]
    for pat in geo_patterns:
        m = re.search(pat, text, re.I)
        if m:
            fields.target_geography = m.group(1).strip()
            break

    # Value proposition / Goal
    goal_patterns = [
        r"(?:goal|objective|mission|value prop|value proposition|positioning)\s*[:\-–]\s*([^\n\r]+)",
        r"(?:overview|summary)\s*[:\-–]\s*([^\n\r]+)"
    ]
    for pat in goal_patterns:
        m = re.search(pat, text, re.I)
        if m:
            fields.goal = m.group(1).strip()
            fields.primary_value_prop = fields.goal
            break

    if not fields.goal and len(lines) > 1:
        # Fallback to first non-title paragraph
        for line in lines[1:5]:
            if len(line) > 30 and not line.startswith("#"):
                fields.goal = line[:300].strip()
                fields.primary_value_prop = fields.goal
                break

    # Competitors
    comp_match = re.search(r"(?:competitors|rivals|competing brands)\s*[:\-–]\s*([^\n\r]+)", text, re.I)
    if comp_match:
        comps = [c.strip() for c in re.split(r"[,;|]", comp_match.group(1)) if c.strip()]
        fields.known_competitors = comps[:10]

    return fields


async def autofill_from_text(text: str, llm: Any = None, byok_config: BYOKConfig | None = None) -> AutofillFields:
    settings = get_settings()
    text = text[: settings.max_autofill_chars]
    if llm is None:
        from orchestrator.core.llm import LLMConfigurationError, build_chat_model

        try:
            llm = build_chat_model(byok=byok_config, fast=True)
        except LLMConfigurationError as exc:
            raise AutofillUnavailableError(str(exc)) from exc
    try:
        result = await llm.with_structured_output(AutofillFields).ainvoke([
            {"role": "system", "content": AUTOFILL_SYSTEM_PROMPT},
            {"role": "user", "content": f"Documents:\n\n{text}"},
        ])
    except Exception as exc:
        logger.warning("Autofill LLM call failed: %s", exc)
        raise AutofillUnavailableError(
            f"The AI model could not read the documents ({type(exc).__name__}). Check OPENAI_API_KEY."
        ) from exc
    fields = result if isinstance(result, AutofillFields) else AutofillFields.model_validate(result)
    return _verify(fields, text)


def filled_field_names(fields: AutofillFields) -> list[str]:
    return [name for name, value in fields.model_dump().items() if value not in (None, "", [])]
