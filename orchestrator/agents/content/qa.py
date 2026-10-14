"""
Content QA: checks every asset before the merchant approves it.

Rules, not a model, so the same copy always gets the same verdict:
- platform limits (email subject, search-ad headlines and descriptions, ad primary text),
- [placeholders] the merchant still has to fill,
- numbers and prices in the copy that the merchant's brief does not contain (a claim we cannot back),
- competitor names (comparative claims need legal care and were not asked for),
- a missing call to action or empty copy.
Issues are attached to the asset; nothing is rewritten here.
"""

from __future__ import annotations

import re
from typing import Any

from orchestrator.schemas.content import ContentAsset, ContentPack

_LIMITS = {
    "subject": 60,
    "preview_text": 90,
    "search_headline": 30,
    "search_description": 90,
    "ad_text": 125,
    "ad_headline": 40,
    "x_post": 280,
}
_PLACEHOLDER = re.compile(r"\[[^\]]{2,60}\]")
_NUMBER = re.compile(r"(?<![\w.])(?:₹|\$|£|€|rs\.?\s?)?\d[\d,]*(?:\.\d+)?\s?%?", re.I)


def _brief_numbers(merchant_context: dict[str, Any]) -> set[str]:
    text = " ".join(str(v) for v in merchant_context.values() if v is not None)
    return {re.sub(r"[^\d.]", "", m.group(0)).rstrip(".") for m in _NUMBER.finditer(text)} - {""}


def _copy_of(a: ContentAsset) -> str:
    return " ".join(x for x in [a.subject, a.preview_text, a.body, *a.headlines, *a.descriptions, a.cta] if x)


def check_asset(a: ContentAsset, merchant_context: dict[str, Any], rivals: list[str]) -> list[str]:
    issues: list[str] = []
    if a.kind == "email":
        if a.subject and len(a.subject) > _LIMITS["subject"]:
            issues.append(f"Subject is {len(a.subject)} characters; keep it under {_LIMITS['subject']}.")
        if a.preview_text and len(a.preview_text) > _LIMITS["preview_text"]:
            issues.append(f"Preview text is over {_LIMITS['preview_text']} characters.")
        if not a.subject:
            issues.append("Email has no subject.")
    if a.kind == "search_ad":
        long = [h for h in a.headlines if len(h) > _LIMITS["search_headline"]]
        if long:
            issues.append(f"{len(long)} headline(s) over {_LIMITS['search_headline']} characters.")
        if len(a.headlines) < 3:
            issues.append("Google needs at least 3 headlines.")
        if len(a.descriptions) < 2:
            issues.append("Google needs at least 2 descriptions.")
        if any(len(d) > _LIMITS["search_description"] for d in a.descriptions):
            issues.append(f"A description is over {_LIMITS['search_description']} characters.")
    elif not a.body.strip():
        issues.append("Copy is empty.")
    if a.kind == "ad":
        if len(a.body) > _LIMITS["ad_text"]:
            issues.append(f"Primary text is {len(a.body)} characters; Meta truncates after about {_LIMITS['ad_text']}.")
        if a.headlines and len(a.headlines[0]) > _LIMITS["ad_headline"]:
            issues.append(f"Headline is over {_LIMITS['ad_headline']} characters.")
    if a.channel == "x" and len(a.body) > _LIMITS["x_post"]:
        issues.append(f"Post is over {_LIMITS['x_post']} characters.")
    if a.kind != "search_ad" and not (a.cta or "").strip():
        issues.append("No call to action.")

    copy = _copy_of(a)
    holes = sorted(set(_PLACEHOLDER.findall(copy)))
    if holes:
        issues.append(f"Fill in before publishing: {', '.join(holes[:4])}.")
    known = _brief_numbers(merchant_context)
    unbacked = sorted({
        m.group(0).strip() for m in _NUMBER.finditer(_PLACEHOLDER.sub(" ", copy))
        if (n := re.sub(r"[^\d.]", "", m.group(0)).rstrip(".")) and len(n.replace(".", "")) >= 2 and n not in known
    })
    if unbacked:
        issues.append(f"Numbers not in your brief, check they are true: {', '.join(unbacked[:4])}.")
    low = copy.lower()
    named = [r for r in rivals if r and len(r) > 2 and re.search(rf"\b{re.escape(r.lower())}\b", low)]
    if named:
        issues.append(f"Names a competitor ({', '.join(named[:3])}); comparative claims need care.")
    return issues


def review_pack(pack: ContentPack, merchant_context: dict[str, Any], rivals: list[str]) -> int:
    """Attaches issues to every asset; returns how many assets have at least one."""
    flagged = 0
    for a in pack.assets:
        a.qa_issues = check_asset(a, merchant_context, rivals)
        flagged += bool(a.qa_issues)
    return flagged
