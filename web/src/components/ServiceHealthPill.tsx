import type { HealthSummary } from "../lib/health";

const TONE_BY_STATE: Record<HealthSummary["state"], string> = {
  ok: "success",
  degraded: "warning",
  down: "danger",
  unknown: "neutral",
};

export function ServiceHealthPill({ health }: { health: HealthSummary }) {
  return (
    <div className={`health health--${TONE_BY_STATE[health.state]}`} title={health.detail}>
      <span className="health__dot" aria-hidden="true" />
      <span>{health.label}</span>
    </div>
  );
}
