export type ChannelKey = "email" | "linkedin" | "instagram" | "facebook" | "meta_ads" | "google_ads" | "x" | "whatsapp";
export type AssetStatus = "draft" | "approved" | "scheduled" | "published" | "failed";

export interface ContentAsset {
  asset_id: string;
  channel: ChannelKey;
  kind: "email" | "post" | "ad" | "search_ad" | "message";
  name: string;
  persona_id?: string | null;
  phase?: string | null;
  subject?: string | null;
  preview_text?: string | null;
  body: string;
  headlines: string[];
  descriptions: string[];
  cta?: string | null;
  landing_url?: string | null;
  creative_brief?: string | null;
  hashtags: string[];
  status: AssetStatus;
  scheduled_for?: string | null;
  external_id?: string | null;
  error?: string | null;
  qa_issues: string[];
  revision: number;
}

export interface ContentPack {
  assets: ContentAsset[];
  approved_channels: ChannelKey[];
  generated_at?: string | null;
  notes: string[];
}

export const CHANNEL_LABEL: Record<ChannelKey, string> = {
  email: "Email",
  linkedin: "LinkedIn",
  instagram: "Instagram",
  facebook: "Facebook",
  meta_ads: "Meta Ads",
  google_ads: "Google Ads",
  x: "X",
  whatsapp: "WhatsApp",
};
