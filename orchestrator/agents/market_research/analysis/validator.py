"""
Adversarial validator: the last check before a report reaches the dashboard.

The grounding gate proves each statement's words appear in some fetched page. It cannot tell
whether that page is about this competitor, whether a "complaint" is a customer's complaint
rather than a headline, or whether a "claim" says anything at all. This critic sees every
item next to the exact passage it was grounded on and rejects the ones the passage does not
really support. It also names gaps worth one more targeted research round.

Rejections are applied deterministically by item id, so the critic can remove data but never
write any.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Literal

from pydantic import BaseModel, Field

from orchestrator.agents.market_research.analysis.grounding import build_documents, find_support_excerpt
from orchestrator.agents.market_research.analysis.scoring import PLACEHOLDER_PRICING
from orchestrator.schemas.research import SWOTReportDelta

logger = logging.getLogger(__name__)

FIELD_LABELS: dict[str, str] = {
    "core_claims": "claim on their own website",
    "weaknesses_mined": "customer complaint",
    "strengths_mined": "customer praise",
    "ad_hooks": "ad they are running",
}
GapField = Literal["pricing_model", "weaknesses_mined", "strengths_mined", "core_claims"]

# Caps the prompt: items per field per competitor, and the passage shown with each.
_MAX_ITEMS_PER_FIELD = 8
_EXCERPT_CHARS = 420


class Rejection(BaseModel):
    id: str = Field(..., description="The item id exactly as given, e.g. 'c2.weaknesses_mined.0'")
    reason: str = Field(..., description="Short reason the merchant will read, e.g. 'about a different company'")


class Gap(BaseModel):
    competitor: str = Field(..., description="Competitor name exactly as given")
    field: GapField
    reason: str = Field(default="")


class ValidatorVerdict(BaseModel):
    rejected: list[Rejection] = Field(default_factory=list)
    gaps: list[Gap] = Field(default_factory=list)


VALIDATOR_PROMPT = """\
You are a strict fact-checker reviewing a competitor report before a business owner sees it. \
You are adversarial: when in doubt, reject. You never add or rewrite anything — you only \
reject items and name gaps.

Each item below is shown with the passage of source text it was matched to. REJECT an item when:
- the passage is about a different company than the competitor it is filed under;
- a "customer complaint" or "customer praise" is not a customer's opinion — e.g. it is the \
company's own marketing, a headline, a job ad, an article teaser, or the author's summary;
- a "claim on their own website" is generic filler with no specific information \
("we deliver quality solutions", "your trusted partner");
- an "ad they are running" is not ad or campaign copy for that competitor;
- a price is not that competitor's price for its main offering, or the passage does not state it;
- the passage does not actually say what the item says (meaning changed, negated, or exaggerated);
- there is no passage at all.

Then list GAPS: for each competitor, a missing field the merchant would clearly need (usually \
pricing, or customer complaints/praise when none were found) that a targeted web search could \
plausibly fill. Do not list a gap for data that is simply unpublished, e.g. agencies that only \
quote on request.

Return only the rejected item ids (with a short reason) and the gaps.
"""


def collect_items(
    report: SWOTReportDelta, corpus: list[str]
) -> tuple[list[dict[str, Any]], dict[str, tuple[int, str, int | None]]]:
    """
    Every reviewable item with its grounding passage, plus an id -> (competitor index, field,
    item index) map used to apply rejections. A price uses item index None.
    """
    documents = build_documents(corpus)
    texts = [t for t in corpus if t]

    def excerpt(statement: str) -> str | None:
        return find_support_excerpt(statement, texts, width=_EXCERPT_CHARS, documents=documents)

    payload: list[dict[str, Any]] = []
    index: dict[str, tuple[int, str, int | None]] = {}
    for ci, comp in enumerate(report.competitors):
        entry: dict[str, Any] = {"competitor": comp.brand_name, "items": []}
        if comp.pricing_model and comp.pricing_model != PLACEHOLDER_PRICING:
            item_id = f"c{ci}.pricing_model"
            index[item_id] = (ci, "pricing_model", None)
            entry["items"].append({
                "id": item_id, "kind": "price", "text": comp.pricing_model,
                "passage": excerpt(comp.pricing_model.split(" ")[0]) or excerpt(comp.pricing_model),
            })
        for field, label in FIELD_LABELS.items():
            for ii, text in enumerate(getattr(comp, field)[:_MAX_ITEMS_PER_FIELD]):
                item_id = f"c{ci}.{field}.{ii}"
                index[item_id] = (ci, field, ii)
                entry["items"].append({"id": item_id, "kind": label, "text": text, "passage": excerpt(text)})
        entry["missing"] = [
            f for f, empty in (
                ("pricing_model", not comp.pricing_model or comp.pricing_model == PLACEHOLDER_PRICING),
                ("weaknesses_mined", not comp.weaknesses_mined),
                ("strengths_mined", not comp.strengths_mined),
            ) if empty
        ]
        payload.append(entry)
    return payload, index


def apply_rejections(
    report: SWOTReportDelta,
    verdict: ValidatorVerdict,
    index: dict[str, tuple[int, str, int | None]],
) -> list[str]:
    """Removes rejected items by id. Unknown ids are ignored: the critic cannot invent targets."""
    by_field: dict[tuple[int, str], set[int]] = {}
    diagnostics: list[str] = []
    for r in verdict.rejected:
        target = index.get(r.id)
        if target is None:
            continue
        ci, field, ii = target
        comp = report.competitors[ci]
        if field == "pricing_model":
            diagnostics.append(f"[VALIDATOR] Removed price for {comp.brand_name} ({comp.pricing_model}): {r.reason}")
            comp.pricing_model = None
            continue
        by_field.setdefault((ci, field), set()).add(ii)  # type: ignore[arg-type]
        diagnostics.append(
            f"[VALIDATOR] Removed {FIELD_LABELS[field]} for {comp.brand_name}: "
            f"\"{getattr(comp, field)[ii][:90]}\" — {r.reason}"
        )
    for (ci, field), drop in by_field.items():
        comp = report.competitors[ci]
        setattr(comp, field, [v for i, v in enumerate(getattr(comp, field)) if i not in drop])
    return diagnostics


async def validate_report(
    report: SWOTReportDelta,
    corpus: list[str],
    llm: Any,
) -> tuple[SWOTReportDelta, ValidatorVerdict, list[str]]:
    """
    Runs the critic and applies its rejections. On any failure the report is returned
    unchanged with an empty verdict: the deterministic grounding gate has already run.
    """
    payload, index = collect_items(report, corpus)
    if not index and not any(p["missing"] for p in payload):
        return report, ValidatorVerdict(), []
    try:
        verdict = await llm.with_structured_output(ValidatorVerdict).ainvoke([
            {"role": "system", "content": VALIDATOR_PROMPT},
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
        ])
        if not isinstance(verdict, ValidatorVerdict):
            verdict = ValidatorVerdict.model_validate(verdict)
    except Exception as exc:
        logger.warning("Validator failed; keeping the grounded report as is: %s", exc)
        return report, ValidatorVerdict(), []

    names = {c.brand_name for c in report.competitors}
    verdict.gaps = [g for g in verdict.gaps if g.competitor in names]
    diagnostics = apply_rejections(report, verdict, index)
    return report, verdict, diagnostics
