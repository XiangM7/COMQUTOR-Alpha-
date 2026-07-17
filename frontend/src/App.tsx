import { Navigate, Route, Routes } from "react-router-dom";
import { AppShell } from "./components/AppShell";
import { ResearchPage } from "./pages/ResearchPage";
import { ProcessingPage } from "./pages/ProcessingPage";
import { ResearchRunPage } from "./pages/ResearchRunPage";
import { StructureGraphPage } from "./pages/StructureGraphPage";
import { ConflictRadarPage } from "./pages/ConflictRadarPage";
import { NotFoundPage } from "./pages/NotFoundPage";

export function App() {
  return (
    <AppShell>
      <Routes>
        <Route path="/" element={<Navigate to="/research" replace />} />
        <Route path="/research" element={<ResearchPage />} />
        <Route path="/runs/:runId/processing" element={<ProcessingPage />} />
        <Route path="/runs/:runId/research" element={<ResearchRunPage />} />
        <Route path="/runs/:runId/structure" element={<StructureGraphPage />} />
        <Route path="/runs/:runId/conflicts" element={<ConflictRadarPage />} />
        <Route path="*" element={<NotFoundPage />} />
      </Routes>
    </AppShell>
  );
}
