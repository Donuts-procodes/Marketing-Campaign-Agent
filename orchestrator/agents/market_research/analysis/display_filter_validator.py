"""
Filter-Validator for dashboard display data.

Audits competitors and findings selected to be displayed on the dashboard, verifies whether
any critical fields are incorrect or missing, and invokes an LLM repair subagent to find and fix
the data from the scraped evidence corpus before finalizing the report.

Two things let "not available" placeholders reach the dashboard: gap detection only caught empty
values and the literal string "detected", and a repair was only written back when the old value
was empty. So a competitor whose pricing had been filled in as "N/A" or "not specified" was
judged complete and shipped as-is. Placeholder text is now treated as missing everywhere -- when
deciding what needs repair, when deciding whether a repair may overwrite, and when the report is
finally swept -- and anything still unresolved is reported as null rather than as prose the UI
renders verbatim.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from pydantic import BaseModel, Field

from orchestrator.schemas.research import CompetitorProfile, SWOTReportDelta

logger = logging.getLogger(__name__)

# Values a model emits in place of admitting it did not find the data. Compared after
# lowercasing and stripping punctuation, so "N/A." and "(not available)" both match.
PLACEHOLDER_VALUES = frozenset({
    "",
    "-",
    "--",
    "n a",
    "na",
    "nil",
    "none",
    "null",
    "detected",
    "undefined",
    "not defined",
    "unknown",
    "not known",
    "not available",
    "unavailable",
    "not found",
    "no data",
    "no data available",
    "not specified",
    "unspecified",
    "not provided",
    "not disclosed",
    "not publicly disclosed",
    "not public",
    "not applicable",
    "not mentioned",
    "not stated",
    "not listed",
    "no information",
    "no information available",
    "information not available",
    "data not available",
    "missing",
    "tbd",
    "to be determined",
    "pending",
    "unclear",
    "varies",
    "pricing on request",
    "price on request",
    "contact for pricing",
    "contact us for pricing",
    "request a quote",
    "quote on request",
    "custom pricing",
    "placeholder",
    "todo",
})

_PUNCT = re.compile(r"[^a-z0-9 ]+")


def _normalize(value: str) -> str:
    """Lowercase, strip punctuation and collapse whitespace for placeholder comparison."""
    return " ".join(_PUNCT.sub(" ", value.lower()).split())


def is_placeholder(value: Any) -> bool:
    """True when a value carries no real information and must not reach the dashboard."""
    if value is None:
        return True
    if not isinstance(value, str):
        return False
    return _normalize(value) in PLACEHOLDER_VALUES


def _clean_list(values: list[str]) -> list[str]:
    """Drop placeholder entries from a display list, preserving order."""
    return [v for v in values if isinstance(v, str) and not is_placeholder(v)]


def sanitize_competitor(c: CompetitorProfile) -> list[str]:
    """
    Strip placeholder text out of a profile in place so the dashboard sees null, not prose.

    Returns the names of the fields that were blanked, for diagnostics.
    """
    blanked: list[str] = []

    for field in ("pricing_model", "rating", "founded", "as_of"):
        if getattr(c, field, None) is not None and is_placeholder(getattr(c, field)):
            setattr(c, field, None)
            blanked.append(field)

    if is_placeholder(c.relevance_reason):
        c.relevance_reason = ""

    for field in (
        "core_claims",
        "weaknesses_mined",
        "strengths_mined",
        "ad_hooks",
        "milestones",
        "factual_evidence",
    ):
        original = getattr(c, field)
        cleaned = _clean_list(original)
        if len(cleaned) != len(original):
            setattr(c, field, cleaned)
            blanked.append(field)

    for key, value in list(c.dynamic_attributes.items()):
        if is_placeholder(value):
            c.dynamic_attributes[key] = None

    return blanked


DISPLAY_REPAIR_PROMPT = """\
You are an expert market intelligence data auditor and repair subagent.
Your goal is to inspect competitors selected for the final dashboard report, verify whether the
displayed data is accurate, and FILL IN any missing or incorrect data using the provided evidence corpus.

Each competitor lists the exact fields that are missing in its "gaps" array. Repair every one you
can support from the evidence.

1. 'pricing_model' - find the verified price or pricing structure (e.g. "$49/mo", "Starts at
   $5,000/project", "Free tier + usage-based"). Quote concrete numbers whenever the corpus states
   them, including the plan name and billing period.
2. 'strengths_mined' - extract genuine customer praise from reviews/snippets.
3. 'weaknesses_mined' - extract verified customer complaints or product limitations.
4. 'core_claims' - extract specific factual claims from their own website copy.
5. Filter out any claim or point that belongs to a different company.

HARD RULES:
- Return only genuine, factually supported repairs grounded in the evidence corpus.
- Do NOT invent fake numbers or hallucinate URLs.
- NEVER return filler text such as "N/A", "not available", "unknown", "not specified",
  "pricing on request" or "varies". If the evidence does not support a field, OMIT that field
  entirely and name it in 'unresolved' - a blank field is handled correctly downstream, while
  filler text is shown to the user verbatim and is worse than nothing.
"""


class CompetitorDisplayRepair(BaseModel):
    brand_name: str = Field(..., description="Brand name of the competitor being repaired")
    pricing_model: str | None = Field(default=None, description="Found or corrected pricing model")
    repaired_claims: list[str] = Field(default_factory=list, description="Specific factual claims extracted from evidence")
    repaired_strengths: list[str] = Field(default_factory=list, description="Customer praise/strengths extracted from evidence")
    repaired_weaknesses: list[str] = Field(default_factory=list, description="Customer complaints/weaknesses extracted from evidence")
    unresolved: list[str] = Field(
        default_factory=list,
        description="Field names the evidence corpus genuinely does not support, left blank on purpose",
    )
    rationale: str = Field(default="", description="Summary of what was verified, found, and repaired")


class DisplayRepairVerdict(BaseModel):
    repairs: list[CompetitorDisplayRepair] = Field(default_factory=list)


def competitor_gaps(c: CompetitorProfile) -> list[str]:
    """Display fields of one competitor that hold nothing usable."""
    gaps = []
    if is_placeholder(c.pricing_model):
        gaps.append("pricing_model")
    if not _clean_list(c.weaknesses_mined):
        gaps.append("weaknesses_mined")
    if not _clean_list(c.strengths_mined):
        gaps.append("strengths_mined")
    if not _clean_list(c.core_claims):
        gaps.append("core_claims")
    return gaps


def inspect_display_candidates(competitors: list[CompetitorProfile]) -> list[dict[str, Any]]:
    """Identifies which competitors have missing or incomplete data needing repair."""
    candidates_with_gaps = []
    for c in competitors:
        candidates_with_gaps.append({
            "brand_name": c.brand_name,
            "product_name": c.product_name,
            "pricing_model": c.pricing_model,
            "gaps": competitor_gaps(c),
            "claims_count": len(c.core_claims),
            "strengths_count": len(c.strengths_mined),
            "weaknesses_count": len(c.weaknesses_mined),
        })
    return candidates_with_gaps


def _relevant_passages(
    corpus: list[str],
    needs_repair: list[dict[str, Any]],
    limit: int = 30,
) -> list[str]:
    """Corpus sections naming any competitor still needing repair, by brand or product name."""
    needed_names = set()
    for c in needs_repair:
        for name in (c.get("brand_name"), c.get("product_name")):
            if name and len(name) > 2:
                needed_names.add(name.lower())

    passages: list[str] = []
    for text in corpus:
        if not text:
            continue
        text_lower = text.lower()
        if any(name in text_lower for name in needed_names):
            passages.append(text[:2500])
        if len(passages) >= limit:
            break

    if not passages:
        passages = [t[:1500] for t in corpus[:10] if t]
    return passages


async def _request_repairs(
    llm: Any,
    needs_repair: list[dict[str, Any]],
    passages: list[str],
) -> DisplayRepairVerdict:
    verdict = await llm.with_structured_output(DisplayRepairVerdict).ainvoke([
        {"role": "system", "content": DISPLAY_REPAIR_PROMPT},
        {
            "role": "user",
            "content": (
                f"## Competitors Needing Verification & Repair:\n"
                f"{json.dumps(needs_repair, indent=2)}\n\n"
                f"## Evidence Corpus:\n"
                f"{json.dumps(passages, ensure_ascii=False)}"
            ),
        },
    ])
    if not isinstance(verdict, DisplayRepairVerdict):
        verdict = DisplayRepairVerdict.model_validate(verdict)
    return verdict


def _apply_repairs(
    report: SWOTReportDelta,
    verdict: DisplayRepairVerdict,
    diagnostics: list[str],
) -> None:
    """Write supported repairs back onto the report, rejecting placeholder answers."""
    repair_map = {r.brand_name.strip().lower(): r for r in verdict.repairs}
    for comp in report.competitors:
        r = repair_map.get(comp.brand_name.strip().lower())
        if not r:
            continue

        fixed_fields = []
        # Overwrite whenever the current value is unusable, not only when it is empty:
        # "N/A" and "pricing on request" are exactly the cases that need replacing.
        # Prices are facts, and facts are written only by profile completion, which checks the
        # source sentence. When it searched and could not verify one, an unquoted repair here
        # would slip an unchecked price past that check.
        price_status = comp.fact_status.get("pricing_model")
        price_locked = price_status is not None and price_status.status in ("not_stated", "removed")
        if (
            not price_locked
            and r.pricing_model and not is_placeholder(r.pricing_model) and is_placeholder(comp.pricing_model)
        ):
            comp.pricing_model = r.pricing_model.strip()
            fixed_fields.append("pricing")

        for src, attr, label in (
            (r.repaired_claims, "core_claims", "claims"),
            (r.repaired_strengths, "strengths_mined", "strengths"),
            (r.repaired_weaknesses, "weaknesses_mined", "weaknesses"),
        ):
            existing = set(getattr(comp, attr))
            new_items = []
            for value in _clean_list(src):
                value = value.strip()
                if value and value not in existing:
                    new_items.append(value)
                    existing.add(value)
            if new_items:
                getattr(comp, attr).extend(new_items[:4])
                fixed_fields.append(f"{len(new_items[:4])} {label}")

        if fixed_fields:
            diagnostics.append(
                f"[DATA_REPAIR] Subagent repaired {comp.brand_name}: "
                f"fixed {', '.join(fixed_fields)}. ({r.rationale or 'Grounded from evidence corpus'})"
            )


async def filter_validate_and_repair_display_data(
    report: SWOTReportDelta,
    corpus: list[str],
    llm: Any,
    max_passes: int = 2,
) -> tuple[SWOTReportDelta, list[str]]:
    """
    FilterValidator: verifies selected display data for correctness & completeness,
    then uses LLM subagent reasoning to find and fix missing/incorrect items.

    Runs up to `max_passes` repair rounds, each round asking only about the gaps the previous
    round failed to close and widening the evidence it is shown. Whatever is still missing at
    the end is blanked, so the dashboard renders its own empty state instead of model filler.
    """
    if not report.competitors:
        return report, []

    diagnostics: list[str] = []

    # Scrub placeholders earlier phases wrote in before judging completeness, so a competitor
    # carrying "not available" is correctly seen as missing data rather than as complete.
    pre_blanked = {c.brand_name: sanitize_competitor(c) for c in report.competitors}
    scrubbed = {name: fields for name, fields in pre_blanked.items() if fields}
    if scrubbed:
        diagnostics.append(
            "[FILTER_VALIDATOR] Cleared placeholder values before audit: "
            + "; ".join(f"{name} ({', '.join(fields)})" for name, fields in scrubbed.items())
        )

    if llm is None:
        return report, diagnostics

    needs_repair = [c for c in inspect_display_candidates(report.competitors) if c["gaps"]]
    if not needs_repair:
        diagnostics.append("[FILTER_VALIDATOR] All displayed competitor data verified complete and valid.")
        return report, diagnostics

    diagnostics.append(
        f"[FILTER_VALIDATOR] Inspected {len(report.competitors)} display competitors; "
        f"identified gaps in {len(needs_repair)}: "
        + ", ".join(f"{c['brand_name']} [{', '.join(c['gaps'])}]" for c in needs_repair)
    )

    for attempt in range(1, max_passes + 1):
        passages = _relevant_passages(corpus, needs_repair, limit=30 if attempt == 1 else 45)
        try:
            verdict = await _request_repairs(llm, needs_repair, passages)
        except Exception as exc:
            logger.warning("Display FilterValidator repair LLM call failed: %s", exc)
            diagnostics.append(f"[FILTER_VALIDATOR] Repair pass {attempt} skipped ({type(exc).__name__}).")
            break

        _apply_repairs(report, verdict, diagnostics)

        # Gaps the model itself declared unsupported are not worth another pass.
        declared_unresolved = {
            r.brand_name.strip().lower(): set(r.unresolved) for r in verdict.repairs
        }
        remaining = []
        for c in report.competitors:
            unresolved = declared_unresolved.get(c.brand_name.strip().lower(), set())
            gaps = [g for g in competitor_gaps(c) if g not in unresolved]
            if gaps:
                remaining.append({
                    "brand_name": c.brand_name,
                    "product_name": c.product_name,
                    "pricing_model": c.pricing_model,
                    "gaps": gaps,
                })
        if not remaining:
            break
        needs_repair = remaining

    # Final sweep: reject any filler the repair pass slipped in, and record what is still open
    # so the gap is visible in diagnostics instead of invented on the dashboard.
    for c in report.competitors:
        sanitize_competitor(c)

    still_missing = [
        (c.brand_name, gaps) for c in report.competitors if (gaps := competitor_gaps(c))
    ]
    if still_missing:
        diagnostics.append(
            "[FILTER_VALIDATOR] Unresolved after repair (left blank, not filled with placeholders): "
            + "; ".join(f"{name} [{', '.join(gaps)}]" for name, gaps in still_missing)
        )
    else:
        diagnostics.append("[FILTER_VALIDATOR] All display gaps closed from evidence corpus.")

    return report, diagnostics
