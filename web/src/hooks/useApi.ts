import { createContext, useContext } from "react";
import type { ApiClient } from "../api/client";

export const ApiContext = createContext<ApiClient | null>(null);

export function useApi(): ApiClient {
  const client = useContext(ApiContext);
  if (!client) {
    throw new Error("ApiContext is not provided");
  }
  return client;
}
