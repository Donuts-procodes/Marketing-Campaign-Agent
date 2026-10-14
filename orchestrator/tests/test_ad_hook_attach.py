"""
Ad hooks must survive synthesis renaming the product and the grounding gate.

Measured on live runs: ad intelligence collected 7, 21, 15 and 9 hooks, and the reports
showed 0, 2, 1 and 0, because synthesis turned "Praxent" into "Praxent Services" and hooks
were re-attached by exact product name.
"""

import pytest

from orchestrator.agents.market_research.ingestion import ad_intelligence
from orchestrator.agents.market_research.agent import attach_ad_hooks
from orchestrator.agents.market_research.intelligence.validation.grounding import validate_information_grounding
from orchestrator.schemas.research import CompetitorProfile, SWOTReportDelta


def _comp(brand, product):
    return CompetitorProfile(brand_name=brand, product_name=product)


def test_hooks_attach_after_synthesis_renames_the_product():
    final = [_comp("Praxent", "Praxent Services"), _comp("Table XI (TXI)", "TXI Services"), _comp("MojoTech", "MojoTech Services")]
    attach_ad_hooks(final, {"Praxent": ['Meta Ad Library: "Ship faster"'], "Table XI (TXI)": ["Web ad mention: Built for Chicago"]})
    assert final[0].ad_hooks == ['Meta Ad Library: "Ship faster"']
    assert final[1].ad_hooks == ["Web ad mention: Built for Chicago"]
    assert final[2].ad_hooks == [], "a rival must never receive another rival's ads"


def test_attach_merges_without_duplicating_what_synthesis_kept():
    comp = _comp("thoughtbot", "thoughtbot Services")
    comp.ad_hooks = ["Meta Ad Library: A"]
    attach_ad_hooks([comp], {"thoughtbot": ["Meta Ad Library: A", "Meta Ad Library: B"]})
    assert comp.ad_hooks == ["Meta Ad Library: A", "Meta Ad Library: B"]


@pytest.mark.asyncio
async def test_web_mention_hooks_survive_grounding(monkeypatch):
    snippet = "Praxent new campaign tagline: Modernize your lending platform without the risk of a rewrite."

    class _Result:
        url = "https://news.example.com/praxent"
        title = "Praxent"

        def __init__(self):
            self.snippet = snippet

    async def _fake_search(queries, tavily_client=None):
        return [_Result()]

    monkeypatch.setattr(ad_intelligence, "execute_tavily_search", _fake_search)
    mentions, docs = await ad_intelligence._web_mentions([_comp("Praxent", "Praxent")], tavily_client=object())
    assert mentions["Praxent"], "the snippet should be accepted as an ad mention"
    assert docs == [{"url": "https://news.example.com/praxent", "markdown": snippet}]

    final = _comp("Praxent", "Praxent Services")
    attach_ad_hooks([final], mentions)
    report, _ = validate_information_grounding(
        SWOTReportDelta(competitors=[final]), [d["markdown"] for d in docs], {d["url"] for d in docs}
    )
    assert report.competitors[0].ad_hooks, "a hook whose snippet is in evidence must not be dropped"
