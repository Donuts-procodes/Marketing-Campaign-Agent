import { lazy, Suspense } from "react";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import { Loader2, Terminal } from "lucide-react";

// Each page is its own chunk: the intake form never downloads the report dashboard and vice versa.
const OrchestratorPage = lazy(() => import("@/pages/OrchestratorPage").then((m) => ({ default: m.OrchestratorPage })));
const NewCampaignPage = lazy(() => import("@/pages/NewCampaignPage").then((m) => ({ default: m.NewCampaignPage })));
const CampaignLivePage = lazy(() => import("@/pages/CampaignLivePage").then((m) => ({ default: m.CampaignLivePage })));

function PageFallback() {
  return (
    <div className="flex-1 flex items-center justify-center py-32 text-zinc-400">
      <Loader2 className="w-5 h-5 animate-spin" />
    </div>
  );
}

export function App() {
  return (
    <BrowserRouter>
      <div className="min-h-screen bg-[#F1ECE1] text-[#19191B] flex flex-col font-['Plus_Jakarta_Sans',sans-serif] selection:bg-[#F8B4D9] selection:text-[#3D102A]">
        {/* Dynamic Route View */}
        <main className="flex-1 py-4 sm:py-6 px-2 sm:px-4 lg:px-6 flex flex-col items-center justify-center">
          <Suspense fallback={<PageFallback />}>
            <Routes>
              <Route path="/" element={<OrchestratorPage />} />
              <Route path="/campaigns/new" element={<NewCampaignPage />} />
              <Route path="/campaigns/:jobId" element={<CampaignLivePage />} />
            </Routes>
          </Suspense>
        </main>

        {/* Subtle Footer */}
        <footer className="py-4 text-center text-xs text-zinc-500 font-mono select-none">
          <div className="max-w-[1620px] mx-auto px-4 flex flex-col sm:flex-row items-center justify-between gap-2">
            <span>Intelly Autonomous Multi-Agent Marketing Engine • LangGraph + React 18</span>
            <span className="flex items-center gap-1 text-zinc-600">
              <Terminal className="w-3.5 h-3.5 text-[#F472B6]" />
              Multi-Vector Web Grounding: Tavily Search • Firecrawl DOM Scraper • Meta Ad Library
            </span>
          </div>
        </footer>
      </div>
    </BrowserRouter>
  );
}

export default App;
