import { createContext, useContext } from "react";
import type { Role } from "./session";

export const RoleContext = createContext<Role>("viewer");

export function useRole(): Role {
  return useContext(RoleContext);
}
