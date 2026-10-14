import { lazy, Suspense, useEffect } from "react";
import { BrowserRouter, Routes, Route, useNavigate } from "react-router-dom";
import { Loader2 } from "lucide-react";

// Each page is its own chunk: the intake form never downloads the report dashboard and vice versa.
const WorkspacePage = lazy(() => import("@/pages/WorkspacePage").then((m) => ({ default: m.WorkspacePage })));
const OrchestratorPage = lazy(() => import("@/pages/OrchestratorPage").then((m) => ({ default: m.OrchestratorPage })));
const CampaignLivePage = lazy(() => import("@/pages/CampaignLivePage").then((m) => ({ default: m.CampaignLivePage })));

/** Replaces the current URL (no history entry), for retired and unknown paths. */
function Redirect({ to }: { to: string }) {
  const navigate = useNavigate();
  useEffect(() => {
    navigate(to, { replace: true });
  }, [navigate, to]);
  return null;
}

function PageFallback() {
  return (
    <div className="flex-1 flex items-center justify-center py-32 text-[#8A8176]">
      <Loader2 className="w-6 h-6 animate-spin text-[#C7431F]" />
    </div>
  );
}

export function App() {
  return (
    <BrowserRouter>
      <div className="min-h-screen bg-[#FAF6EF] text-[#1F1A17] flex flex-col font-['Manrope',sans-serif] selection:bg-[#F3CFC0] selection:text-[#8F2F14]">
        <main className="flex-1 flex flex-col">
          <Suspense fallback={<PageFallback />}>
            <Routes>
              {/* The URL is the workspace's state: back/forward walk the campaign steps. */}
              <Route path="/" element={<WorkspacePage />} />
              <Route path="/workspace" element={<Redirect to="/" />} />
              <Route path="/campaigns/new" element={<WorkspacePage />} />
              <Route path="/campaigns/:jobId" element={<WorkspacePage />} />
              <Route path="/campaigns/:jobId/:step" element={<WorkspacePage />} />
              <Route path="/legacy" element={<OrchestratorPage />} />
              <Route path="/legacy/:jobId" element={<CampaignLivePage />} />
              <Route path="*" element={<Redirect to="/" />} />
            </Routes>
          </Suspense>
        </main>
      </div>
    </BrowserRouter>
  );
}

export default App;
