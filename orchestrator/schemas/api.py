"""
Pydantic v2 DTOs for Campaign HTTP Ingress and Egress contracts.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal
from pydantic import BaseModel, ConfigDict, Field

from orchestrator.schemas.research import CompetitorProfile, SWOTReportDelta
from orchestrator.schemas.strategy import CampaignStrategyBrief


# Request size limits: the API is a trust boundary and every field ends up in memory and in LLM prompts.
ShortText = Annotated[str, Field(max_length=300)]
LongText = Annotated[str, Field(max_length=4000)]
MAX_LIST_ITEMS = 20
MAX_DOSSIER_CHARS = 200_000


class BYOKConfig(BaseModel):
    provider: Literal["openai", "anthropic", "gemini"]
    model: ShortText
    api_key: Annotated[str, Field(max_length=500)]
    custom_endpoint: Annotated[str, Field(max_length=500)] | None = None


class MerchantProduct(BaseModel):
    """One product in the merchant's line. Competitor prices are looked up and compared per product."""

    name: ShortText
    category: ShortText | None = Field(default=None, description="e.g. 'formal leather shoes', 'running sneakers'")
    price: float | None = Field(default=None, ge=0, description="Planned selling price, in `currency`")
    mrp: float | None = Field(default=None, ge=0, description="List/MRP price, in `currency`")


class MerchantContextInput(BaseModel):
    product_name: ShortText
    category: ShortText
    primary_value_prop: LongText
    goal: LongText | None = None
    price_usd: float | None = None
    price: float | None = Field(default=None, ge=0, description="Product selling price, in `currency`")
    products: list[MerchantProduct] = Field(
        default_factory=list,
        max_length=MAX_LIST_ITEMS,
        description="The product line being launched. Empty means the single product above.",
    )
    known_competitors: list[ShortText] = Field(default_factory=list, max_length=MAX_LIST_ITEMS)
    existing_customer_profiles: list[ShortText] = Field(default_factory=list, max_length=MAX_LIST_ITEMS)
    dossier: Annotated[str, Field(max_length=MAX_DOSSIER_CHARS)] | None = None
    campaign_type: ShortText | None = Field(
        default=None,
        description="Campaign type: e.g. brand_launch, product_launch, lead_gen, competitor_takeover, ecommerce_sales, rebrand",
    )
    business_model: ShortText | None = Field(
        default=None,
        description="Business model: e.g. b2b_saas, d2c_ecommerce, local_service, professional_services, mobile_app, creator_infoproduct",
    )
    target_geography: ShortText | None = Field(
        default=None,
        description="Target market or service area: e.g. 'United States', 'Global', 'Austin, TX'",
    )
    price_model: ShortText | None = Field(
        default=None,
        description="Pricing structure: e.g. monthly_subscription, one_time, hourly_rate, retainer, usage_based, free_quote",
    )
    budget: float | None = Field(
        default=None,
        description="Campaign budget, in `currency`",
    )
    currency: Annotated[str, Field(max_length=3)] | None = Field(
        default=None,
        description="ISO currency code of the budget and prices, e.g. 'INR'. Inferred from the market when omitted.",
    )
    launch_stage: Literal["pre_launch", "launched_few_sales", "regular_orders"] | None = Field(
        default=None, description="Where the business is today; decides validate vs scale planning"
    )
    sales_channel: ShortText | None = Field(
        default=None, description="Where customers buy: own site, Instagram/WhatsApp, marketplace, offline"
    )
    unit_cost: float | None = Field(
        default=None, ge=0, description="Product + fulfilment cost per unit, in `currency`; enables break-even"
    )
    stock_ready: bool | None = Field(default=None, description="Inventory and sizes ready to sell")
    campaign_days: int | None = Field(
        default=None,
        ge=3,
        le=365,
        description="Desired campaign duration in days (e.g. 14, 30, 60, 90, 180)",
    )
    sub_goals: list[ShortText] = Field(
        default_factory=list,
        max_length=MAX_LIST_ITEMS,
        description="Specific target sub-goals or milestones",
    )


class PriorRunInfo(BaseModel):
    """Returned by GET /campaigns/prior-run when a completed run exists for the same product."""

    found: bool
    job_id: str | None = None
    finished_at: str | None = None
    dqs_score: float | None = None
    competitor_count: int | None = None


class CampaignCreate(BaseModel):
    merchant_context: MerchantContextInput
    byok_config: BYOKConfig | None = None
    run_mode: Literal["fresh", "update"] = "fresh"


class CampaignCreateResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    job_id: str
    status: str


class UploadedFileInfo(BaseModel):
    filename: str
    characters: int


class DossierUploadResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    status: str
    characters: int
    filename: str  # comma-joined names, kept for older clients
    files: list[UploadedFileInfo] = Field(default_factory=list)


class AutofillFields(BaseModel):
    """Campaign form fields read from uploaded documents; None / empty when a document does not state it."""

    product_name: str | None = Field(default=None, description="The merchant's own product or brand name, as written in the documents")
    category: str | None = Field(default=None, description="Product category or industry")
    primary_value_prop: str | None = Field(default=None, description="Main value proposition, close to the documents' wording")
    goal: str | None = Field(default=None, description="Stated business or campaign goal")
    price_usd: float | None = Field(default=None, description="Product price in USD, only if a USD price is stated")
    price: float | None = Field(default=None, description="Flagship product price as stated, in `currency`")
    currency: str | None = Field(default=None, description="ISO code of the stated price, e.g. 'INR' for ₹")
    known_competitors: list[str] = Field(default_factory=list, description="Competitor names mentioned in the documents")
    existing_customer_profiles: list[str] = Field(default_factory=list, description="Target customer types mentioned")
    target_geography: str | None = Field(default=None, description="Target market, city, region, or country (e.g. 'Delhi', 'Austin, TX', 'United States', or 'Global')")


class AutofillResponse(BaseModel):
    fields: AutofillFields
    filled: list[str]  # names of the fields that were found
    files: list[UploadedFileInfo]


class SessionSummary(BaseModel):
    job_id: str
    status: str
    label: str | None = None
    finished_at: str | None = None
    product_name: str | None = None
    category: str | None = None


class SessionListResponse(BaseModel):
    sessions: list[SessionSummary]


class SessionDetailResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    job_id: str
    status: str
    label: str | None = None
    finished_at: str | None = None
    merchant_context: dict = Field(default_factory=dict)
    swot_report: SWOTReportDelta | None = None
    strategy_brief: CampaignStrategyBrief | None = None
    events: list[dict] = Field(default_factory=list)


class InterpretQueryInput(BaseModel):
    """Free-form user text to interpret into structured merchant context fields."""

    text: Annotated[str, Field(max_length=4000)]


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: Annotated[str, Field(min_length=1, max_length=4000)]


class ReportChatInput(BaseModel):
    """A conversation about one run's report; the last message is the user's question."""

    messages: Annotated[list[ChatMessage], Field(min_length=1, max_length=40)]
    step: Literal["brief", "research", "strategy", "content", "schedule", "live"] | None = Field(
        default=None, description="The workspace step the merchant is on; answers follow it"
    )
    focus_asset_id: Annotated[str, Field(max_length=40)] | None = Field(
        default=None, description="The content asset open on screen, if any"
    )


EditableField = Literal[
    "core_claims", "weaknesses_mined", "strengths_mined", "ad_hooks", "factual_evidence", "milestones"
]


class ReportEdit(BaseModel):
    """One merchant correction to a finished report."""

    op: Literal["remove_item", "set_price", "set_rating", "remove_competitor"]
    competitor: ShortText
    field: EditableField | None = None
    value: Annotated[str, Field(max_length=2000)] | None = None


class ReportEditInput(BaseModel):
    edits: Annotated[list[ReportEdit], Field(min_length=1, max_length=20)]


class ReportEditResponse(BaseModel):
    applied: list[str]
    swot_report: SWOTReportDelta


class MoreCompetitorsInput(BaseModel):
    """Optional: research these named competitors instead of the next ones found."""

    names: Annotated[list[ShortText], Field(max_length=5)] = Field(default_factory=list)


class RenameSessionInput(BaseModel):
    label: ShortText


class ResolveInterruptInput(BaseModel):
    checkpoint_id: ShortText
    action: Literal["APPROVED", "REVISED"]
    feedback: LongText | None = None


class ResolveInterruptResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    status: str


class MoreCompetitorsResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    status: str
    added_competitors: list[CompetitorProfile]
    total_competitors: int
    swot_report: SWOTReportDelta


class ReResearchResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    status: str
    swot_report: SWOTReportDelta


class AgentDescriptor(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    agent_id: str
    name: str
    description: str
    service_endpoint: str
    port: int
    models: list[str]
    tools: list[str]
    capabilities: list[str]
    input_contract: str
    output_contract: str
    status: str = "operational"


class AgentListResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    agents: list[AgentDescriptor]


class UpdateContextInput(BaseModel):
    field: ShortText
    value: Any
    reasoning: LongText | None = None


class UpdateContextResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    status: str = "ACCEPTED"
    field: str
    value: Any
    applied: str
    merchant_context: dict[str, Any]

