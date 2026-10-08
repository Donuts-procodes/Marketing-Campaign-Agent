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
"""


def _verify(fields: AutofillFields, text: str) -> AutofillFields:
    """Drops names and prices the documents do not actually contain."""
    lower = text.lower()
    if fields.product_name and fields.product_name.lower() not in lower:
        fields.product_name = None
    fields.known_competitors = [c for c in fields.known_competitors if c.strip() and c.lower() in lower][:20]
    fields.existing_customer_profiles = [p for p in fields.existing_customer_profiles if p.strip()][:20]
    if fields.price_usd is not None:
        digits = re.sub(r"(?<=\d),(?=\d)", "", text)
        price = fields.price_usd
        forms = {f"{price:.2f}", f"{price:g}", str(int(price)) if price == int(price) else f"{price:g}"}
        if not any(re.search(rf"(?<![\d.]){re.escape(f)}(?![\d])", digits) for f in forms):
            fields.price_usd = None
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
