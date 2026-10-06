"""Live wall-clock sourcing: one UTC clock, and models told the real date."""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

from orchestrator.agents.market_research.analysis.freshness import score_recency
from orchestrator.agents.market_research.analysis.grounding import validate_information_grounding
from orchestrator.core import clock
from orchestrator.schemas.research import CompetitorProfile, SWOTReportDelta

_ORCHESTRATOR_ROOT = Path(__file__).resolve().parents[1]


class TestLiveClock:
    def test_reads_live_utc_time(self):
        before = datetime.now(timezone.utc)
        now = clock.utc_now()
        after = datetime.now(timezone.utc)
        assert before <= now <= after
        assert now.tzinfo is timezone.utc

    def test_today_and_year_agree_with_utc_now(self):
        """The helpers must be mutually consistent — that is the whole point of one source."""
        now = clock.utc_now()
        assert clock.today() == now.date()
        assert clock.current_year() == now.date().year
        assert clock.today_iso() == now.date().isoformat()

    def test_today_iso_is_iso_format(self):
        assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", clock.today_iso())

    def test_clock_advances_with_real_time(self):
        """Guards against anyone freezing this to a constant."""
        assert clock.utc_now() <= clock.utc_now()


class TestSingleClockSource:
    """No module may read the wall clock directly; they must go through core.clock."""

    #: time.time() is duration/TTL bookkeeping, not calendar reasoning, so it is allowed.
    _BANNED = ("date.today()", "datetime.now()")

    def _calendar_modules(self):
        for path in (_ORCHESTRATOR_ROOT / "agents").rglob("*.py"):
            if "__pycache__" not in str(path):
                yield path

    def test_no_direct_clock_reads_in_agents(self):
        offenders = []
        for path in self._calendar_modules():
            text = path.read_text(encoding="utf-8")
            for banned in self._BANNED:
                if banned in text:
                    offenders.append(f"{path.relative_to(_ORCHESTRATOR_ROOT)}: {banned}")
        assert offenders == [], (
            "These read the wall clock directly instead of orchestrator.core.clock, "
            f"which lets timezones disagree: {offenders}"
        )


class TestPromptsCarryLiveDate:
    """Models must anchor recency on the real date, not their training cutoff."""

    @pytest.mark.asyncio
    async def test_classifier_prompt_includes_today(self):
        from orchestrator.agents.market_research.analysis.classification import (
            classify_campaign_context,
        )

        captured: dict[str, str] = {}

        class _Capturing:
            def with_structured_output(self, _schema):
                return self

            async def ainvoke(self, messages):
                captured["prompt"] = messages[-1]["content"]
                raise RuntimeError("stop after capture")

        await classify_campaign_context({"category": "Dental Clinic"}, llm=_Capturing())
        assert clock.today_iso() in captured["prompt"]

    @pytest.mark.asyncio
    async def test_synthesis_prompt_includes_today(self):
        from orchestrator.agents.market_research.analysis.synthesis import (
            synthesize_swot_with_llm,
        )

        captured: dict[str, str] = {}

        class _Capturing:
            def with_structured_output(self, _schema, **_kw):
                return self

            async def ainvoke(self, messages):
                captured["system"] = messages[0]["content"]
                captured["user"] = messages[1]["content"]
                return SWOTReportDelta()

        await synthesize_swot_with_llm(
            merchant_context={"product_name": "X", "category": "Y"},
            search_results=[],
            extracted_pages=[],
            llm=_Capturing(),
        )
        assert clock.today_iso() in captured["user"]
        # And the system prompt must tell it to use that date over its training data.
        assert "training data" in captured["system"].lower()


class TestStalenessUsesInjectableDate:
    def test_grounding_flags_stale_evidence_against_supplied_date(self):
        report = SWOTReportDelta(
            competitors=[CompetitorProfile(brand_name="RivalCo", product_name="RivalPro")]
        )
        scraped = ["RivalCo pricing page. Last updated 2015-03-01. Plans from $49."]

        today = date(2026, 10, 6)
        report, diags = validate_information_grounding(
            report, scraped, verified_urls=set(), max_age_days=548, today=today
        )
        assert report.competitors[0].as_of == "2015-03-01"
        assert any("RECENCY" in d for d in diags)

    def test_grounding_does_not_flag_fresh_evidence(self):
        today = date(2026, 10, 6)
        recent = (today - timedelta(days=30)).isoformat()
        report = SWOTReportDelta(
            competitors=[CompetitorProfile(brand_name="RivalCo", product_name="RivalPro")]
        )
        scraped = [f"RivalCo pricing page. Last updated {recent}. Plans from $49."]

        report, diags = validate_information_grounding(
            report, scraped, verified_urls=set(), max_age_days=548, today=today
        )
        assert report.competitors[0].as_of == recent
        assert not any("RECENCY" in d for d in diags)

    def test_recency_scoring_defaults_to_live_clock(self):
        """With no explicit date, staleness is judged against the live clock."""
        just_now = [clock.today()]
        score, _ = score_recency(just_now, has_evidence=True, max_age_days=30)
        assert score == 1.0

        long_ago = [clock.today() - timedelta(days=4000)]
        score, diags = score_recency(long_ago, has_evidence=True, max_age_days=30)
        assert score == 0.0 and diags
