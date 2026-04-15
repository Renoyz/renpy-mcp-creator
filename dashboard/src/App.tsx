import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { AppShell } from "./AppShell";
import { ProjectSelectPage } from "./pages/ProjectSelectPage";
import { ProjectHomePage } from "./pages/ProjectHomePage";
import { LegacyIframePage } from "./pages/LegacyIframePage";

function App() {
  return (
    <BrowserRouter basename="/dashboard">
      <AppShell>
        <Routes>
          <Route path="/" element={<Navigate to="/projects" replace />} />
          <Route path="/projects" element={<ProjectSelectPage />} />
          <Route path="/projects/:name" element={<ProjectHomePage />} />
          <Route
            path="/story-map"
            element={<LegacyIframePage path="/story-map" title="Story Map" />}
          />
          <Route
            path="/script-editor"
            element={<LegacyIframePage path="/script-editor" title="脚本编辑器" />}
          />
          <Route
            path="/assets"
            element={<LegacyIframePage path="/assets" title="资源管理" />}
          />
          <Route
            path="*"
            element={
              <div className="flex h-full items-center justify-center">
                <div className="text-center">
                  <h1 className="text-2xl font-bold">404</h1>
                  <p className="text-muted-foreground">页面建设中</p>
                </div>
              </div>
            }
          />
        </Routes>
      </AppShell>
    </BrowserRouter>
  );
}

export default App;
