"""
Query interpreter: extracts structured merchant context from free-form user text.

Unlike autofill (which reads documents), this service handles vague goal-oriented
statements like "i want to attract more customers" by actively inferring the most
likely product context — it is allowed to make confident guesses where autofill
is constrained to only what documents explicitly state.

The same AutofillFields schema is returned so the frontend has one unified type.
"""

from __future__ import annotations

import logging
from typing import Any

from orchestrator.schemas.api import AutofillFields

logger = logging.getLogger(__name__)

INTERPRET_SYSTEM_PROMPT = """\
You extract a marketing campaign brief from a user's free-form text.
The user may have written anything: a polished product description, a vague goal
statement, a half-formed idea, or a mix of all three.

Your job is to fill in the following fields as best you can:

- product_name: the specific product, app, service, or brand being marketed.
  CRITICAL: If the text is purely a goal ("i want to grow my connections",
  "help me attract more customers") with NO product name, set product_name to null.
  Do NOT use the goal sentence as the product name. Do NOT invent brand names.
  Only use a name that appears in or can be directly inferred from the text.

- category: the industry or product category. Examples: "B2B SaaS CRM",
  "E-commerce Fashion", "Mobile Fitness App", "Local Restaurant". Infer confidently
  from any context clues (mentions of software, pricing, target customers, etc.).
  If truly unknown, set to null.

- primary_value_prop: what the product offers / why customers should choose it.
  Paraphrase from the user's words if needed. If not inferable, null.

- goal: the user's strategic objective. Extract or paraphrase the goal sentence.
  E.g. "increase customer acquisition", "enter new market", "beat competitor X".

- known_competitors: any competitor names the user mentions. Empty list if none.

- existing_customer_profiles: any target customer types mentioned. Empty list if none.

- price_usd: only if an explicit USD price is stated. Otherwise null.

Always return something useful for goal — it is the most reliably present field.
For product_name, returning null is correct and honest when no product is named.
"""


async def interpret_query(text: str, llm: Any = None) -> AutofillFields:
    """
    Interprets free-form user text into a structured merchant context.

    Raises AutofillUnavailableError when no LLM is configured.
    """
    from orchestrator.services.autofill import AutofillUnavailableError
    from orchestrator.core.config import get_settings

    settings = get_settings()
    text = text[: settings.max_autofill_chars]

    if llm is None:
        from orchestrator.core.llm import LLMConfigurationError, build_chat_model

        try:
            llm = build_chat_model(fast=True)
        except LLMConfigurationError as exc:
            raise AutofillUnavailableError(str(exc)) from exc

    try:
        result = await llm.with_structured_output(AutofillFields).ainvoke([
            {"role": "system", "content": INTERPRET_SYSTEM_PROMPT},
            {"role": "user", "content": f"User text:\n\n{text}"},
        ])
    except Exception as exc:
        logger.warning("Query interpreter LLM call failed: %s", exc)
        raise AutofillUnavailableError(
            f"Query interpretation failed ({type(exc).__name__}). Check OPENAI_API_KEY."
        ) from exc

    return result if isinstance(result, AutofillFields) else AutofillFields.model_validate(result)
