"""
Pydantic v2 DTOs for Campaign HTTP Ingress and Egress contracts.
"""

from __future__ import annotations

from typing import Annotated, Literal
from pydantic import BaseModel, ConfigDict, Field

from orchestrator.schemas.research import CompetitorProfile, SWOTReportDelta


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


class MerchantContextInput(BaseModel):
    product_name: ShortText
    category: ShortText
    primary_value_prop: LongText
    goal: LongText | None = None
    price_usd: float | None = None
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


class CampaignCreate(BaseModel):
    merchant_context: MerchantContextInput
    byok_config: BYOKConfig | None = None


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
    known_competitors: list[str] = Field(default_factory=list, description="Competitor names mentioned in the documents")
    existing_customer_profiles: list[str] = Field(default_factory=list, description="Target customer types mentioned")


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

