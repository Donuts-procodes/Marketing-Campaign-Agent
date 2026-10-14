"""Campaign content: the assets written from an approved strategy, per channel, each approvable."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

#: Channel keys shared by content, scheduling and integrations.
ChannelKey = Literal["email", "linkedin", "instagram", "facebook", "meta_ads", "google_ads", "x", "whatsapp"]

AssetStatus = Literal["draft", "approved", "scheduled", "published", "failed"]


class ContentAsset(BaseModel):
    asset_id: str
    channel: ChannelKey
    kind: Literal["email", "post", "ad", "search_ad", "message"]
    name: str = Field(description="Short label, e.g. 'Email 1 · Launch announcement'")
    persona_id: str | None = None
    phase: str | None = Field(default=None, description="Strategy phase this belongs to")
    # Copy fields; each kind uses the ones it needs.
    subject: str | None = None
    preview_text: str | None = None
    body: str = ""
    headlines: list[str] = Field(default_factory=list, description="Search ads: up to 15 headlines of ≤30 chars")
    descriptions: list[str] = Field(default_factory=list, description="Search ads: up to 4 descriptions of ≤90 chars")
    cta: str | None = None
    landing_url: str | None = None
    creative_brief: str | None = Field(default=None, description="What the image or video should show")
    hashtags: list[str] = Field(default_factory=list)
    status: AssetStatus = "draft"
    scheduled_for: str | None = Field(default=None, description="ISO datetime in the campaign's timezone")
    external_id: str | None = Field(default=None, description="Id on the platform once published")
    error: str | None = None
    qa_issues: list[str] = Field(default_factory=list, description="Content QA findings to fix or accept before approving")
    revision: int = 1


class ContentPack(BaseModel):
    assets: list[ContentAsset] = Field(default_factory=list)
    approved_channels: list[ChannelKey] = Field(default_factory=list)
    generated_at: str | None = None
    notes: list[str] = Field(default_factory=list)

    def channels(self) -> list[str]:
        return list(dict.fromkeys(a.channel for a in self.assets))
