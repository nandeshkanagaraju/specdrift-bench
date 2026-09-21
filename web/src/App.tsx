import { Route, Routes } from "react-router-dom";
import { AppShell } from "./components/AppShell";
import { CaseDetailPage } from "./pages/CaseDetail";
import { ComparePage } from "./pages/Compare";
import { ExplorerPage } from "./pages/Explorer";
import { KitchenSink } from "./pages/KitchenSink";
import { LiveCheckPage } from "./pages/LiveCheck";
import { OverviewPage } from "./pages/Overview";

export function App() {
  return (
    <AppShell>
      <Routes>
        <Route path="/" element={<OverviewPage />} />
        <Route path="/explorer" element={<ExplorerPage />} />
        <Route path="/cases/:caseId" element={<CaseDetailPage />} />
        <Route path="/compare" element={<ComparePage />} />
        <Route path="/live" element={<LiveCheckPage />} />
        <Route path="/kitchen-sink" element={<KitchenSink />} />
        <Route
          path="*"
          element={<p className="text-sm text-muted">No such page.</p>}
        />
      </Routes>
    </AppShell>
  );
}
