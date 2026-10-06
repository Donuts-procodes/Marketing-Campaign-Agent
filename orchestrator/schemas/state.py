from __future__ import annotations

from typing import TypedDict

from orchestrator.schemas.research import SWOTReportDelta


class StrategyState(TypedDict, total=False):
    """
    Shared state contract for the Strategy Sub-Orchestrator LangGraph.

    Active fields are populated by the Market Research Agent.
    Reserved future slots carry None defaults and are pass-through
    until their owning agents are implemented.
    """

    # ── Active Fields (Market Research Agent) ─────────────────────
    merchant_context: dict
    """Hydrated merchant dossier: product_name, category, value props, pricing, known competitors."""

    swot_report: SWOTReportDelta | None
    """Populated by Market Research Agent — consumed downstream by Persona & Campaign agents."""

    dqs_retries: int
    """Tracks how many DQS retry loops have been attempted (max 3)."""

    errors: list[str]
    """Accumulator for non-fatal error messages across the pipeline."""

    # ── Reserved Future Slots ─────────────────────────────────────
    persona_profiles: list | None
    """EXTENSION POINT: Audience/Persona Agent output — list of persona archetypes."""

    campaign_brief: dict | None
    """EXTENSION POINT: Campaign Strategy Agent output — structured execution brief."""

    media_brief: dict | None
    """EXTENSION POINT: Media Agent output — asset specs and channel assignments."""
