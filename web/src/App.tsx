import { Route, Routes } from "react-router-dom";
import { AppShell } from "./components/AppShell";
import { CaseDetailPage } from "./pages/CaseDetail";
import { ComparePage } from "./pages/Compare";
import { DemoPage } from "./pages/Demo";
import { ExplorerPage } from "./pages/Explorer";
import { KitchenSink } from "./pages/KitchenSink";
import { LiveCheckPage } from "./pages/LiveCheck";
import { OverviewPage } from "./pages/Overview";
import { YourProjectPage } from "./pages/YourProject";

/**
 * "/" is the walkthrough: one page, no chrome, readable by someone who has never
 * seen the project. Everything else is the original dashboard, which keeps the
 * sidebar and is reachable from the walkthrough's footer.
 */
export function App() {
  return (
    <Routes>
      <Route path="/" element={<DemoPage />} />
      <Route
        path="*"
        element={
          <AppShell>
            <Routes>
              <Route path="/dashboard" element={<OverviewPage />} />
              <Route path="/explorer" element={<ExplorerPage />} />
              <Route path="/cases/:caseId" element={<CaseDetailPage />} />
              <Route path="/compare" element={<ComparePage />} />
              <Route path="/live" element={<LiveCheckPage />} />
              <Route path="/yours" element={<YourProjectPage />} />
              <Route path="/kitchen-sink" element={<KitchenSink />} />
              <Route
                path="*"
                element={<p className="text-sm text-muted">No such page.</p>}
              />
            </Routes>
          </AppShell>
        }
      />
    </Routes>
  );
}
