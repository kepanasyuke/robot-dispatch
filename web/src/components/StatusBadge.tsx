import type { ReactNode } from "react";
import type { Tone } from "../lib/status";

export function StatusBadge({ tone, children }: { tone: Tone; children: ReactNode }) {
  return (
    <span className={`badge badge--${tone}`} data-tone={tone}>
      {children}
    </span>
  );
}
