import { SWOTReportDelta } from "@/types/research";

/**
 * Exports competitor analysis matrix to standard CSV format.
 */
export function exportToCSV(swotReport: SWOTReportDelta, filename = "market_intel_competitors.csv"): void {
  const competitors = swotReport.competitors || [];
  if (competitors.length === 0) return;

  // Order must match the row builder below: the last column previously read
  // "Target Audience / ICP" while carrying factual_evidence.
  const headers = [
    "Brand Name",
    "Product Name",
    "Relevance",
    "Why Relevant",
    "Pricing Model",
    "Evidence As Of",
    "Verified Core Claims",
    "Customer Weaknesses / Gripes",
    "Live Ad Hooks",
    "Evidence Grounding URLs",
    "Supporting Evidence Quotes",
  ];

  const escapeCell = (val: string | number | null | undefined): string => {
    if (val === null || val === undefined) return '""';
    const str = String(val).replace(/"/g, '""');
    return `"${str}"`;
  };

  const rows = competitors.map((c) => [
    escapeCell(c.brand_name),
    escapeCell(c.product_name),
    escapeCell(c.relevance_score != null ? c.relevance_score.toFixed(2) : ""),
    escapeCell(c.relevance_reason || ""),
    escapeCell(c.pricing_model || "Not publicly listed"),
    escapeCell(c.as_of || "undated"),
    escapeCell(c.core_claims?.join("; ") || ""),
    escapeCell(c.weaknesses_mined?.join("; ") || ""),
    escapeCell(c.ad_hooks?.join("; ") || ""),
    escapeCell(c.sources?.join("; ") || ""),
    escapeCell(c.factual_evidence?.join("; ") || ""),
  ]);

  // Excel assumes the system codepage unless the file opens with a UTF-8 BOM, which mangles
  // accented brand names and the quote characters in mined gripes.
  const csvContent = "﻿" + [headers.join(","), ...rows.map((r) => r.join(","))].join("\r\n");
  const blob = new Blob([csvContent], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.setAttribute("href", url);
  link.setAttribute("download", filename);
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
}

/**
 * Prints the report / saves as PDF.
 *
 * The print layout itself lives in the `@media print` block in index.css, which hides the
 * app chrome and un-clips the truncated table cells. This sets the document title first
 * because browsers use it for the default PDF filename and the page header, so without it
 * every exported file is called "Marketing Orchestrator" or similar.
 */
export function printDashboardReport(productName?: string): void {
  const previousTitle = document.title;
  const stamp = new Date().toISOString().slice(0, 10);
  const subject = productName?.trim() || "Market Intelligence";
  document.title = `${subject} - Competitor Report - ${stamp}`;

  // Chrome/Safari fire this synchronously; restoring afterwards keeps the tab title intact.
  const restore = () => {
    document.title = previousTitle;
    window.removeEventListener("afterprint", restore);
  };
  window.addEventListener("afterprint", restore);

  window.print();
}
