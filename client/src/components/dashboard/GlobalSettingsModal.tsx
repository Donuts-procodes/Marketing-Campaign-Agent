import { useState, useEffect, type FC } from "react";
import { createPortal } from "react-dom";
import { Settings, X, KeyRound, Check, Trash2, Eye, EyeOff } from "lucide-react";
import { AVAILABLE_MODELS, BYOKProvider } from "@/types/api";
import { cn } from "@/lib/utils";

const BYOK_STORAGE_KEY = "intelly.byok";

interface GlobalSettingsModalProps {
  isOpen: boolean;
  onClose: () => void;
}

export const GlobalSettingsModal: FC<GlobalSettingsModalProps> = ({ isOpen, onClose }) => {
  const [provider, setProvider] = useState<BYOKProvider>("openai");
  const [model, setModel] = useState<string>("gpt-4o");
  const [apiKey, setApiKey] = useState("");
  const [showApiKey, setShowApiKey] = useState(false);
  const [isSaved, setIsSaved] = useState(false);

  useEffect(() => {
    if (isOpen) {
      try {
        const raw = localStorage.getItem(BYOK_STORAGE_KEY);
        if (raw) {
          const parsed = JSON.parse(raw);
          setProvider(parsed.provider || "openai");
          setModel(parsed.model || "gpt-4o");
          setApiKey(parsed.apiKey || "");
          setIsSaved(true);
        }
      } catch {
        // ignore
      }
    }
  }, [isOpen]);

  if (!isOpen) return null;

  const handleProviderChange = (newProvider: BYOKProvider) => {
    setProvider(newProvider);
    const models = AVAILABLE_MODELS[newProvider];
    const recommended = models.find((m) => m.recommended) || models[0];
    setModel(recommended.id);
    setIsSaved(false);
  };

  const handleSave = () => {
    try {
      localStorage.setItem(
        BYOK_STORAGE_KEY,
        JSON.stringify({ provider, model, apiKey: apiKey.trim() })
      );
      setIsSaved(true);
      setTimeout(onClose, 800);
    } catch {
      setIsSaved(false);
    }
  };

  const handleClear = () => {
    try {
      localStorage.removeItem(BYOK_STORAGE_KEY);
    } catch {
      // ignore
    }
    setApiKey("");
    setIsSaved(false);
  };

  const modelsForCurrentProvider = AVAILABLE_MODELS[provider];

  return createPortal(
    <div
      onClick={onClose}
      className="fixed inset-0 z-[9999] flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm animate-in fade-in duration-200"
    >
      <div
        onClick={(e) => e.stopPropagation()}
        className="bg-white rounded-[24px] shadow-2xl w-full max-w-lg overflow-hidden flex flex-col border border-zinc-200 text-[#19191B] m-auto animate-in zoom-in-95 duration-200"
      >
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-zinc-100 bg-[#FAF7EE]">
          <div className="flex items-center gap-2">
            <Settings className="w-5 h-5 text-zinc-600" />
            <h2 className="text-sm font-bold font-display tracking-tight">Global Settings & BYOK</h2>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 rounded-full hover:bg-zinc-200 text-zinc-500 transition-colors cursor-pointer"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Body */}
        <div className="p-6 space-y-6">
          <div className="space-y-4">
            <div>
              <h3 className="text-xs font-bold uppercase tracking-wider text-[#19191B] mb-1">
                Custom Provider Key (BYOK)
              </h3>
              <p className="text-[11px] text-zinc-500 leading-relaxed">
                Configure your own API key to bypass server limits. This key is stored securely in your browser's LocalStorage and will be used for autofill and new campaigns.
              </p>
            </div>

            {/* Provider Tabs */}
            <div className="flex gap-2">
              {(["openai", "anthropic", "gemini"] as BYOKProvider[]).map((prov) => (
                <button
                  key={prov}
                  type="button"
                  onClick={() => handleProviderChange(prov)}
                  className={cn(
                    "flex-1 py-2 px-3 text-xs font-bold rounded-full capitalize transition-all border cursor-pointer",
                    provider === prov
                      ? "bg-[#19191B] text-white border-[#19191B] shadow-sm"
                      : "bg-white text-zinc-600 border-zinc-200 hover:text-black"
                  )}
                >
                  {prov === "openai" ? "OpenAI" : prov === "anthropic" ? "Anthropic" : "Google Gemini"}
                </button>
              ))}
            </div>

            {/* Model Selection */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-2.5">
              {modelsForCurrentProvider.map((m) => {
                const isSelected = model === m.id;
                return (
                  <div
                    key={m.id}
                    onClick={() => { setModel(m.id); setIsSaved(false); }}
                    className={cn(
                      "p-3 rounded-2xl border cursor-pointer transition text-left relative",
                      isSelected
                        ? "bg-[#F8B4D9]/20 border-[#F8B4D9] shadow-sm"
                        : "bg-zinc-50 border-zinc-200 hover:border-zinc-300"
                    )}
                  >
                    <div className="flex flex-col gap-1">
                      <span className="text-xs font-bold text-[#19191B] flex items-center justify-between">
                        {m.name}
                        {m.recommended && (
                          <span className="text-[9px] px-1.5 py-0.5 rounded-full bg-emerald-100 text-emerald-800 font-bold border border-emerald-200">
                            Rec
                          </span>
                        )}
                      </span>
                      <span className="text-[10px] text-zinc-500 font-mono">
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
                <KeyRound className="w-3.5 h-3.5 text-zinc-500" />
                API Key for {provider.toUpperCase()}
              </label>
              <div className="relative">
                <input
                  type={showApiKey ? "text" : "password"}
                  value={apiKey}
                  onChange={(e) => {
                    setApiKey(e.target.value);
                    setIsSaved(false);
                  }}
                  placeholder={`Enter your ${provider.toUpperCase()} API key...`}
                  className="w-full pr-10 pl-4 py-2.5 rounded-2xl bg-zinc-50 border border-zinc-200 text-[#19191B] font-mono text-xs placeholder:text-zinc-400 focus:outline-none focus:border-[#19191B]"
                />
                <button
                  type="button"
                  onClick={() => setShowApiKey(!showApiKey)}
                  className="absolute right-3.5 top-2.5 text-zinc-400 hover:text-black cursor-pointer"
                >
                  {showApiKey ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                </button>
              </div>
            </div>

          </div>
        </div>

        {/* Footer Actions */}
        <div className="p-4 bg-zinc-50 border-t border-zinc-100 flex items-center justify-between">
          <button
            type="button"
            onClick={handleClear}
            className="px-4 py-2 rounded-full text-xs font-bold text-rose-600 hover:bg-rose-50 transition-colors flex items-center gap-1.5 cursor-pointer"
          >
            <Trash2 className="w-3.5 h-3.5" />
            Clear Key
          </button>
          
          <div className="flex items-center gap-2">
            <button
              onClick={onClose}
              className="px-4 py-2 rounded-full text-xs font-bold text-zinc-600 bg-white border border-zinc-200 hover:bg-zinc-50 transition-colors cursor-pointer"
            >
              Cancel
            </button>
            <button
              onClick={handleSave}
              disabled={!apiKey.trim()}
              className={cn(
                "px-5 py-2 rounded-full text-xs font-bold transition-all shadow-sm flex items-center gap-1.5 cursor-pointer",
                !apiKey.trim()
                  ? "bg-zinc-200 text-zinc-400 cursor-not-allowed"
                  : isSaved
                    ? "bg-emerald-600 text-white hover:bg-emerald-700"
                    : "bg-[#19191B] text-white hover:bg-black"
              )}
            >
              {isSaved ? <Check className="w-4 h-4" /> : <KeyRound className="w-4 h-4" />}
              {isSaved ? "Saved" : "Save Settings"}
            </button>
          </div>
        </div>
      </div>
    </div>,
    document.body
  );
};
