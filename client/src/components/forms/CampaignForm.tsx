import { useEffect, useState } from "react";
import {
  AVAILABLE_MODELS,
  BYOKConfig,
  BYOKProvider,
  CampaignInitPayload,
  MerchantContext,
} from "@/types/api";
import { DossierUpload } from "./DossierUpload";
import { autofillFromFiles } from "@/lib/api-client";
import {
  Sparkles,
  KeyRound,
  Eye,
  EyeOff,
  Cpu,
  Layers,
  ArrowRight,
  ShieldCheck,
  Bookmark,
  Check,
  Trash2,
} from "lucide-react";
import { cn } from "@/lib/utils";

interface CampaignFormProps {
  onSubmit: (payload: CampaignInitPayload, dossiers: File[]) => Promise<void>;
  isLoading: boolean;
}

// Remembered BYOK key, kept only in this browser (localStorage), never sent anywhere but your own runs.
const BYOK_STORAGE_KEY = "intelly.byok";

function loadSavedByok(): { provider: BYOKProvider; model: string; apiKey: string } | null {
  try {
    const raw = localStorage.getItem(BYOK_STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    if (parsed && typeof parsed.apiKey === "string" && parsed.apiKey) return parsed;
  } catch {
    // localStorage can be unavailable (private mode, blocked storage) — just skip.
  }
  return null;
}

export function CampaignForm({ onSubmit, isLoading }: CampaignFormProps) {
  // Merchant State
  const [productName, setProductName] = useState("");
  const [category, setCategory] = useState("");
  const [primaryValueProp, setPrimaryValueProp] = useState("");
  const [goal, setGoal] = useState("");
  const [priceUsd, setPriceUsd] = useState<string>("");
  const [knownCompetitorsInput, setKnownCompetitorsInput] = useState("");
  const [customerProfilesInput, setCustomerProfilesInput] = useState("");

  // BYOK State
  const [enableByok, setEnableByok] = useState(false);
  const [selectedProvider, setSelectedProvider] = useState<BYOKProvider>("openai");
  const [selectedModel, setSelectedModel] = useState("gpt-4o");
  const [apiKey, setApiKey] = useState("");
  const [showApiKey, setShowApiKey] = useState(false);
  const [keySaved, setKeySaved] = useState(false);

  // Restore a key saved on this device, so it is remembered across visits.
  useEffect(() => {
    const saved = loadSavedByok();
    if (saved) {
      setEnableByok(true);
      setSelectedProvider(saved.provider);
      setSelectedModel(saved.model);
      setApiKey(saved.apiKey);
      setKeySaved(true);
    }
  }, []);

  const handleSaveKey = () => {
    try {
      localStorage.setItem(
        BYOK_STORAGE_KEY,
        JSON.stringify({ provider: selectedProvider, model: selectedModel, apiKey: apiKey.trim() })
      );
      setKeySaved(true);
    } catch {
      setKeySaved(false);
    }
  };

  const handleClearSavedKey = () => {
    try {
      localStorage.removeItem(BYOK_STORAGE_KEY);
    } catch {
      // ignore
    }
    setApiKey("");
    setKeySaved(false);
  };

  // Document uploads: used for autofill and attached to the run as dossiers
  const [dossierFiles, setDossierFiles] = useState<File[]>([]);
  const [isAutofilling, setIsAutofilling] = useState(false);
  const [autofillNotice, setAutofillNotice] = useState<{ ok: boolean; text: string } | null>(null);

  // Fills only fields that are still empty, so nothing the user typed is overwritten.
  const handleAutofill = async () => {
    setIsAutofilling(true);
    setAutofillNotice(null);
    try {
      const { fields } = await autofillFromFiles(dossierFiles);
      const filled: string[] = [];
      const fill = (label: string, current: string, value: string | null | undefined, set: (v: string) => void) => {
        if (value && !current.trim()) {
          set(value);
          filled.push(label);
        }
      };
      fill("product name", productName, fields.product_name, setProductName);
      fill("category", category, fields.category, setCategory);
      fill("value proposition", primaryValueProp, fields.primary_value_prop, setPrimaryValueProp);
      fill("goal", goal, fields.goal, setGoal);
      fill("price", priceUsd, fields.price_usd != null ? String(fields.price_usd) : null, setPriceUsd);
      fill("competitors", knownCompetitorsInput, fields.known_competitors.join(", "), setKnownCompetitorsInput);
      fill("customer profiles", customerProfilesInput, fields.existing_customer_profiles.join(", "), setCustomerProfilesInput);
      setAutofillNotice(
        filled.length
          ? { ok: true, text: `Filled from your documents: ${filled.join(", ")}. Review before launching.` }
          : { ok: true, text: "No empty fields could be filled: the documents do not state them, or you already filled them." }
      );
    } catch (err: unknown) {
      setAutofillNotice({ ok: false, text: `Autofill failed: ${err instanceof Error ? err.message : "unknown error"}` });
    } finally {
      setIsAutofilling(false);
    }
  };

  const handleProviderChange = (provider: BYOKProvider) => {
    setSelectedProvider(provider);
    const models = AVAILABLE_MODELS[provider];
    const recommended = models.find((m) => m.recommended) || models[0];
    setSelectedModel(recommended.id);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    const competitorsList = knownCompetitorsInput
      .split(",")
      .map((c) => c.trim())
      .filter((c) => c.length > 0);

    const profilesList = customerProfilesInput
      .split(",")
      .map((p) => p.trim())
      .filter((p) => p.length > 0);

    const merchant_context: MerchantContext = {
      product_name: productName.trim(),
      category: category.trim(),
      primary_value_prop: primaryValueProp.trim(),
      goal: goal.trim() || undefined,
      price_usd: priceUsd ? parseFloat(priceUsd) : undefined,
      known_competitors: competitorsList.length > 0 ? competitorsList : undefined,
      existing_customer_profiles: profilesList.length > 0 ? profilesList : undefined,
    };

    let byok_config: BYOKConfig | undefined = undefined;
    if (enableByok && apiKey.trim()) {
      byok_config = {
        provider: selectedProvider,
        model: selectedModel,
        api_key: apiKey.trim(),
      };
    }

    await onSubmit({ merchant_context, byok_config }, dossierFiles);
  };

  const modelsForCurrentProvider = AVAILABLE_MODELS[selectedProvider];

  return (
    <form onSubmit={handleSubmit} className="space-y-8 select-none">
      {/* Top Banner with Quick Fill */}
      <div className="flex flex-wrap items-center justify-between gap-4 p-4 rounded-[24px] bg-[#FAF7EE] border border-[#EDE7D8]">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-full bg-[#F8B4D9] text-[#3D102A] flex items-center justify-center shrink-0">
            <Sparkles className="w-4 h-4" />
          </div>
          <div>
            <h4 className="text-xs font-bold text-[#19191B]">
              Strategy Intake Blueprint
            </h4>
            <p className="text-[11px] text-zinc-500">
              Upload your documents to autofill the form, or type the details below.
            </p>
          </div>
        </div>
        <DossierUpload files={dossierFiles} onFilesChange={setDossierFiles} disabled={isLoading || isAutofilling} />
        <div className="flex flex-wrap items-center gap-3 w-full">
          <button
            type="button"
            onClick={handleAutofill}
            disabled={dossierFiles.length === 0 || isAutofilling || isLoading}
            className={cn(
              "inline-flex items-center gap-1.5 px-4 py-2 rounded-full text-xs font-bold border transition shadow-xs",
              dossierFiles.length === 0 || isAutofilling || isLoading
                ? "bg-zinc-100 text-zinc-400 border-zinc-200 cursor-not-allowed"
                : "bg-[#FDE583] hover:bg-[#F8D24E] text-[#2D2306] border-[#FDE583] cursor-pointer"
            )}
          >
            {isAutofilling ? (
              <div className="w-3.5 h-3.5 border-2 border-[#2D2306]/30 border-t-[#2D2306] rounded-full animate-spin" />
            ) : (
              <Sparkles className="w-3.5 h-3.5" />
            )}
            {isAutofilling ? "Reading documents..." : "Autofill form from files"}
          </button>
          {autofillNotice && (
            <span role="status" className={cn("text-[11px] font-medium", autofillNotice.ok ? "text-[#19350E]" : "text-rose-600")}>
              {autofillNotice.text}
            </span>
          )}
        </div>
      </div>

      {/* Section 1: Merchant & Product Context */}
      <div className="space-y-4">
        <div className="flex items-center gap-2 border-b border-[#EDE7D8] pb-2">
          <Layers className="w-4 h-4 text-[#19191B]" />
          <h3 className="text-xs font-bold uppercase tracking-wider text-[#19191B]">
            1. Product Specification
          </h3>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div className="space-y-1.5">
            <label className="text-xs font-bold text-[#19191B]">
              Product Name <span className="text-rose-500">*</span>
            </label>
            <input
              type="text"
              required
              value={productName}
              onChange={(e) => setProductName(e.target.value)}
              placeholder="e.g. ErgoMouse V2"
              className="w-full px-4 py-2.5 rounded-2xl bg-[#FAF7EE] border border-[#EDE7D8] text-[#19191B] placeholder:text-zinc-400 text-xs font-medium focus:outline-none focus:border-[#19191B] focus:ring-1 focus:ring-[#19191B] transition"
            />
          </div>

          <div className="space-y-1.5">
            <label className="text-xs font-bold text-[#19191B]">
              Category / Industry <span className="text-rose-500">*</span>
            </label>
            <input
              type="text"
              required
              value={category}
              onChange={(e) => setCategory(e.target.value)}
              placeholder="e.g. B2B Ergonomic Computer Peripherals"
              className="w-full px-4 py-2.5 rounded-2xl bg-[#FAF7EE] border border-[#EDE7D8] text-[#19191B] placeholder:text-zinc-400 text-xs font-medium focus:outline-none focus:border-[#19191B] focus:ring-1 focus:ring-[#19191B] transition"
            />
          </div>
        </div>

        <div className="space-y-1.5">
          <label className="text-xs font-bold text-[#19191B]">
            Primary Value Proposition <span className="text-rose-500">*</span>
          </label>
          <textarea
            required
            rows={2}
            value={primaryValueProp}
            onChange={(e) => setPrimaryValueProp(e.target.value)}
            placeholder="e.g. Patented 57-degree neutral wrist posture engineered with genuine tactile mechanical switches for programmers."
            className="w-full px-4 py-2.5 rounded-2xl bg-[#FAF7EE] border border-[#EDE7D8] text-[#19191B] placeholder:text-zinc-400 text-xs font-medium focus:outline-none focus:border-[#19191B] focus:ring-1 focus:ring-[#19191B] transition"
          />
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div className="space-y-1.5">
            <label className="text-xs font-bold text-[#19191B]">
              Price (USD)
            </label>
            <div className="relative">
              <span className="absolute left-4 top-2.5 text-zinc-400 text-xs font-bold">$</span>
              <input
                type="number"
                step="0.01"
                min="0"
                value={priceUsd}
                onChange={(e) => setPriceUsd(e.target.value)}
                placeholder="129.00"
                className="w-full pl-8 pr-4 py-2.5 rounded-2xl bg-[#FAF7EE] border border-[#EDE7D8] text-[#19191B] placeholder:text-zinc-400 text-xs font-medium focus:outline-none focus:border-[#19191B] focus:ring-1 focus:ring-[#19191B] transition"
              />
            </div>
          </div>

          <div className="space-y-1.5">
            <label className="text-xs font-bold text-[#19191B]">
              Known Competitors (Comma-separated, optional)
            </label>
            <input
              type="text"
              value={knownCompetitorsInput}
              onChange={(e) => setKnownCompetitorsInput(e.target.value)}
              placeholder="e.g. Logitech Lift, Logitech MX Master 3S"
              className="w-full px-4 py-2.5 rounded-2xl bg-[#FAF7EE] border border-[#EDE7D8] text-[#19191B] placeholder:text-zinc-400 text-xs font-medium focus:outline-none focus:border-[#19191B] focus:ring-1 focus:ring-[#19191B] transition"
            />
          </div>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div className="space-y-1.5">
            <label className="text-xs font-bold text-[#19191B]">
              Merchant Goal (Strategic objective, optional)
            </label>
            <input
              type="text"
              value={goal}
              onChange={(e) => setGoal(e.target.value)}
              placeholder="e.g. Capture 15% market share from Logitech Lift among engineering teams"
              className="w-full px-4 py-2.5 rounded-2xl bg-[#FAF7EE] border border-[#EDE7D8] text-[#19191B] placeholder:text-zinc-400 text-xs font-medium focus:outline-none focus:border-[#19191B] focus:ring-1 focus:ring-[#19191B] transition"
            />
          </div>

          <div className="space-y-1.5">
            <label className="text-xs font-bold text-[#19191B]">
              Target Customer Profiles (Comma-separated, optional)
            </label>
            <input
              type="text"
              value={customerProfilesInput}
              onChange={(e) => setCustomerProfilesInput(e.target.value)}
              placeholder="e.g. Software Engineers with RSI, Engineering Managers"
              className="w-full px-4 py-2.5 rounded-2xl bg-[#FAF7EE] border border-[#EDE7D8] text-[#19191B] placeholder:text-zinc-400 text-xs font-medium focus:outline-none focus:border-[#19191B] focus:ring-1 focus:ring-[#19191B] transition"
            />
          </div>
        </div>

      </div>

      {/* Section 2: Model & BYOK Selection */}
      <div className="space-y-4">
        <div className="flex items-center justify-between border-b border-[#EDE7D8] pb-2">
          <div className="flex items-center gap-2">
            <Cpu className="w-4 h-4 text-[#19191B]" />
            <h3 className="text-xs font-bold uppercase tracking-wider text-[#19191B]">
              2. Frontier Model Routing & BYOK
            </h3>
          </div>
          <label className="flex items-center gap-2 cursor-pointer text-xs font-semibold text-[#19191B]">
            <input
              type="checkbox"
              checked={enableByok}
              onChange={(e) => setEnableByok(e.target.checked)}
              className="rounded-md border-[#EDE7D8] text-[#19191B] focus:ring-[#19191B]"
            />
            Custom Provider Key
          </label>
        </div>

        {enableByok ? (
          <div className="p-5 rounded-[24px] bg-[#FAF7EE] border border-[#EDE7D8] space-y-4">
            {/* Provider Tabs */}
            <div className="flex gap-2">
              {(["openai", "anthropic", "gemini"] as BYOKProvider[]).map((prov) => (
                <button
                  key={prov}
                  type="button"
                  onClick={() => handleProviderChange(prov)}
                  className={cn(
                    "flex-1 py-2 px-3 text-xs font-bold rounded-full capitalize transition-all border",
                    selectedProvider === prov
                      ? "bg-[#19191B] text-white border-[#19191B] shadow-xs"
                      : "bg-white text-zinc-600 border-[#EDE7D8] hover:text-black"
                  )}
                >
                  {prov === "openai" ? "OpenAI" : prov === "anthropic" ? "Anthropic" : "Google Gemini"}
                </button>
              ))}
            </div>

            {/* Model Cards Grid */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-2.5">
              {modelsForCurrentProvider.map((m) => {
                const isSelected = selectedModel === m.id;
                return (
                  <div
                    key={m.id}
                    onClick={() => setSelectedModel(m.id)}
                    className={cn(
                      "p-3.5 rounded-2xl border cursor-pointer transition text-left relative",
                      isSelected
                        ? "bg-[#F8B4D9]/30 border-[#F8B4D9] shadow-xs"
                        : "bg-white border-[#EDE7D8] hover:border-zinc-300"
                    )}
                  >
                    <div className="flex items-center justify-between">
                      <span className="text-xs font-bold text-[#19191B] flex items-center gap-1.5">
                        {m.name}
                        {m.recommended && (
                          <span className="text-[10px] px-2 py-0.5 rounded-full bg-[#96C87C]/30 text-[#19350E] font-bold border border-[#96C87C]/40">
                            Recommended
                          </span>
                        )}
                      </span>
                      <span className="text-[10px] px-2 py-0.5 rounded-full bg-[#FAF7EE] text-zinc-500 font-mono">
                        {m.id}
                      </span>
                    </div>
                  </div>
                );
              })}
            </div>

            {/* API Key Input */}
            <div className="space-y-1.5 pt-2">
              <label className="text-xs font-bold text-[#19191B] flex items-center gap-1.5">
                <KeyRound className="w-3.5 h-3.5 text-[#19191B]" />
                API Key for {selectedProvider.toUpperCase()}
              </label>
              <div className="relative">
                <input
                  type={showApiKey ? "text" : "password"}
                  required={enableByok}
                  value={apiKey}
                  onChange={(e) => {
                    setApiKey(e.target.value);
                    setKeySaved(false);
                  }}
                  placeholder={`Enter your ${selectedProvider.toUpperCase()} API key...`}
                  className="w-full pr-10 pl-4 py-2.5 rounded-2xl bg-white border border-[#EDE7D8] text-[#19191B] font-mono text-xs placeholder:text-zinc-400 focus:outline-none focus:border-[#19191B]"
                />
                <button
                  type="button"
                  onClick={() => setShowApiKey(!showApiKey)}
                  className="absolute right-3.5 top-2.5 text-zinc-400 hover:text-black cursor-pointer"
                >
                  {showApiKey ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                </button>
              </div>

              {/* Save / remember the key on this device */}
              <div className="flex flex-wrap items-center gap-2">
                <button
                  type="button"
                  onClick={handleSaveKey}
                  disabled={!apiKey.trim() || keySaved}
                  className={cn(
                    "inline-flex items-center gap-1.5 px-3.5 py-2 rounded-full text-xs font-bold border transition shadow-xs",
                    !apiKey.trim() || keySaved
                      ? "bg-zinc-100 text-zinc-400 border-zinc-200 cursor-not-allowed"
                      : "bg-[#19191B] hover:bg-black text-white border-[#19191B] cursor-pointer"
                  )}
                >
                  {keySaved ? <Check className="w-3.5 h-3.5" /> : <Bookmark className="w-3.5 h-3.5" />}
                  {keySaved ? "Saved on this device" : "Save key"}
                </button>
                {keySaved && (
                  <button
                    type="button"
                    onClick={handleClearSavedKey}
                    className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-full text-xs font-bold border border-[#EDE7D8] bg-white text-zinc-600 hover:text-rose-600 hover:border-rose-200 transition cursor-pointer"
                  >
                    <Trash2 className="w-3.5 h-3.5" />
                    Forget
                  </button>
                )}
              </div>

              <p className="text-[11px] text-zinc-500 flex items-center gap-1 font-medium">
                <ShieldCheck className="w-3 h-3 text-[#96C87C]" />
                {keySaved
                  ? "Saved only in this browser on this device. Click Forget to remove it."
                  : "Saved only in this browser on this device, never on our servers."}
              </p>
            </div>
          </div>
        ) : (
          <div className="p-4 rounded-[22px] bg-[#FAF7EE] border border-[#EDE7D8] flex items-center justify-between text-xs text-zinc-600">
            <span>Using the server model: <strong className="text-[#19191B]">GPT-4o</strong> (falls back to GPT-4o mini)</span>
            <span className="text-[11px] text-zinc-500">Enable BYOK above for personal quotas</span>
          </div>
        )}
      </div>

      {/* Submit Button */}
      <div className="pt-2">
        <button
          type="submit"
          disabled={isLoading || !productName || !category || !primaryValueProp}
          className={cn(
            "w-full py-4 px-6 rounded-full font-bold text-sm flex items-center justify-center gap-2 transition-all shadow-md cursor-pointer",
            isLoading || !productName || !category || !primaryValueProp
              ? "bg-zinc-200 text-zinc-400 cursor-not-allowed shadow-none"
              : "bg-[#19191B] hover:bg-black text-white hover:scale-[1.01]"
          )}
        >
          {isLoading ? (
            <>
              <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
              Initializing Multi-Agent Strategy Pipeline...
            </>
          ) : (
            <>
              Launch Autonomous Strategy Run
              <ArrowRight className="w-4 h-4" />
            </>
          )}
        </button>
      </div>
    </form>
  );
}
