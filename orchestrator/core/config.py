from functools import lru_cache

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}

    openai_api_key: str = Field(
        default="",
        validation_alias=AliasChoices("openai_api_key", "OPENAI_API_KEY"),
    )
    tavily_api_key: str = Field(
        default="",
        validation_alias=AliasChoices(
            "tavily_api_key", "tavily_api", "TAVILY_API_KEY", "TAVILY_API"
        ),
    )
    you_api_key: str = Field(
        default="",
        validation_alias=AliasChoices(
            "you_api_key", "you_api", "YOU_API_KEY", "YOU_API"
        ),
    )
    # Crawl API for deep search: Scrape.do (preferred when set), Firecrawl or Crawlbase tokens below
    scrapedo_api_key: str = Field(
        default="79715dda747943419a8e6fc08dcfad52e24de495001",
        validation_alias=AliasChoices(
            "scrapedo_api_key", "scrapedo_token", "SCRAPEDO_API_KEY", "SCRAPEDO_TOKEN",
        ),
    )
    firecrawl_api_key: str = Field(
        default="",
        validation_alias=AliasChoices(
            "firecrawl_api_key", "firecrawl_api", "FIRECRAWL_API_KEY", "FIRECRAWL_API"
        ),
    )
    # Crawlbase Crawling API: normal token for static pages, JS token for rendered pages
    crawlapi_token: str = Field(
        default="",
        validation_alias=AliasChoices(
            "crawlapi_token", "CRAWLAPI_TOKEN", "CRAWLAPI_KEY", "CRAWLAPI_API_KEY", "CRAWLAPI",
            "CRAWLBASE_TOKEN", "CRAWLBASE_API_KEY",
        ),
    )
    crawlapi_js_token: str = Field(
        default="",
        validation_alias=AliasChoices(
            "crawlapi_js_token", "CRAWLAPI_JS_TOKEN", "CRAWLBASE_JS_TOKEN",
        ),
    )
    crawlapi_timeout_seconds: float = 90.0
    # Meta Ad Library API (graph.facebook.com/ads_archive); without it the public library page is crawled
    meta_access_token: str = Field(
        default="",
        validation_alias=AliasChoices(
            "meta_access_token", "META_ACCESS_TOKEN", "META_AD_LIBRARY_TOKEN", "FACEBOOK_ACCESS_TOKEN",
        ),
    )
    meta_graph_api_version: str = "v21.0"
    # Meta's API returns commercial (non-political) ads only for ads delivered in the EU/UK.
    meta_ad_reached_countries: str = "GB,DE,FR,IE,NL"

    # Ad libraries searched for competitor ads: any of meta, linkedin, google
    ad_library_platforms: str = "meta,linkedin,google"
    ad_library_country: str = "US"
    ad_library_max_competitors: int = 3

    llm_model: str = "gpt-4o"
    llm_temperature: float = 0.1
    # Smaller OpenAI model retried when the main model call fails (errors, rate limits, outages).
    # Empty disables the fallback.
    llm_fallback_model: str = "gpt-4o-mini"
    # Lighter model for classification, taxonomy, category fit and dashboard curation. Report
    # synthesis, the validator and the chat stay on llm_model. Empty uses llm_model everywhere.
    llm_fast_model: str = "gpt-4o-mini"

    tavily_search_depth: str = "advanced"
    tavily_max_results: int = 15

    # DuckDuckGo (no key): "fallback" runs it for queries where Tavily/You.com fail or return
    # fewer than duckduckgo_min_results; "always" adds it to every query; "off" disables it.
    duckduckgo_mode: str = "fallback"
    duckduckgo_min_results: int = 5
    duckduckgo_max_results: int = 10
    duckduckgo_region: str = "us-en"
    # Deep search: pages scraped per research round (CrawlAPI first, Tavily Extract fallback)
    # Pages deep-scraped per run. At 10, a run that discovers ~100 URLs across ~10
    # competitor sites gets roughly one page each -- rarely the one carrying pricing,
    # which is what held P_pricing (and so DQS) down. Each page is one crawl API call.
    deep_search_max_pages: int = 24
    # Pages fetched in parallel. A measured run spent 155s of its 258s in deep crawl: 19 pages
    # at 3-at-a-time is 7 sequential waves. These are the two nested limits -- the crawler's own
    # gate and Firecrawl's process-wide one, whichever is lower binds. Raise to match your
    # Firecrawl plan's per-minute allowance; 429s are retried (_FIRECRAWL_RETRIES) so an
    # overshoot degrades into backoff rather than failure.
    crawl_max_concurrent: int = 10
    # Per-page limit for competitor page crawls (ad-library fetches keep crawlapi_timeout_seconds).
    crawl_page_timeout_seconds: float = 30.0
    firecrawl_max_concurrent: int = 10

    dqs_threshold: float = 0.90
    dqs_max_retries: int = 3
    # Targeted research rounds the validator may send back for the gaps it names. Each costs a
    # search, a short crawl and one more validator call; 0 keeps the validator review-only.
    validator_max_rounds: int = 1
    # Attribute density gate for the research loop. Preliminary search-stage profiles carry
    # few structured attributes, so the default leaves density as a reported metric only.
    research_min_density: float = 0.0
    research_min_competitors: int = 5
    # Competitors promoted into the report. The rest stay on the bench: discovered, listed and
    # saved, but not deep-crawled until the merchant asks for more. 0 means no limit, which also
    # leaves the bench permanently empty.
    research_max_competitors: int = 5
    # Rivals the merchant names are researched IN ADDITION to the research_max_competitors the
    # agent discovers itself; they never use up discovery slots. Capped so a 20-name list
    # cannot multiply the cost of a run; names past the cap wait on the bench for "find more".
    research_max_named_competitors: int = 10
    # Deep crawl is competitor-targeted, not URL-targeted. Spraying one page each across every
    # host that appeared in search left pricing at 0/48, because a competitor's single scraped
    # page was almost never their pricing page. These concentrate the same page budget on the
    # shortlist: 5 competitors x 4 pages fetches each one's home, pricing and feature pages.
    research_deep_crawl_competitors: int = 5
    # Tier 1 wedge scan: a cheap, broad sweep for every player in the merchant's niche,
    # including brands that launched recently and only show up on launch platforms and forums.
    # Costs three searches and one light LLM call per run. Off skips the scan entirely.
    wedge_scan_enabled: bool = True
    wedge_max_candidates: int = 25
    # Tier 2 threat watch: how many peer-scale rivals get momentum tracking between scans.
    threat_watch_size: int = 5
    # Profile completion: searches for each rival's missing facts (price, rating, reviews,
    # founded, HQ, team size, revenue, funding) and keeps only values whose source sentence is
    # verified on a fetched page. Per round: up to 4 searches and N page fetches per rival.
    profile_completion_enabled: bool = True
    profile_completion_rounds: int = 2
    profile_pages_per_competitor: int = 3
    # Max "alternatives to the leaders" search passes before the shortlist is locked; stops
    # earlier once a pass adds no new name to the top 10.
    research_discovery_iterations: int = 3
    research_pages_per_competitor: int = 4

    # Dated evidence older than this counts as stale in the DQS recency dimension.
    # Evidence with no discoverable date is never counted as stale.
    recency_max_age_days: int = 548  # ~18 months
    # Convergence floor for R_recency. At 0.15 weight, recency alone cannot pull DQS under
    # the threshold, so the loop gates on it directly: when most *dated* evidence is stale,
    # research iterates again rather than passing it off as current. Undated evidence scores
    # 1.0, so this only bites on verifiable staleness.
    research_min_recency: float = 0.5

    # BYOK custom endpoints make the server call user-supplied hosts; off unless trusted.
    allow_custom_llm_endpoints: bool = False

    # In-memory job store limits
    job_ttl_seconds: int = 3600
    max_jobs: int = 500
    # Each run spends paid API credits: cap how many research runs execute at once.
    max_running_jobs: int = 3

    # MongoDB keeps finished runs (report + event history) across restarts; empty disables it.
    mongo_url: str = Field(default="", validation_alias=AliasChoices("mongo_url", "MONGO_URL"))
    mongo_db: str = "marketing"
    # Redis rate-limits run creation (sliding window, shared by all workers); empty disables it.
    redis_url: str = Field(default="", validation_alias=AliasChoices("redis_url", "REDIS_URL"))
    max_jobs_per_hour: int = 20
    # Report chat: messages per client per hour, and how much of the report goes into its prompt.
    max_chat_messages_per_hour: int = 120
    max_chat_context_chars: int = 60_000

    # When set, every /api request must send it in the X-API-Key header (the dev proxy injects it).
    api_access_key: str = Field(
        default="",
        validation_alias=AliasChoices("api_access_key", "API_ACCESS_KEY"),
    )

    # Synthesis prompt budget. The research loop accumulates results across every retry round,
    # so an unconverged run reached ~367 results / 30 pages and overflowed the model's context
    # window, losing the whole SWOT. These cap the evidence corpus; selection is prioritized by
    # vector rather than truncated, so breadth of coverage survives the cut.
    max_synthesis_snippet_chars: int = 160_000
    max_synthesis_page_chars: int = 90_000
    max_synthesis_page_excerpt_chars: int = 3_000

    # Dossier ingestion limits
    max_dossier_bytes: int = 15 * 1024 * 1024
    max_dossier_prompt_chars: int = 6000
    # Multi-file uploads (dossiers and autofill): file count, and document text sent to the autofill LLM.
    max_upload_files: int = 10
    max_autofill_chars: int = 40000

    # Shared secret required by agent microservices on /execute (empty disables the check)
    agent_service_token: str = ""

    # Agent Microservice URLs (empty string triggers in-process execution fallback)
    market_research_service_url: str = ""
    audience_persona_service_url: str = ""
    campaign_strategy_service_url: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()
