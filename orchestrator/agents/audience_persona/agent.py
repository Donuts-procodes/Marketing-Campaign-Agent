"""
Audience Persona Agent node.

Turns the research's audience read (ICP, segments, pains, triggers, channels: each point already
tied to a page or the merchant's brief) and the buyer types rivals' reviewers describe into 2-3
personas the strategy plans against: one primary, one challenger.

The model may only regroup and name what those inputs say; every persona keeps the source URLs of
the points it was built from, and a persona with no supporting point is dropped. Without a model,
or when it fails, the research-derived personas are used, so the strategy always has personas.
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any, Callable, Coroutine

from pydantic import BaseModel, Field

from orchestrator.schemas.persona import PersonaInput
from orchestrator.schemas.state import StrategyState

if TYPE_CHECKING:
    from orchestrator.schemas.api import BYOKConfig

logger = logging.getLogger(__name__)

ProgressFn = Callable[[str, str], Coroutine[Any, Any, None]]

PROMPT = """\
Build 2-3 buyer personas for this campaign from the numbered audience points and buyer types \
below. Use ONLY those points: regroup and name them, do not add facts.

For each persona give: name (a short label), description (1-2 sentences), demographics (only \
attributes the points state), pains, motivations, objections, preferred_channels, \
buying_triggers, role ("primary" for the one to win first, then "challenger", then "later"), \
and refs: the ids of the points it is built from (at least one).
"""


class _Persona(BaseModel):
    name: str
    description: str = ""
    demographics: dict[str, str] = Field(default_factory=dict)
    pains: list[str] = Field(default_factory=list)
    motivations: list[str] = Field(default_factory=list)
    objections: list[str] = Field(default_factory=list)
    preferred_channels: list[str] = Field(default_factory=list)
    buying_triggers: list[str] = Field(default_factory=list)
    role: str = "later"
    refs: list[str] = Field(default_factory=list)


class _Personas(BaseModel):
    personas: list[_Persona] = Field(default_factory=list)


async def _say(on_progress: ProgressFn | None, message: str) -> None:
    if on_progress:
        try:
            await on_progress(message, "INFO")
        except Exception:
            pass


def audience_points(swot_report: Any) -> list[tuple[str, str, str | None]]:
    """(id, text, source_url) for every grounded audience point and review buyer type."""
    points: list[tuple[str, str, str | None]] = []
    audience = getattr(swot_report, "audience", None)
    if audience is not None:
        if audience.icp is not None and audience.icp.name:
            attrs = ", ".join(f"{k}: {v}" for k, v in audience.icp.attributes.items())
            src = next((p.source_url for p in audience.icp.why if p.source_url), None)
            points.append(("", f"ICP: {audience.icp.name}. {audience.icp.description} {attrs}".strip(), src))
        for label, items in (("Pain", audience.pains), ("Motivation", audience.motivations),
                             ("Behavior", audience.behaviors), ("Trigger", audience.triggers),
                             ("Barrier", audience.barriers)):
            points += [("", f"{label}: {p.text}", p.source_url) for p in items]
        points += [("", f"Channel: {c.text} ({c.reason})", c.source_url) for c in audience.channels]
        points += [("", f"Segment: {g.name} — {g.definition}; trigger: {g.trigger}", g.source_url)
                   for g in audience.segments]
    for comp in getattr(swot_report, "competitors", None) or []:
        rc = getattr(comp, "review_context", None)
        src = comp.sources[0] if comp.sources else None
        for persona in (rc.buyer_personas if rc else [])[:3]:
            points.append(("", f"Buyer type in reviews of {comp.brand_name}: {persona}", src))
    return [(f"A{i + 1}", text, url) for i, (_, text, url) in enumerate(points)]


def ground_personas(raw: _Personas, points: list[tuple[str, str, str | None]]) -> list[PersonaInput]:
    by_id = {pid: url for pid, _, url in points}
    out: list[PersonaInput] = []
    roles_taken: set[str] = set()
    for i, p in enumerate(raw.personas[:3]):
        refs = [r.strip().upper() for r in p.refs if r.strip().upper() in by_id]
        if not refs or not p.name.strip():
            continue  # a persona nothing in the research supports
        role = p.role if p.role in ("primary", "challenger", "later") and p.role not in roles_taken else "later"
        roles_taken.add(role)
        out.append(PersonaInput(
            persona_id=f"persona_{i + 1}",
            name=p.name.strip()[:120],
            description=p.description,
            demographics=p.demographics,
            pains=p.pains[:5],
            motivations=p.motivations[:5],
            objections=p.objections[:5],
            preferred_channels=p.preferred_channels[:5],
            buying_triggers=p.buying_triggers[:5],
            evidence=list(dict.fromkeys(u for r in refs if (u := by_id[r])))[:5],
            source="persona_agent",
            confidence=min(0.85, 0.4 + 0.1 * len(refs)),
            role=role,  # type: ignore[arg-type]
        ))
    return out


async def execute_audience_persona(
    state: StrategyState,
    *,
    llm: Any = None,
    llm_config: BYOKConfig | None = None,
    on_progress: ProgressFn | None = None,
) -> dict[str, Any]:
    from orchestrator.agents.campaign_strategy.context import derive_personas_from_research
    from orchestrator.core.llm import LLMConfigurationError, build_chat_model, has_llm_credentials

    swot_report = state.get("swot_report")
    merchant_context = state.get("merchant_context", {})
    fallback = derive_personas_from_research(swot_report, merchant_context) if swot_report else []

    points = audience_points(swot_report) if swot_report else []
    if llm is None and has_llm_credentials(llm_config):
        try:
            llm = build_chat_model(llm_config, fast=True)
        except LLMConfigurationError:
            llm = None
    if llm is None or len(points) < 3:
        await _say(on_progress, f"[AUDIENCE_PERSONA] {len(fallback)} persona(s) derived from the research")
        return {"persona_profiles": [p.model_dump() for p in fallback]}

    try:
        result = await llm.with_structured_output(_Personas).ainvoke([
            {"role": "system", "content": PROMPT},
            {"role": "user", "content": json.dumps({
                "product": {k: merchant_context.get(k) for k in ("product_name", "category", "primary_value_prop")},
                "points": [{"id": pid, "text": text} for pid, text, _ in points[:40]],
            }, ensure_ascii=False)},
        ])
        if not isinstance(result, _Personas):
            result = _Personas.model_validate(result)
        personas = ground_personas(result, points)
    except Exception as exc:
        logger.warning("Persona agent failed: %s", exc)
        personas = []

    if not personas:
        await _say(on_progress, f"[AUDIENCE_PERSONA] Using {len(fallback)} research-derived persona(s)")
        return {"persona_profiles": [p.model_dump() for p in fallback]}
    names = ", ".join(f"{p.name} ({p.role})" for p in personas)
    await _say(on_progress, f"[AUDIENCE_PERSONA] {len(personas)} persona(s) from {len(points)} audience point(s): {names}")
    return {"persona_profiles": [p.model_dump() for p in personas]}
