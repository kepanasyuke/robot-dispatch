import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { App } from "./App";
import { ApiContext } from "./hooks/useApi";
import { createApiClient } from "./api/client";
import "./styles.css";

const baseUrl = import.meta.env.VITE_API_BASE ?? "http://localhost:8000/api/v1";
const apiKey = import.meta.env.VITE_API_KEY as string | undefined;

const client = createApiClient({ baseUrl, apiKey });

const container = document.getElementById("root");
if (!container) {
  throw new Error("root element is missing");
}

createRoot(container).render(
  <StrictMode>
    <ApiContext.Provider value={client}>
      <App />
    </ApiContext.Provider>
  </StrictMode>,
);
