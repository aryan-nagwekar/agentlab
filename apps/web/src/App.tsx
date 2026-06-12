import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";

import { Shell } from "./components/layout/Shell";
import { AgentDetailPage } from "./pages/AgentDetail";
import { DashboardPage } from "./pages/Dashboard";
import { LabPage } from "./pages/Lab";
import { ProjectDetailPage } from "./pages/ProjectDetail";
import { ProjectsPage } from "./pages/Projects";
import { RunDetailPage } from "./pages/RunDetail";
import { RuntimeWorkspacePage } from "./pages/RuntimeWorkspace";
import { RuntimeWorkspacesPage } from "./pages/RuntimeWorkspaces";
import { SettingsPage } from "./pages/Settings";
import { StudioPage } from "./pages/Studio";
import { StudioTemplatePage } from "./pages/StudioTemplate";
import { StudioTemplatesPage } from "./pages/StudioTemplates";
import { StudioWorkflowPage } from "./pages/StudioWorkflow";

export function App() {
  return (
    <BrowserRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <Routes>
        <Route element={<Shell />}>
          <Route path="/" element={<Navigate to="/dashboard" replace />} />
          <Route path="/dashboard" element={<DashboardPage />} />
          <Route path="/projects" element={<ProjectsPage />} />
          <Route path="/projects/:projectId" element={<ProjectDetailPage />} />
          <Route path="/runs/:runId" element={<RunDetailPage />} />
          <Route path="/agents/:agentId" element={<AgentDetailPage />} />
          <Route path="/studio" element={<StudioPage />} />
          <Route path="/studio/templates" element={<StudioTemplatesPage />} />
          <Route path="/studio/templates/:templateId" element={<StudioTemplatePage />} />
          <Route path="/studio/workflows" element={<Navigate to="/studio" replace />} />
          <Route path="/studio/workflows/:workflowId" element={<StudioWorkflowPage />} />
          <Route path="/runtime" element={<RuntimeWorkspacesPage />} />
          <Route path="/runtime/workspaces/:workspaceId" element={<RuntimeWorkspacePage />} />
          <Route path="/lab" element={<LabPage />} />
          <Route path="/settings" element={<SettingsPage />} />
          <Route path="*" element={<Navigate to="/dashboard" replace />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
