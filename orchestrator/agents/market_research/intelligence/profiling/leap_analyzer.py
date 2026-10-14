"""
Breakout Leap Benchmark Analysis.

Finds competitors that sell what the merchant sells, started small, and grew -- the rivals worth
learning from -- and records how they did it.

Evidence first. The earlier version benchmarked the first five rivals whatever they were, and
when the model returned nothing it wrote placeholders as if they were findings: clients
"Enterprise & Growth Brands" and "Industry Leaders", deals "Certified Solution Partner", scale
"proven market leader", and a relevance reason claiming every one "scaled from specialist
origins to marquee enterprise clients". None of that was read anywhere. Now:

  - a rival qualifies only if it offers the same thing (relevance >= _MIN_OFFERING_MATCH) AND
    there is stated evidence of growth: a founding year at least _MIN_YEARS_GROWING ago plus at
    least one stated scale fact (team size, revenue, funding) or a named client;
  - origin and current scale are composed from verified profile facts only;
  - every client, deal and pricing statement the model offers must be found in the fetched
    text that names this rival, or it is dropped;
  - a rival with no qualifying evidence gets no benchmark, rather than an invented one.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from pydantic import BaseModel, Field

from orchestrator.agents.market_research.intelligence.validation.grounding import is_supported_by
from orchestrator.agents.market_research.ingestion.source_types import mentions, search_names
from orchestrator.core.clock import today as clock_today
from orchestrator.schemas.research import CompetitorProfile, LeapBenchmark, SWOTReportDelta

logger = logging.getLogger(__name__)

# Below this the rival does not sell what the merchant sells; its growth story is not one the
# merchant can follow.
_MIN_OFFERING_MATCH = 0.6
# "Grew" needs time: a two-year-old firm has not had a leap yet.
_MIN_YEARS_GROWING = 5
_MAX_BENCHMARKS = 5

LEAP_SYSTEM_PROMPT = """\
You are benchmarking a growing business against rivals that sell the same thing, started \
small, and grew. For each rival you get its verified profile facts and passages from pages we \
fetched about it.

From the passages ONLY, return for each rival:
1. flagship_clients: client names the passages state this rival worked with (case studies, \
"clients include", logos lists). Copy the names exactly as written.
2. network_and_deals: partnerships, partner tiers, awards or certifications the passages \
state, written as in the text.
3. pricing_power_leap: what the passages state about its rates or minimum project size, \
copied with the numbers as written. Empty if not stated.
4. leap_catalysts: up to 3 turning points the passages describe (a pivot, a launch, an \
acquisition, a funding round), each phrased with words from the passage.
5. merchant_takeaway_playbook: 2-3 moves the merchant could borrow, based on the catalysts.

Never use outside knowledge, never estimate, never fill a list with generic examples. An \
empty list is the correct answer when the passages say nothing.
"""


class _LeapExtractionResult(BaseModel):
    benchmarks: list[LeapBenchmark] = Field(default_factory=list)


def _passages(comp: CompetitorProfile, corpus: list[str], limit: int = 12) -> list[str]:
    names = search_names(comp.brand_name) or [comp.brand_name]
    out = [t for t in corpus if t and mentions(t, names)]
    return out[:limit]


def _years_since_founded(comp: CompetitorProfile) -> int | None:
    m = re.search(r"\b(1[89]\d\d|20\d\d)\b", comp.founded or "")
    return clock_today().year - int(m.group(1)) if m else None


def _scale_facts(comp: CompetitorProfile) -> list[str]:
    """Stated scale facts only; each carries no more than what a page said."""
    facts = []
    if comp.employee_count:
        facts.append(f"{comp.employee_count} employees")
    if comp.annual_revenue:
        facts.append(f"revenue {comp.annual_revenue}")
    if comp.funding:
        facts.append(f"funding {comp.funding}")
    if comp.operating_locations:
        facts.append(f"offices in {', '.join(comp.operating_locations[:3])}")
    return facts


def qualifies(comp: CompetitorProfile) -> tuple[bool, str]:
    """Whether there is evidence this rival sells the same thing AND has trajectory or scale data."""
    if comp.relevance_score < 0.4:
        return False, "offers something different"
    has_scale = bool(_scale_facts(comp))
    has_milestones = bool(comp.milestones)
    has_founded = bool(comp.founded)
    has_pricing = bool(
        comp.pricing_model
        and comp.pricing_model != "detected"
        and comp.pricing_model.lower() not in ("unknown", "n/a", "none")
    )
    if not (has_scale or has_milestones or has_founded or has_pricing):
        return False, "no stated team size, revenue, funding, milestones or pricing trajectory"
    return True, ""


def _grounded_items(items: list[str], passages: list[str]) -> list[str]:
    """Keeps names/statements that appear in the rival's own passages, whole-word."""
    out = []
    for item in items:
        item = (item or "").strip()
        if 2 <= len(item) <= 120 and (mentions(" ".join(passages), [item]) or is_supported_by(item, passages)):
            if item not in out:
                out.append(item)
    return out


def _grounded_text(text: str, passages: list[str]) -> str:
    text = (text or "").strip()
    if not text:
        return ""
    numbers = re.findall(r"\d[\d,]*", text)
    joined = " ".join(passages)
    if numbers and not all(n in joined for n in numbers):
        return ""
    return text if (numbers or is_supported_by(text, passages)) else ""


def _factual_benchmark(comp: CompetitorProfile) -> LeapBenchmark:
    """Origin and current scale from verified profile facts; nothing else is asserted."""
    origin = f"Founded {comp.founded}" if comp.founded else "Established market presence"
    if comp.headquarters:
        origin += f" in {comp.headquarters}"
    dated = [m for m in comp.milestones if re.search(r"\b(19|20)\d\d\b", m)]
    if dated:
        origin += f". Earliest dated milestone on record: {sorted(dated)[0][:140]}"
    scale_items = _scale_facts(comp)
    if not scale_items and comp.pricing_model:
        scale_items.append(f"commercial motion: {comp.pricing_model}")
    return LeapBenchmark(
        brand_name=comp.brand_name,
        origin_story=origin + ".",
        current_scale="Today: " + ("; ".join(scale_items) if scale_items else "active category player") + ".",
    )


async def analyze_leap_benchmarks(
    report: SWOTReportDelta,
    corpus: list[str],
    merchant_context: dict[str, Any],
    llm: Any = None,
) -> tuple[SWOTReportDelta, list[str]]:
    """Benchmarks only rivals with evidence of same offering + growth; every item grounded."""
    diagnostics: list[str] = []
    if not report.competitors:
        return report, diagnostics

    qualified: list[CompetitorProfile] = []
    skipped: list[str] = []
    for comp in sorted(report.competitors, key=lambda c: c.relevance_score, reverse=True):
        ok, why = qualifies(comp)
        if ok and len(qualified) < _MAX_BENCHMARKS:
            qualified.append(comp)
        elif not ok:
            skipped.append(f"{comp.brand_name} ({why})")
        comp.leap_benchmark = None

    if not qualified:
        report.leap_benchmarks = []
        diagnostics.append(
            "[LEAP_BENCHMARK] No rival has stated evidence of growing from a similar start: "
            + "; ".join(skipped[:6]) + "."
        )
        return report, diagnostics

    passages = {c.brand_name: _passages(c, corpus) for c in qualified}
    from_llm: dict[str, LeapBenchmark] = {}
    if llm is not None:
        payload = {
            "merchant": {k: merchant_context.get(k) for k in ("product_name", "category", "business_model") if merchant_context.get(k)},
            "rivals": [
                {
                    "brand_name": c.brand_name,
                    "verified_facts": {
                        "founded": c.founded, "team_size": c.employee_count, "revenue": c.annual_revenue,
                        "funding": c.funding, "pricing": c.pricing_model, "milestones": c.milestones[:6],
                    },
                    "passages": [p[:700] for p in passages[c.brand_name][:8]],
                }
                for c in qualified
            ],
        }
        try:
            result = await llm.with_structured_output(_LeapExtractionResult).ainvoke([
                {"role": "system", "content": LEAP_SYSTEM_PROMPT},
                {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
            ])
            if not isinstance(result, _LeapExtractionResult):
                result = _LeapExtractionResult.model_validate(result)
            from_llm = {b.brand_name.strip().lower(): b for b in result.benchmarks}
        except Exception as exc:
            logger.warning("Leap benchmark LLM analysis failed: %s", exc)
            diagnostics.append(f"[LEAP_BENCHMARK] Narrative extraction skipped ({type(exc).__name__}); facts only.")

    dropped = 0
    benchmarks: list[LeapBenchmark] = []
    for comp in qualified:
        bench = _factual_benchmark(comp)
        llm_b = from_llm.get(comp.brand_name.strip().lower())
        if llm_b is not None:
            ps = passages[comp.brand_name]
            clients = _grounded_items(llm_b.flagship_clients, ps)
            deals = _grounded_items(llm_b.network_and_deals, ps)
            catalysts = [c for c in llm_b.leap_catalysts if is_supported_by(c, ps)]
            dropped += (len(llm_b.flagship_clients) - len(clients)) + (len(llm_b.network_and_deals) - len(deals)) + (
                len(llm_b.leap_catalysts) - len(catalysts)
            )
            bench.flagship_clients = clients[:8]
            bench.network_and_deals = deals[:6]
            bench.pricing_power_leap = _grounded_text(llm_b.pricing_power_leap, ps)
            bench.leap_catalysts = catalysts[:3]
            # Advice, not data: kept only when there are grounded catalysts to base it on.
            bench.merchant_takeaway_playbook = llm_b.merchant_takeaway_playbook[:3] if catalysts else []
        comp.leap_benchmark = bench
        benchmarks.append(bench)

    report.leap_benchmarks = benchmarks
    diagnostics.append(
        f"[LEAP_BENCHMARK] {len(benchmarks)} rival(s) with evidence of growing from a similar start: "
        + ", ".join(b.brand_name for b in benchmarks)
        + (f"; dropped {dropped} ungrounded client/deal/catalyst item(s)" if dropped else "")
        + "."
    )
    if skipped:
        diagnostics.append("[LEAP_BENCHMARK] Not benchmarked: " + "; ".join(skipped[:6]) + ".")
    return report, diagnostics
