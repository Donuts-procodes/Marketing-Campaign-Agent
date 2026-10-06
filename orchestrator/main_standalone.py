"""
Standalone local execution harness for Strategy Sub-Orchestrator.

Runs the compiled LangGraph pipeline locally without requiring
FastAPI, Redis, or MongoDB infrastructure. Always uses live research
(Tavily search, CrawlAPI deep search, ad libraries); there is no sample-data mode.

    python -m orchestrator.main_standalone --input merchant.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

# Ensure project root is in sys.path when executed directly
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from orchestrator.core.config import get_settings
from orchestrator.schemas.state import StrategyState
from orchestrator.subgraphs.strategy import strategy_subgraph


# ── Execution Runner ─────────────────────────────────────────────────────────

async def run_standalone_orchestrator(merchant_context: dict) -> dict:
    """Run the Strategy Sub-Orchestrator live on a merchant payload."""
    settings = get_settings()

    missing = [
        name
        for name, value in (
            ("OPENAI_API_KEY", settings.openai_api_key),
            (
                "TAVILY_API_KEY or YOU_API_KEY (or DUCKDUCKGO_MODE)",
                settings.tavily_api_key or settings.you_api_key or settings.duckduckgo_mode.lower() != "off",
            ),
        )
        if not value
    ]
    if missing:
        raise SystemExit(f"Live research needs {', '.join(missing)} in .env; no sample data is used.")
    if not (settings.firecrawl_api_key or settings.crawlapi_token or settings.crawlapi_js_token):
        print("WARNING: no crawl API key (FIRECRAWL_API_KEY or CRAWLAPI_TOKEN); deep search falls back "
              "to Tavily Extract and LinkedIn/Google ad libraries are skipped.")

    print("\n=======================================================")
    print(" Strategy Sub-Orchestrator Standalone Harness [LIVE]")
    print("=======================================================\n")

    graph = strategy_subgraph
    print("Pipeline Graph Topology:")
    try:
        print(graph.get_graph().draw_ascii())
    except Exception:
        print("  START -> market_research -> audience_persona -> campaign_strategy -> END")

    print("\nInvoking Strategy Sub-Orchestrator with payload...")
    print(f"Product: {merchant_context.get('product_name')}")
    print(f"Category: {merchant_context.get('category')}")
    print("-------------------------------------------------------")

    state: StrategyState = {
        "merchant_context": merchant_context,
        "swot_report": None,
        "dqs_retries": 0,
        "errors": [],
    }
    final_state = await graph.ainvoke(state)

    report = final_state.get("swot_report")

    print("\n=======================================================")
    print(" EXECUTION RESULTS: SWOT REPORT & INTELLIGENCE DELTA")
    print("=======================================================\n")

    if report is not None:
        report_dict = report.model_dump() if hasattr(report, "model_dump") else report
        print(json.dumps(report_dict, indent=2))

        print("\n-------------------------------------------------------")
        print(f"Data Quality Score (DQS): {report_dict.get('dqs_score'):.2f}")
        print(f"Assumptions Tagged:       {report_dict.get('assumptions_tagged')}")
        print(f"DQS Retry Cycles Used:    {final_state.get('dqs_retries', 0)}")
        print(f"Verified Source URLs ({len(report_dict.get('source_urls', []))}):")
        for idx, url in enumerate(report_dict.get("source_urls", []), 1):
            print(f"  [{idx}] {url}")
    else:
        print("No SWOT report produced.")
    if final_state.get("errors"):
        print("Errors encountered:", final_state["errors"])

    return final_state


def main():
    parser = argparse.ArgumentParser(description="Strategy Sub-Orchestrator Standalone Harness (live)")
    parser.add_argument("--input", required=True, help="Path to merchant context JSON file")
    args = parser.parse_args()

    with open(args.input, encoding="utf-8") as f:
        merchant_context = json.load(f)
    asyncio.run(run_standalone_orchestrator(merchant_context))


if __name__ == "__main__":
    main()
