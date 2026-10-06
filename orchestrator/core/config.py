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
    # Crawl API for deep search: Firecrawl (preferred when set) or Crawlbase tokens below
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

    dqs_threshold: float = 0.80
    dqs_max_retries: int = 3
    # Attribute density gate for the research loop. Preliminary search-stage profiles carry
    # few structured attributes, so the default leaves density as a reported metric only.
    research_min_density: float = 0.0
    research_min_competitors: int = 4
    research_max_competitors: int = 8

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

    # When set, every /api request must send it in the X-API-Key header (the dev proxy injects it).
    api_access_key: str = Field(
        default="",
        validation_alias=AliasChoices("api_access_key", "API_ACCESS_KEY"),
    )

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
