import { BrowserRouter, Routes, Route } from "react-router-dom";
import { OrchestratorPage } from "@/pages/OrchestratorPage";
import { NewCampaignPage } from "@/pages/NewCampaignPage";
import { CampaignLivePage } from "@/pages/CampaignLivePage";
import { Terminal } from "lucide-react";

export function App() {
  return (
    <BrowserRouter>
      <div className="min-h-screen bg-[#F1ECE1] text-[#19191B] flex flex-col font-['Plus_Jakarta_Sans',sans-serif] selection:bg-[#F8B4D9] selection:text-[#3D102A]">
        {/* Dynamic Route View */}
        <main className="flex-1 py-4 sm:py-6 px-2 sm:px-4 lg:px-6 flex flex-col items-center justify-center">
          <Routes>
            <Route path="/" element={<OrchestratorPage />} />
            <Route path="/campaigns/new" element={<NewCampaignPage />} />
            <Route path="/campaigns/:jobId" element={<CampaignLivePage />} />
          </Routes>
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
