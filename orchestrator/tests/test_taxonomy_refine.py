from orchestrator.agents.market_research.intelligence.market_mapping.taxonomy import refine_parameters_from_findings
from orchestrator.schemas.research import DynamicParameterTaxonomy

BASE = DynamicParameterTaxonomy(critical_jtbd_drivers=["price"], minor_attributes=["support_hours"])


def test_attribute_shared_by_two_pages_is_kept_first():
    pages = ["| Tech Stack | React, Node |", "- Tech Stack: Python and Django"]
    out = refine_parameters_from_findings(BASE, pages)
    assert out.minor_attributes[0] == "tech_stack"
    assert "support_hours" in out.minor_attributes


def test_single_page_table_rows_are_not_attributes():
    out = refine_parameters_from_findings(BASE, ["| Team Size | 40 |\n| Office | Austin |"])
    assert out.minor_attributes == ["support_hours"]


def test_page_furniture_is_rejected_even_when_repeated():
    junk = "| Tuesday | 9am - 5pm |\n| tungnt620 9 months ago | great post |\n- Wednesday: closed"
    out = refine_parameters_from_findings(BASE, [junk, junk.replace("Tuesday", "TTuesday")])
    assert out.minor_attributes == ["support_hours"]
