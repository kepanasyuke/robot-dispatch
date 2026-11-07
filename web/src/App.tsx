import { HashRouter, Route, Routes } from "react-router-dom";
import { useCallback, useMemo, useState } from "react";
import { Layout } from "./components/Layout";
import { DashboardPage } from "./pages/DashboardPage";
import { TasksPage } from "./pages/TasksPage";
import { TaskDetailPage } from "./pages/TaskDetailPage";
import { RobotsPage } from "./pages/RobotsPage";
import { LoginPage } from "./pages/LoginPage";
import { summarizeHealth } from "./lib/health";
import { useResource } from "./hooks/useResource";
import { useApi, ApiContext } from "./hooks/useApi";
import { RoleContext } from "./auth/RoleContext";
import { clearSession, loadSession, saveSession, type Session } from "./auth/session";
import { createApiClient, type ApiClient } from "./api/client";
import { createDemoClient } from "./demo/demoClient";

export interface AppProps {
  clientFactory?: (session: Session) => ApiClient;
}

function defaultFactory(session: Session): ApiClient {
  if (import.meta.env.VITE_DEMO === "1") {
    return createDemoClient();
  }
  return createApiClient({
    baseUrl: import.meta.env.VITE_API_BASE ?? "http://localhost:8000/api/v1",
    apiKey: session.apiKey || undefined,
  });
}

function Shell({ session, onLogout }: { session: Session; onLogout: () => void }) {
  const api = useApi();
  const live = useResource(() => api.getHealthLive(), [], 10000);
  const ready = useResource(() => api.getHealthReady(), [], 10000);
  const health = useMemo(() => summarizeHealth(live.data, ready.data), [live.data, ready.data]);

  return (
    <RoleContext.Provider value={session.role}>
      <Layout health={health} session={session} onLogout={onLogout}>
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
    </RoleContext.Provider>
  );
}

export function App({ clientFactory }: AppProps = {}) {
  const [session, setSession] = useState<Session | null>(() => loadSession());

  const factory = clientFactory ?? defaultFactory;

  const login = useCallback((next: Session) => {
    saveSession(next);
    setSession(next);
  }, []);

  const logout = useCallback(() => {
    clearSession();
    setSession(null);
  }, []);

  const client = useMemo(() => (session ? factory(session) : null), [session, factory]);

  if (!session || !client) {
    return <LoginPage onLogin={login} />;
  }

  return (
    <ApiContext.Provider value={client}>
      <HashRouter>
        <Shell session={session} onLogout={logout} />
      </HashRouter>
    </ApiContext.Provider>
  );
}
