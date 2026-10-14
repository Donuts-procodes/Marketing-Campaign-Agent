"""
Static Promotion Channels and Promotional Means Knowledge Base.

Provides deterministic, battle-tested promotion channels, tactical promotional means,
lead magnets, and conversion vehicles tailored to business models and campaign archetypes.
Ensures zero-downtime, predictable recommendations even under network or search latency.
"""

from __future__ import annotations

from typing import Any


STATIC_CHANNEL_TAXONOMY: dict[str, dict[str, Any]] = {
    "b2b_saas": {
        "channels": [
            "LinkedIn Sponsored Content & Document Ads",
            "Google Search Ads (Conquest & High-Intent Solution Queries)",
            "Account-Based Cold Email Outbound (Clay/Apollo)",
            "Dynamic Meta & Display Retargeting",
            "Niche Category Newsletters & Technical Communities",
        ],
        "promotion_means": [
            "Interactive Migration & Payback ROI Calculator",
            "Free 30-Minute Architecture & Code Audit (Proof of Concept)",
            "Rival Switcher Rebate (Up to $1,500 onboarding credit)",
            "Ungated Category Benchmark Report & Architecture Teardown",
            "Zero-Commitment 14-Day Pilot with SLA Guarantees",
            "Executive 1-on-1 Strategy Session with Founder / Lead Engineer",
        ],
        "tactics_by_channel": {
            "linkedin": [
                "Sponsored document carousel teardowns comparing old vs modern architecture",
                "Executive thought leadership posts citing industry benchmark data",
                "Direct InMail outreach inviting decision-makers to interactive audits",
            ],
            "search": [
                "Conquest bidding on rival brand keywords ('rival alternative', 'switch from rival')",
                "High-intent solution problem terms with dedicated comparison landing pages",
                "Ad copy highlighting zero lock-in contracts and transparent pricing",
            ],
            "email": [
                "Hyper-personalized 4-step cold outreach to verified switch candidate accounts",
                "Interactive case study teardowns demonstrating 3x velocity improvement",
                "Automated nurture drip triggered on comparison page visitors",
            ],
            "retarget": [
                "Dynamic social proof video testimonials targeted at pricing page drop-offs",
                "Feature-gap checklist ad creatives highlighting what rivals lack",
                "Limited-time evaluation extension offer for engaged demo visitors",
            ],
            "content": [
                "In-depth competitor alternative landing pages with feature-by-feature teardowns",
                "Search-optimized migration guides ('How to migrate away from legacy provider')",
                "Interactive self-service ROI and payback calculator widget",
            ],
        },
    },
    "professional_services": {
        "channels": [
            "LinkedIn Executive Thought Leadership & InMail",
            "Google Search Ads (Commercial Intent & Local/Global RFP Queries)",
            "Curated Outbound Account Sequences",
            "Retargeting Comparison Case Studies",
            "Industry Association Directories & Sponsorships",
        ],
        "promotion_means": [
            "Free 48-Hour Technical Feasibility & Architecture Teardown",
            "Milestone-Guaranteed Delivery SLA (Zero Slippage Penalty)",
            "Competitor Contract Buyout Credit ($1,000 - $2,500 credit)",
            "Detailed Client ROI & Sprint Velocity Case Study Dossier",
            "Free 1-on-1 Discovery Strategy Session with Senior Partners",
            "Fixed-Price Rapid Prototyping Pilot (2-Week Sprint)",
        ],
        "tactics_by_channel": {
            "linkedin": [
                "Partner-level breakdown of successful enterprise digital transformation sprints",
                "Sponsored video clips highlighting real client metrics and deployment velocity",
                "Direct messaging to CTOs and VP Engineers with tailored teardown insights",
            ],
            "email": [
                "Multi-touch account-based outreach offering targeted technology audits",
                "Quarterly industry benchmarking trends report sent to key decision-makers",
                "Direct invite to exclusive peer roundtables on enterprise modernizations",
            ],
            "retarget": [
                "Case-study video proof retargeted to visitors of service capability pages",
                "Customer testimonial spotlight ads addressing common migration anxieties",
                "Limited-capacity onboarding announcement for upcoming quarter",
            ],
            "search": [
                "High-intent keyword matching for custom enterprise software development",
                "Comparison search ad copy targeting dissatisfaction with legacy consultancies",
                "Direct links to verified portfolio showcases and client testimonials",
            ],
            "content": [
                "Deep-dive technical architectural blueprints and migration frameworks",
                "Cost comparison guides: Agency Retainer vs. Modern Dedicated Sprint Teams",
                "Public interactive code-audit checklist and evaluation rubric",
            ],
        },
    },
    "d2c_ecommerce": {
        "channels": [
            "Meta (Instagram & Facebook) Video & Carousel Ads",
            "Google Shopping & Performance Max",
            "TikTok Creator Collaborations & Spark Ads",
            "Klaviyo Automated Email/SMS Retention Flows",
            "Influencer Co-Branded Unboxing Campaigns",
        ],
        "promotion_means": [
            "First-Order Starter Bundle (20% off + Free Expedited Shipping)",
            "Risk-Free 30-Day Money-Back Guarantee with Prepaid Return Label",
            "Interactive Product Matcher / Fitment Diagnostic Quiz",
            "Buy One, Gift One / Tiered Volume Savings Structure",
            "VIP Early Access Drop for SMS Club Subscribers",
            "Customer UGC Video Review Incentive ($15 store credit)",
        ],
        "tactics_by_channel": {
            "retarget": [
                "Cart abandonment dynamic product ads with personalized discount code",
                "Urgency-driven inventory alerts on browsed category items",
                "UGC unboxing video ads showing real customer transformations",
            ],
            "search": [
                "Google Shopping feed optimization for high-margin SKU clusters",
                "Exact-match product title bidding against competing store brands",
                "Sitelink extensions highlighting free returns and verified 5-star ratings",
            ],
            "email": [
                "3-part automated welcome sequence with progressive incentive unlocks",
                "Browse abandonment trigger offering matching accessory recommendations",
                "Post-purchase satisfaction check-in and VIP loyalty points invitation",
            ],
            "content": [
                "Viral-format unboxing tutorials and comparison side-by-sides",
                "Seasonal gift guides and best-in-category editorial listicles",
                "Interactive visual style / shade / size quiz",
            ],
            "linkedin": [
                "Corporate gifting and B2B wholesale bulk order campaigns",
                "Brand founder storytelling and sustainable sourcing spotlights",
                "Partnership announcements with retail distributors",
            ],
        },
    },
    "general": {
        "channels": [
            "Google Search Ads (High-Intent Solution Queries)",
            "LinkedIn Sponsored Updates & Document Teardowns",
            "Targeted Outbound Email Campaigns",
            "Dynamic Conversion Retargeting (Meta / Google Display)",
            "Authority Content & Comparison Landing Pages",
        ],
        "promotion_means": [
            "Free Comprehensive Diagnostic / Strategy Evaluation Session",
            "Interactive Payback & Value Realization Calculator",
            "Guaranteed Milestone SLA or Full Refund Commitment",
            "Competitor Switcher Onboarding Concierge & Migration Credit",
            "Ungated Category Playbook & Technical Blueprint",
            "Limited-Availability Pilot Cohort with Direct Founder Access",
        ],
        "tactics_by_channel": {
            "search": [
                "Targeting commercial intent keywords with high conversion propensity",
                "Competitor conquest search ads driving to side-by-side comparison tables",
                "Ad extensions featuring customer rating badges and instant booking links",
            ],
            "linkedin": [
                "Targeted job-title and industry seniority account lists",
                "Educational carousel ads outlining category pitfalls and solutions",
                "Direct lead gen forms with 1-click submission and instant resource download",
            ],
            "email": [
                "Personalized 3-step value sequence addressing top 3 industry pain points",
                "Relevant case study teardown demonstrating measurable client ROI",
                "Low-friction call to action offering a free 15-minute diagnostic review",
            ],
            "retarget": [
                "Sequential retargeting ads highlighting features, proof, and urgency",
                "Overcoming objections: security, compliance, and onboarding ease",
                "Final call-to-action incentive before campaign cohort closes",
            ],
            "content": [
                "Search-grounded buyer guide: What to evaluate before purchasing",
                "Competitor comparison landing pages with transparent feature matrices",
                "Customer success video stories detailing measurable outcomes",
            ],
        },
    },
}


def get_static_promotions(
    business_model: str = "",
    campaign_type: str = "",
    category: str = "",
) -> dict[str, Any]:
    """
    Returns static, deterministic promotion channels, means of promotion,
    and channel tactics tailored to the detected business archetype.
    """
    key = "general"
    bm = (business_model or "").lower()
    cat = (category or "").lower()

    if "saas" in bm or "software" in cat or "platform" in cat:
        key = "b2b_saas"
    elif "service" in bm or "development" in cat or "agency" in cat or "consulting" in cat:
        key = "professional_services"
    elif "ecommerce" in bm or "d2c" in bm or "retail" in cat:
        key = "d2c_ecommerce"

    data = STATIC_CHANNEL_TAXONOMY.get(key) or STATIC_CHANNEL_TAXONOMY["general"]
    return {
        "suggested_channels": list(data["channels"]),
        "promotion_means": list(data["promotion_means"]),
        "tactics_by_channel": {k: list(v) for k, v in data["tactics_by_channel"].items()},
    }


def get_option_promotions(
    option_id: str,
    top_competitor: str,
    category: str,
) -> tuple[list[str], list[str]]:
    """
    Provides static, specialized promotion channels and means of promotion
    for each comparative strategy option.
    """
    comp = top_competitor or "Incumbent Competitors"
    cat = category or "Digital Solutions"

    if option_id == "opt_disrupter":
        channels = [
            "LinkedIn Sponsored Updates & InMail",
            "Google Search Ads (Conquest Keywords)",
            "Targeted Cold Outbound (Clay / Apollo)",
            "Competitor Teardown Landing Pages",
        ]
        means = [
            f"Switcher Onboarding Rebate (Up to $1,500 credit toward {cat} setup)",
            f"Free 48-Hour Architecture & Migration Audit comparing against {comp}",
            "Zero-Downtime Guarantee with SLA Penalty Protection",
            f"Side-by-Side {comp} Feature & Cost Transparency Calculator",
            "Dedicated 1-on-1 Migration Architect Onboarding Concierge",
        ]
    elif option_id == "opt_search_harvester":
        channels = [
            "Google Search Ads (High-Intent Solution Queries)",
            "Dynamic Retargeting (Meta & Google Display)",
            "Automated Comparative Email Sequences",
            "Category Comparison SEO Hubs",
        ]
        means = [
            "Instant Online ROI & Payback Timeline Calculator",
            "Interactive Self-Guided Solution Walkthrough & Sandbox",
            "Instant Transparent Scope & Pricing Quote Estimator",
            "Limited-Time Fast-Track Sprint Priority Slot",
            "Ungated Category Benchmark Teardown PDF",
        ]
    else:  # opt_abm_authority
        channels = [
            "High-Authority Industry Benchmark Reports",
            "LinkedIn Executive Thought Leadership & Carousels",
            "Direct Executive Account Outbound Sequences",
            "Exclusive Technical Webinars & Virtual Roundtables",
        ]
        means = [
            "1-on-1 Founder / Principal Architect Technical Strategy Session",
            f"Ungated 2026 {cat} Industry Benchmark & Architecture Teardown",
            "Tailored Enterprise Proof of Concept (PoC) Blueprint",
            "Invitation-Only Executive Roundtables on Modern Engineering Velocity",
            "Custom Executive Board-Ready Transformation Dossier",
        ]

    return channels, means
