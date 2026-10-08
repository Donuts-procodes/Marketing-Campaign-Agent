import pytest

from orchestrator.agents.market_research.analysis.grounding import find_support_excerpt
from orchestrator.agents.market_research.analysis.validator import (
    Gap,
    Rejection,
    ValidatorVerdict,
    collect_items,
    validate_report,
)
from orchestrator.schemas.research import CompetitorProfile, SWOTReportDelta

CORPUS = [
    "Reddit thread: Praxent onboarding was slow, communication with the team broke down twice.",
    "Praxent | We deliver quality solutions for our valued partners.",
    "Review of Acme Corp: their support never answers tickets on weekends.",
    "Praxent pricing: projects start at $5,000 per project for discovery.",
]


def _report():
    return SWOTReportDelta(
        competitors=[
            CompetitorProfile(
                brand_name="Praxent",
                product_name="Praxent Services",
                pricing_model="$5,000 per project",
                core_claims=["We deliver quality solutions for our valued partners."],
                weaknesses_mined=[
                    "Praxent onboarding was slow, communication with the team broke down twice.",
                    "their support never answers tickets on weekends.",
                ],
            )
        ]
    )


class _Structured:
    def __init__(self, verdict=None, fail=False):
        self.verdict, self.fail, self.payload = verdict, fail, None

    def with_structured_output(self, _schema):
        return self

    async def ainvoke(self, messages):
        if self.fail:
            raise RuntimeError("provider down")
        self.payload = messages[1]["content"]
        return self.verdict


def test_excerpt_is_the_passage_the_statement_came_from():
    excerpt = find_support_excerpt("their support never answers tickets on weekends.", CORPUS)
    assert excerpt and "Acme Corp" in excerpt, "the critic must see that this passage is about Acme"


def test_items_carry_ids_and_passages():
    payload, index = collect_items(_report(), CORPUS)
    items = {i["id"]: i for i in payload[0]["items"]}
    assert set(index) == {"c0.pricing_model", "c0.core_claims.0", "c0.weaknesses_mined.0", "c0.weaknesses_mined.1"}
    assert "Acme" in items["c0.weaknesses_mined.1"]["passage"]
    assert payload[0]["missing"] == ["strengths_mined"]


@pytest.mark.asyncio
async def test_rejections_are_applied_by_id_and_unknown_ids_ignored():
    verdict = ValidatorVerdict(
        rejected=[
            Rejection(id="c0.weaknesses_mined.1", reason="about a different company"),
            Rejection(id="c0.core_claims.0", reason="generic filler"),
            Rejection(id="c9.weaknesses_mined.0", reason="invented target"),
        ],
        gaps=[Gap(competitor="Praxent", field="strengths_mined"), Gap(competitor="Nobody Inc", field="pricing_model")],
    )
    report, out, notes = await validate_report(_report(), CORPUS, _Structured(verdict))
    comp = report.competitors[0]
    assert comp.weaknesses_mined == ["Praxent onboarding was slow, communication with the team broke down twice."]
    assert comp.core_claims == []
    assert comp.pricing_model == "$5,000 per project"
    assert len(notes) == 2 and all(n.startswith("[VALIDATOR]") for n in notes)
    assert [g.competitor for g in out.gaps] == ["Praxent"], "gaps for unknown rivals are dropped"


@pytest.mark.asyncio
async def test_price_rejection_clears_the_price():
    verdict = ValidatorVerdict(rejected=[Rejection(id="c0.pricing_model", reason="not their price")])
    report, _, _ = await validate_report(_report(), CORPUS, _Structured(verdict))
    assert report.competitors[0].pricing_model is None


@pytest.mark.asyncio
async def test_validator_failure_leaves_the_grounded_report_untouched():
    report, verdict, notes = await validate_report(_report(), CORPUS, _Structured(fail=True))
    assert len(report.competitors[0].weaknesses_mined) == 2
    assert verdict.rejected == [] and verdict.gaps == [] and notes == []


@pytest.mark.asyncio
async def test_gap_round_fills_missing_pricing_from_targeted_search():
    from orchestrator.agents.market_research.agent import _fill_validator_gaps
    from orchestrator.agents.market_research.discovery.search import TavilySearchResult
    from orchestrator.schemas.research import DynamicParameterTaxonomy

    class _Search:
        queries = None

        async def run(self, queries, round_number=0):
            self.queries = queries
            return [
                TavilySearchResult(
                    vector="pricing_scrape",
                    title="Praxent pricing",
                    url="https://praxent.com/pricing",
                    snippet="Praxent pricing: engagements start at $25,000 per project.",
                    score=0.9,
                )
            ]

    class _Crawl:
        async def run(self, urls):
            return []

    crew = type("Crew", (), {"search": _Search(), "crawl": _Crawl()})()
    report = SWOTReportDelta(
        competitors=[CompetitorProfile(brand_name="Praxent", product_name="Praxent Services", sources=["https://praxent.com"])]
    )
    texts, urls = await _fill_validator_gaps(
        crew,
        report,
        [Gap(competitor="Praxent", field="pricing_model")],
        {"product_name": "DevFlow", "category": "Software agency"},
        DynamicParameterTaxonomy(critical_jtbd_drivers=["price"], minor_attributes=[]),
        1,
    )
    assert crew.search.queries, "a targeted search must be issued for the gap"
    assert "https://praxent.com/pricing" in urls and any("$25,000" in t for t in texts)
    assert report.competitors[0].pricing_model and "25,000" in report.competitors[0].pricing_model
