import { HashRouter, Route, Routes } from "react-router-dom";
import { useMemo } from "react";
import { Layout } from "./components/Layout";
import { DashboardPage } from "./pages/DashboardPage";
import { TasksPage } from "./pages/TasksPage";
import { TaskDetailPage } from "./pages/TaskDetailPage";
import { RobotsPage } from "./pages/RobotsPage";
import { summarizeHealth } from "./lib/health";
import { useResource } from "./hooks/useResource";
import { useApi } from "./hooks/useApi";

function Shell() {
  const api = useApi();
  const live = useResource(() => api.getHealthLive(), [], 10000);
  const ready = useResource(() => api.getHealthReady(), [], 10000);
  const health = useMemo(() => summarizeHealth(live.data, ready.data), [live.data, ready.data]);

  return (
    <Layout health={health}>
      <Routes>
        <Route path="/" element={<DashboardPage />} />
        <Route path="/tasks" element={<TasksPage />} />
        <Route path="/tasks/:taskId" element={<TaskDetailPage />} />
        <Route path="/robots" element={<RobotsPage />} />
        <Route
          path="*"
          element={
            <div className="empty">
              <strong>Страница не найдена</strong>
              <p>Проверьте адрес.</p>
            </div>
          }
        />
      </Routes>
    </Layout>
  );
}

export function App() {
  return (
    <HashRouter>
      <Shell />
    </HashRouter>
  );
}
