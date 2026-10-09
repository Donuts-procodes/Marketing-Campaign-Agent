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

    # Active Fields (Market Research Agent)
    merchant_context: dict
    """Hydrated merchant dossier: product_name, category, value props, pricing, known competitors."""

    swot_report: SWOTReportDelta | None
    """Populated by Market Research Agent — consumed downstream by Persona & Campaign agents."""

    dqs_retries: int
    """Tracks how many DQS retry loops have been attempted (max 3)."""

    errors: list[str]
    """Accumulator for non-fatal error messages across the pipeline."""

    # Cross-run memory fields
    run_mode: str | None
    """'update' triggers incremental search (time-bounded queries + prior competitor seeding).
    'fresh' (default/None) runs a full discovery scan regardless of prior data."""

    prior_report: SWOTReportDelta | None
    """Previous run's SWOTReportDelta for the same product. Populated by campaign_service
    before the pipeline starts when run_mode='update'."""

    prior_run_at: str | None
    """ISO datetime string of when the prior run finished. Used to bound time-range queries."""

    baseline_report: SWOTReportDelta | None
    """The last finished run for the same product, loaded on EVERY run (fresh or update).
    Read only by the wedge scan and threat watch, which need a previous reading to measure
    movement; it is never merged into a fresh run's findings."""

    baseline_run_at: str | None
    """ISO datetime of when baseline_report's run finished; the start of the momentum window."""

    bench_competitors: list
    """Competitors the research loop discovered but the top-N cut-off excluded. Served by
    'find more competitors' before any new search is run."""

    # Reserved Future Slots
    persona_profiles: list | None
    """EXTENSION POINT: Audience/Persona Agent output — list of persona archetypes."""

    campaign_brief: dict | None
    """EXTENSION POINT: Campaign Strategy Agent output — structured execution brief."""

    media_brief: dict | None
    """EXTENSION POINT: Media Agent output — asset specs and channel assignments."""
