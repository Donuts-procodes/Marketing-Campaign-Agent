"""
Tests for dossier audit, unit economics simulation, and launch roadmap generation.
"""

from orchestrator.agents.market_research.intelligence.advisory.dossier_auditor import (
    audit_merchant_dossier,
    build_unit_economics_model,
    generate_launch_roadmap,
)
from orchestrator.schemas.research import SWOTReportDelta


def test_dossier_audit_detects_unsubstantiated_claims():
    merchant_context = {
        "product_name": "Sovereign Oxford",
        "category": "Men's Footwear",
        "target_geography": "India",
        "description": "Goodyear-welted oxford with zero break-in, monsoon-resistant leather, and hybrid rubber sole.",
    }
    audit = audit_merchant_dossier(merchant_context)

    # Should detect zero break-in and monsoon-resistant claims
    assert any("zero break-in" in c for c in audit.unsubstantiated_claims)
    assert any("monsoon-resistant" in c for c in audit.unsubstantiated_claims)

    # Should detect Goodyear-welted vs hybrid rubber sole potential mismatch
    assert len(audit.spec_inconsistencies) >= 1
    assert "Goodyear-welted" in audit.spec_inconsistencies[0]

    # Should identify India Footwear regulatory requirements
    assert any("QCO" in r or "BIS" in r for r in audit.regulatory_and_compliance)


def test_unit_economics_model_calculates_contribution_and_gst():
    merchant_context = {
        "product_name": "Sovereign Oxford",
        "target_price": "7499",
        "category": "Formal Shoes",
    }
    model = build_unit_economics_model(merchant_context)

    assert len(model.scenarios) == 3
    base_case = next(s for s in model.scenarios if "Base Case" in s.label)
    assert base_case.target_price == 7499.0
    # Net revenue after 18% GST on ₹7499 is ~₹6355
    assert 6300 <= base_case.net_revenue_ex_tax <= 6400
    # Net contribution should be positive and realistic (~1000 to 2000)
    assert 1000 <= base_case.contribution_per_unit <= 2000
    assert base_case.contribution_margin_pct > 15.0


def test_launch_roadmap_structure():
    roadmap = generate_launch_roadmap("Sovereign Oxford", "Delhi NCR, Bengaluru, Mumbai")
    assert len(roadmap.phases) == 3
    assert "Days 1–30" in roadmap.phases[0].phase_name
    assert "Days 31–60" in roadmap.phases[1].phase_name
    assert "Days 61–90" in roadmap.phases[2].phase_name
    assert len(roadmap.key_metrics_dashboard) >= 3


def test_swot_report_delta_schema_backward_compatibility():
    delta = SWOTReportDelta()
    assert delta.dossier_audit is None
    assert delta.unit_economics is None
    assert delta.launch_roadmap is None

    audit = audit_merchant_dossier({"product_name": "Oxford", "description": "12-hour comfort"})
    delta.dossier_audit = audit
    assert len(delta.dossier_audit.unsubstantiated_claims) >= 1
