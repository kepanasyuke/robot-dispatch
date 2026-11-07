import type { Robot } from "../api/types";
import { formatRelative } from "../lib/format";
import { robotStatusLabel, robotStatusTone } from "../lib/status";
import { EmptyState } from "./EmptyState";
import { StatusBadge } from "./StatusBadge";

export function RobotGrid({ robots, now }: { robots: Robot[]; now?: Date }) {
  const reference = now ?? new Date();

  if (robots.length === 0) {
    return <EmptyState title="Парк пуст" hint="Зарегистрируйте робота через POST /api/v1/robots." />;
  }

  return (
    <div className="robot-grid">
      {robots.map((robot) => (
        <article key={robot.id} className="robot-card" data-testid="robot-card">
          <header className="robot-card__head">
            <strong>{robot.name}</strong>
            <StatusBadge tone={robotStatusTone(robot.status)}>{robotStatusLabel(robot.status)}</StatusBadge>
          </header>
          <dl className="robot-card__meta">
            <div>
              <dt>Namespace</dt>
              <dd className="mono">{robot.namespace}</dd>
            </div>
            <div>
              <dt>Связь</dt>
              <dd>{formatRelative(robot.last_seen_at, reference)}</dd>
            </div>
            <div>
              <dt>Задача</dt>
              <dd className="mono">{robot.current_task_id ? robot.current_task_id.slice(0, 8) : "—"}</dd>
            </div>
          </dl>
          <div className="robot-card__caps">
            {robot.capabilities.map((capability) => (
              <span key={capability} className="chip chip--static">
                {capability}
              </span>
            ))}
          </div>
        </article>
      ))}
    </div>
  );
}
