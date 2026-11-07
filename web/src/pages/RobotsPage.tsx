import { useMemo } from "react";
import { useApi } from "../hooks/useApi";
import { useResource } from "../hooks/useResource";
import { ErrorBanner } from "../components/ErrorBanner";
import { Panel } from "../components/KpiCards";
import { RobotGrid } from "../components/RobotGrid";
import { robotAvailability, staleRobots } from "../lib/health";
import { formatPercent } from "../lib/format";
import { robotStatusLabel } from "../lib/status";

export function RobotsPage() {
  const api = useApi();
  const robots = useResource(() => api.getRobots(), [], 5000);
  const items = useMemo(() => robots.data ?? [], [robots.data]);
  const fleet = useMemo(() => robotAvailability(items), [items]);
  const stale = useMemo(() => staleRobots(items), [items]);

  return (
    <div className="stack">
      {robots.error ? (
        <ErrorBanner message={robots.error} onRetry={robots.reload} />
      ) : (
        <>
          <Panel
            title="Парк роботов"
            actions={
              <span className="muted">
                {fleet.online} из {fleet.total} на связи · {formatPercent(fleet.online, Math.max(1, fleet.total))}
              </span>
            }
          >
            <RobotGrid robots={items} />
          </Panel>

          <Panel title="Требуют внимания" actions={<span className="muted">{stale.length}</span>}>
            {stale.length === 0 ? (
              <p className="muted">Все роботы выходили на связь недавно</p>
            ) : (
              <ul className="list">
                {stale.map((robot) => (
                  <li key={robot.id} className="list__row">
                    <strong>{robot.name}</strong>
                    <span className="muted">
                      {robotStatusLabel(robot.status)} · последний heartbeat{" "}
                      {robot.last_seen_at ? robot.last_seen_at : "нет"}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </Panel>
        </>
      )}
    </div>
  );
}
