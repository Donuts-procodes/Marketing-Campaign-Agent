"""
Tier 2 -- threat watch: momentum tracking on the few peer rivals most likely to overtake.

The question this answers is not "who is biggest" but "who is moving fastest from where I
am". A static report cannot answer it; movement needs two readings. So every scan stores a raw
snapshot per watched rival, and the next scan measures velocity against it.

Revenue and customer-acquisition cost are not public for private brands, and estimating them
would produce confident fiction. The score is built only from signals anyone can re-check:

    review_velocity  growth in public review count     -> proxy for sales volume
    ad_momentum      new and active ad creatives       -> proxy for ad spend / a new push
    share_of_voice   share of fetched pages naming it  -> proxy for awareness
    launch           dated launches in their milestones
    repositioning    claims they started making
    price_pressure   their price against the merchant's
    overlap          how directly they compete (relevance score)

Fully deterministic: the same inputs always give the same score, and each score is shown with
the signals behind it. Signals that cannot be read on a given scan (no baseline yet, no
merchant price) are left out and the remaining weights renormalized, rather than guessed.
"""

from __future__ import annotations

import re
from datetime import date
from typing import Any

from orchestrator.agents.market_research.intelligence.validation.freshness import extract_dates, parse_iso_date
from orchestrator.core.clock import today as clock_today
from orchestrator.schemas.research import (
    CompetitorProfile,
    SWOTReportDelta,
    ThreatEntry,
    ThreatSignal,
    ThreatWatch,
    WedgeScan,
)

WEIGHTS: dict[str, float] = {
    "review_velocity": 0.30,
    "ad_momentum": 0.20,
    "overlap": 0.15,
    "share_of_voice": 0.10,
    "launch": 0.10,
    "price_pressure": 0.10,
    "repositioning": 0.05,
}

# Review growth of this much per 30 days scores 1.0 on review_velocity.
_FULL_REVIEW_GROWTH = 0.30
# Rates (review growth, share of mentions, messaging) are only measured against a baseline at
# least this old. Two scans a day apart read different pages; the difference is scrape noise,
# and reporting it labelled every rival "slowing" on a run with no review or ad data at all.
# Discrete events (a price cut, new ad creatives, a dated launch) are reported at any age.
_MIN_WINDOW_DAYS = 7
# A claim counts as new messaging only if it shares less than this much vocabulary with every
# claim they made before; a re-scraped, re-worded version of the same claim is not news.
_CLAIM_SIMILARITY = 0.5
_LAUNCH_HOT_DAYS = 120
_LAUNCH_WARM_DAYS = 365

METHOD_NOTE = (
    "Scores use public signals only: review count stands in for sales volume, active ad "
    "creatives for ad spend, and the share of pages naming a brand for awareness. Revenue and "
    "acquisition cost are not public for private brands, so they are never estimated."
)


def _key(name: str) -> str:
    return "".join(ch for ch in (name or "").lower() if ch.isalnum())


def _clamp(x: float) -> float:
    return max(0.0, min(1.0, x))


def _rating(value: str | None) -> float | None:
    try:
        return float(str(value).split("/")[0]) if value else None
    except ValueError:
        return None


def _price(c: CompetitorProfile) -> float | None:
    p = c.pricing_parsed
    if p is None:
        return None
    return p.monthly_equivalent if p.monthly_equivalent is not None else p.amount


def _mention_share(name: str, corpus: list[str]) -> float:
    name = (name or "").strip()
    docs = [t for t in corpus if t]
    if len(name) < 3 or not docs:
        return 0.0
    # Whole-word match: a substring count credits "Hal" with every "half" and "shall".
    rx = re.compile(rf"(?<![A-Za-z0-9]){re.escape(name)}(?![A-Za-z0-9])", re.I)
    return sum(1 for t in docs if rx.search(t)) / len(docs)


def _tokens(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]+", text.lower()) if len(w) > 2}


def _new_claims(current: list[str], previous: list[str]) -> list[str]:
    """Claims genuinely unlike anything said before. Empty when the history is too thin to judge."""
    if not previous:
        return []
    old = [_tokens(p) for p in previous if p]
    fresh = []
    for claim in current:
        t = _tokens(claim)
        if not t:
            continue
        if all(len(t & o) / max(1, len(t | o)) < _CLAIM_SIMILARITY for o in old):
            fresh.append(claim)
    # When most of what we read is "new", we read different pages, not new messaging.
    if len(fresh) > max(2, len(current) // 2):
        return []
    return fresh


def snapshot_of(c: CompetitorProfile, share: float) -> dict[str, float | int | str | None]:
    """The raw readings the next scan measures velocity against."""
    return {
        "review_count": c.review_count,
        "rating": _rating(c.rating),
        "ad_hooks": len(c.ad_hooks),
        "share_of_voice": round(share, 4),
        "price": _price(c),
        "currency": c.pricing_parsed.currency if c.pricing_parsed else None,
        "claims": len(c.core_claims),
    }


def _baseline_snapshot(
    brand: str, baseline: SWOTReportDelta | None
) -> tuple[dict[str, Any] | None, CompetitorProfile | None]:
    """Prior readings for one brand: the stored snapshot when there is one, else the profile."""
    if baseline is None:
        return None, None
    k = _key(brand)
    profile = next((c for c in baseline.competitors if _key(c.brand_name) == k), None)
    if baseline.threat_watch:
        for e in baseline.threat_watch.watched:
            if _key(e.brand_name) == k and e.snapshot:
                return dict(e.snapshot), profile
    if profile is not None:
        return snapshot_of(profile, share=-1.0), profile  # -1: share unknown for this scan
    return None, None


def _recent_launch(c: CompetitorProfile, today: date) -> tuple[float | None, str]:
    newest: date | None = None
    newest_text = ""
    for m in c.milestones:
        for d in extract_dates(m, limit=200):
            if d <= today and (newest is None or d > newest):
                newest, newest_text = d, m
    if newest is None:
        return None, ""
    age = (today - newest).days
    if age <= _LAUNCH_HOT_DAYS:
        return 1.0, newest_text
    if age <= _LAUNCH_WARM_DAYS:
        return 0.4, newest_text
    return 0.0, newest_text


def _merchant_price(merchant_context: dict[str, Any]) -> float | None:
    p = merchant_context.get("price_usd")
    return float(p) if isinstance(p, (int, float)) and p > 0 else None


def assess(
    c: CompetitorProfile,
    *,
    corpus: list[str],
    merchant_context: dict[str, Any],
    baseline: SWOTReportDelta | None,
    baseline_date: date | None,
    today: date,
    max_share: float,
    scale: str = "unknown",
) -> ThreatEntry:
    """Scores one rival. Pure: same inputs, same entry."""
    share = _mention_share(c.brand_name, corpus)
    snap = snapshot_of(c, share)
    prior, prior_profile = _baseline_snapshot(c.brand_name, baseline)
    has_baseline = prior is not None and baseline_date is not None
    age_days = (today - baseline_date).days if has_baseline else None
    # Rates need a window long enough to mean something; events do not.
    rates_ok = has_baseline and age_days is not None and age_days >= _MIN_WINDOW_DAYS
    days = age_days if rates_ok else None
    too_soon = (
        f"last scan was {age_days} day(s) ago; rates are measured over {_MIN_WINDOW_DAYS}+ days"
        if has_baseline and not rates_ok else ""
    )

    signals: list[ThreatSignal] = []
    scores: dict[str, float] = {}
    changed: list[str] = []
    review_per30: float | None = None
    new_hooks = 0
    share_ratio: float | None = None
    price_cut = False

    # Review velocity: the closest public stand-in for sales.
    rc, prc = c.review_count, (prior or {}).get("review_count")
    if rc is not None and rates_ok and isinstance(prc, (int, float)) and prc > 0:
        growth = (rc - prc) / prc
        review_per30 = growth * 30 / days
        scores["review_velocity"] = _clamp(review_per30 / _FULL_REVIEW_GROWTH)
        signals.append(ThreatSignal(
            key="review_velocity", label="Review growth", value=f"{rc:,} reviews",
            change=f"{growth:+.0%} since {baseline_date.isoformat()} ({review_per30:+.0%}/30d)",
            direction="up" if rc > prc else "down" if rc < prc else "flat",
            score=scores["review_velocity"],
        ))
        if rc != prc:
            changed.append(f"Reviews {int(prc):,} → {rc:,}")
    elif rc is not None:
        signals.append(ThreatSignal(
            key="review_velocity", label="Review growth", value=f"{rc:,} reviews",
            change=too_soon or "baseline set; growth shows from the next scan", direction="new",
        ))

    # Ad momentum: new creatives mean a new push; active ones mean ongoing spend.
    active = len(c.ad_hooks)
    if has_baseline and prior_profile is not None:
        old = set(prior_profile.ad_hooks)
        new_hooks = sum(1 for h in c.ad_hooks if h and h not in old)
        scores["ad_momentum"] = _clamp(new_hooks / 3) * 0.7 + _clamp(active / 6) * 0.3
        change = f"{new_hooks} new since last scan" if new_hooks else "no new creatives"
        if new_hooks:
            changed.append(f"{new_hooks} new ad creative(s)")
    else:
        scores["ad_momentum"] = _clamp(active / 6)
        change = "baseline set"
    signals.append(ThreatSignal(
        key="ad_momentum", label="Ad activity", value=f"{active} active creative(s)", change=change,
        direction="up" if new_hooks else ("new" if not has_baseline else "flat"),
        score=scores["ad_momentum"],
    ))

    # Share of voice. Each scan reads a different page set, so only the ratio is compared.
    prior_share = (prior or {}).get("share_of_voice")
    if rates_ok and isinstance(prior_share, (int, float)) and prior_share > 0:
        share_ratio = share / prior_share
        scores["share_of_voice"] = _clamp(share_ratio - 1.0)
        signals.append(ThreatSignal(
            key="share_of_voice", label="Share of mentions", value=f"{share:.0%} of pages",
            change=f"{share_ratio:.1f}× vs last scan",
            direction="up" if share_ratio > 1.1 else "down" if share_ratio < 0.9 else "flat",
            score=scores["share_of_voice"],
        ))
    elif max_share > 0:
        scores["share_of_voice"] = _clamp(share / max_share) * 0.5
        signals.append(ThreatSignal(
            key="share_of_voice", label="Share of mentions", value=f"{share:.0%} of pages",
            direction="new", score=scores["share_of_voice"],
        ))

    launch_score, launch_text = _recent_launch(c, today)
    if launch_score is not None:
        scores["launch"] = launch_score
        signals.append(ThreatSignal(
            key="launch", label="Recent launch", value=launch_text[:120],
            direction="up" if launch_score >= 1.0 else "flat", score=launch_score,
        ))
        if launch_score >= 1.0:
            changed.append(f"Launch: {launch_text[:80]}")

    if rates_ok and prior_profile is not None:
        added = _new_claims(c.core_claims, prior_profile.core_claims)
        if added:
            scores["repositioning"] = _clamp(len(added) / 3)
            signals.append(ThreatSignal(
                key="repositioning", label="New messaging", value=added[0][:120],
                change=f"{len(added)} new claim(s)", direction="up", score=scores["repositioning"],
            ))
            changed.append(f"New claim: “{added[0][:70]}”")

    # Price pressure only means something against the merchant's own price.
    rival_price = _price(c)
    mine = _merchant_price(merchant_context)
    prior_price = (prior or {}).get("price")
    # Only a same-currency move is a price cut: "$49" -> "Rs 1,999" is a relisting, not a 98% drop.
    same_ccy = (prior or {}).get("currency") == (c.pricing_parsed.currency if c.pricing_parsed else None)
    if (
        rival_price is not None
        and isinstance(prior_price, (int, float))
        and same_ccy
        and rival_price < prior_price - 0.01
    ):
        price_cut = True
        changed.append(f"Price cut {prior_price:g} → {rival_price:g}")
    # The merchant's price is stored in USD. A rival priced in rupees or euros is not compared
    # against it: converting at an assumed rate would put a made-up number on the dashboard.
    rival_ccy = c.pricing_parsed.currency if c.pricing_parsed else None
    comparable = rival_ccy in (None, "USD")
    if rival_price is not None and mine is not None and comparable:
        ratio = rival_price / mine
        s = 1.0 if ratio <= 0.85 else 0.6 if ratio <= 1.0 else 0.2 if ratio <= 1.15 else 0.0
        if price_cut:
            s = 1.0
        scores["price_pressure"] = s
        signals.append(ThreatSignal(
            key="price_pressure", label="Price vs yours", value=c.pricing_model or f"{rival_price:g}",
            change=f"{ratio - 1:+.0%} vs your price" + (" · just cut" if price_cut else ""),
            direction="down" if price_cut else "flat", score=s,
        ))

    scores["overlap"] = _clamp(c.relevance_score)
    signals.append(ThreatSignal(
        key="overlap", label="Overlap with you", value=f"{c.relevance_score:.0%}",
        change=(c.relevance_reason or "")[:120], direction="flat", score=scores["overlap"],
    ))

    total_w = sum(WEIGHTS[k] for k in scores)
    threat = round(sum(WEIGHTS[k] * v for k, v in scores.items()) / total_w, 3) if total_w else 0.0

    measured = review_per30 is not None or share_ratio is not None
    if not has_baseline:
        momentum = "baseline"
    elif (
        (review_per30 is not None and review_per30 >= 0.15)
        or new_hooks >= 2
        or (share_ratio is not None and share_ratio >= 1.5)
        or price_cut
        or (launch_score or 0) >= 1.0
    ):
        momentum = "accelerating"
    elif not measured and new_hooks == 0:
        # Nothing to compare: no review counts, no ads, or a baseline too recent. Saying
        # "slowing" here would be a claim the data cannot support.
        momentum = "no_data"
    elif (
        review_per30 is not None and review_per30 <= 0.01
        and new_hooks == 0
        and (share_ratio is None or share_ratio < 0.8)
    ):
        # Measured: reviews flat over a real window, attention falling, no new ads.
        momentum = "slowing"
    else:
        momentum = "steady"

    if not has_baseline and baseline is not None:
        changed.insert(0, "First scan with this rival on the watch list")

    entry = ThreatEntry(
        brand_name=c.brand_name,
        threat_score=threat,
        momentum=momentum,
        scale=scale,
        signals=sorted(signals, key=lambda s: WEIGHTS.get(s.key, 0) * s.score, reverse=True),
        what_changed=changed,
        snapshot=snap,
    )
    entry.headline = _headline(entry, c, review_per30, new_hooks, price_cut)
    entry.counter_move = _counter_move(entry, c)
    return entry


def _headline(e: ThreatEntry, c: CompetitorProfile, review_per30: float | None, new_hooks: int, price_cut: bool) -> str:
    # Strongest evidence of growth leads; a price cut is the next most actionable move.
    if review_per30 is not None and review_per30 >= 0.05:
        return f"Reviews growing {review_per30:.0%} a month" + (", and just cut their price" if price_cut else "")
    if price_cut:
        return "Just cut their price"
    if new_hooks >= 2:
        return f"Launched {new_hooks} new ad creatives"
    top = next((s for s in e.signals if s.score > 0), None)
    if top is None:
        return "Closest match to your positioning"
    return {
        "launch": "Recent launch",
        "ad_momentum": f"Actively advertising ({len(c.ad_hooks)} creatives)",
        "price_pressure": "Priced below you" if "−" in top.change or top.change.startswith("-") else "Priced near you",
        "share_of_voice": "Getting talked about",
        "repositioning": "Changing their message",
        "overlap": "Closest match to your positioning",
        "review_velocity": "Review count rising",
    }.get(top.key, "Worth watching")


def _counter_move(e: ThreatEntry, c: CompetitorProfile) -> str:
    rc = c.review_context
    complaint = rc.top_complaint_drivers[0].topic.lower() if rc and rc.top_complaint_drivers else (
        c.weaknesses_mined[0][:60].lower() if c.weaknesses_mined else ""
    )
    top = next((s.key for s in e.signals if s.score > 0), "overlap")
    if top == "review_velocity":
        move = "Their sales proxy is climbing: read their newest reviews for what buyers reward, and match it before the gap widens."
    elif top == "ad_momentum":
        move = "They are paying for attention: don't outbid them; run one low-cost counter-hook" + (
            f" on their weak spot ({complaint})." if complaint else "."
        )
    elif top == "price_pressure":
        move = "Don't follow them down on price; lead with what they lack" + (f" ({complaint})." if complaint else ".")
    elif top == "launch":
        move = "Fresh launch: their first reviews over the next few weeks will show their weak spots. Check back and aim at them."
    elif top == "repositioning":
        move = "They are moving onto new ground: check whether their new claim overlaps yours and sharpen your difference."
    else:
        move = (rc.counter_positioning_angle if rc and rc.counter_positioning_angle else
                "Closest rival to your positioning: make your one difference obvious in every listing and ad.")
    return move[:260]


def build_threat_watch(
    report: SWOTReportDelta,
    corpus: list[str],
    merchant_context: dict[str, Any],
    *,
    wedge: WedgeScan | None = None,
    baseline: SWOTReportDelta | None = None,
    baseline_run_at: str | None = None,
    watch_size: int = 5,
) -> tuple[ThreatWatch, list[str]]:
    """Scores every profiled rival and keeps the `watch_size` peer-scale ones most likely to overtake."""
    today = clock_today()
    baseline_date = parse_iso_date(baseline_run_at) if baseline_run_at else None
    if baseline_date is None and baseline is not None and baseline.threat_watch:
        baseline_date = parse_iso_date(baseline.threat_watch.scanned_at)

    scale_by_key = {_key(c.brand_name): c.scale for c in (wedge.candidates if wedge else [])}
    shares = [_mention_share(c.brand_name, corpus) for c in report.competitors]
    max_share = max(shares, default=0.0)

    entries = [
        assess(
            c, corpus=corpus, merchant_context=merchant_context, baseline=baseline,
            baseline_date=baseline_date, today=today, max_share=max_share,
            scale=scale_by_key.get(_key(c.brand_name), "unknown"),
        )
        for c in report.competitors
    ]

    # A category giant is not the rival that overtakes a small merchant; it is the backdrop,
    # and its playbook (a budget the merchant does not have) is not one to copy. Giants never
    # enter the watch list. "Larger" brands only backfill when fewer than three peers exist,
    # and only when the scan found no peers or unknowns at all does the list fall back to
    # everyone, so the panel is never empty for a market made only of big names.
    by_score = lambda es: sorted(es, key=lambda e: e.threat_score, reverse=True)  # noqa: E731
    peers = by_score([e for e in entries if e.scale not in ("incumbent", "larger")])
    larger = by_score([e for e in entries if e.scale == "larger"])
    pool = peers + larger[: max(0, 3 - len(peers))]
    if not pool:
        pool = by_score(entries)
    watched = by_score(pool)[:watch_size]

    alerts: list[str] = []
    for e in watched:
        if e.momentum == "accelerating":
            alerts.append(f"{e.brand_name} is accelerating: {e.headline.lower()}.")
    if wedge:
        fresh = [c.brand_name for c in wedge.candidates if c.emerging and not c.deep_researched]
        if fresh:
            alerts.append(f"Emerging in your niche, not yet researched: {', '.join(fresh[:4])}.")

    note = METHOD_NOTE
    if baseline_date is None:
        note += " This is the first scan, so momentum shows from the next refresh."

    watch = ThreatWatch(
        scanned_at=today.isoformat(),
        baseline_date=baseline_date.isoformat() if baseline_date else None,
        watched=watched,
        alerts=alerts,
        method_note=note,
    )

    excluded = len(entries) - len(pool)
    diagnostics = [
        f"[THREAT_MONITOR] Watching {len(watched)} rival(s)"
        + (f" (momentum vs {baseline_date.isoformat()})" if baseline_date else " (first scan: baseline set)")
        + (f"; {excluded} incumbent/larger brand(s) left off" if excluded else "")
        + ": "
        + ", ".join(f"{e.brand_name} {e.threat_score:.2f} {e.momentum}" for e in watched)
        + "."
    ]
    diagnostics += [f"[THREAT_MONITOR] Alert: {a}" for a in alerts]
    return watch, diagnostics


def assign_cohorts(report: SWOTReportDelta) -> list[str]:
    """
    Labels each profiled rival by why it matters to a small merchant. Each label needs evidence:
      leapfrog     - has a leap benchmark (same offering + stated growth; see leap_analyzer)
      catching_up  - on the threat watch, not a giant, and measurably accelerating
      peer / larger / incumbent - the wedge scan's evidence-based size call
    No evidence, no label: an unlabelled rival is shown as "size unknown", not guessed.
    """
    scale_by_key = {_key(c.brand_name): c.scale for c in (report.wedge_scan.candidates if report.wedge_scan else [])}
    watch_by_key = {_key(e.brand_name): e for e in (report.threat_watch.watched if report.threat_watch else [])}
    counts: dict[str, int] = {}
    for c in report.competitors:
        k = _key(c.brand_name)
        scale = scale_by_key.get(k, "unknown")
        entry = watch_by_key.get(k)
        if c.leap_benchmark is not None:
            cohort = "leapfrog"
        elif entry is not None and entry.momentum == "accelerating" and scale not in ("incumbent", "larger"):
            cohort = "catching_up"
        elif scale in ("peer", "larger", "incumbent"):
            cohort = scale
        else:
            cohort = ""
        c.cohort = cohort
        counts[cohort or "unlabelled"] = counts.get(cohort or "unlabelled", 0) + 1
    return ["[THREAT_MONITOR] Cohorts: " + ", ".join(f"{n} {k}" for k, n in sorted(counts.items())) + "."]
