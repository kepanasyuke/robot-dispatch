import { useMemo } from "react";
import { useApi } from "../hooks/useApi";
import { useResource } from "../hooks/useResource";
import { KpiCards, Panel } from "../components/KpiCards";
import { ErrorBanner } from "../components/ErrorBanner";
import { RobotGrid } from "../components/RobotGrid";
import { StatusBadge } from "../components/StatusBadge";
import { formatDuration, formatNumber, formatPercent } from "../lib/format";
import { queueRows, robotAvailability, summarizeHealth } from "../lib/health";
import { statusCount, successRate, summarizeTasks } from "../lib/tasks";
import { taskStatusLabel, taskStatusTone } from "../lib/status";

export function DashboardPage() {
  const api = useApi();
  const tasks = useResource(() => api.getTasks({}, { limit: 200 }), [], 3000);
  const robots = useResource(() => api.getRobots(), [], 3000);
  const stats = useResource(() => api.getStats(), [], 3000);
  const live = useResource(() => api.getHealthLive(), [], 10000);
  const ready = useResource(() => api.getHealthReady(), [], 10000);

  const summary = useMemo(() => summarizeTasks(tasks.data?.items ?? []), [tasks.data]);
  const fleet = useMemo(() => robotAvailability(robots.data ?? []), [robots.data]);
  const health = useMemo(() => summarizeHealth(live.data, ready.data), [live.data, ready.data]);
  const queues = useMemo(() => queueRows(stats.data), [stats.data]);
  const items = tasks.data?.items ?? [];

  if (tasks.error) {
    return <ErrorBanner message={tasks.error} onRetry={tasks.reload} />;
  }

  return (
    <div className="stack">
      <KpiCards
        items={[
          { label: "Задач всего", value: formatNumber(summary.total), hint: `${summary.active} в работе` },
          {
            label: "В очереди",
            value: formatNumber(statusCount(summary, "pending") + statusCount(summary, "retrying")),
            hint: summary.oldestWaitingSeconds > 0 ? `старейшая ждёт ${formatDuration(summary.oldestWaitingSeconds)}` : "очередь пуста",
            tone: "neutral",
          },
          {
            label: "Успешно",
            value: formatPercent(statusCount(summary, "succeeded"), Math.max(1, summary.total)),
            hint: `доля успеха ${successRate(items)} %`,
            tone: "success",
          },
          {
            label: "Повторы",
            value: formatNumber(summary.retries),
            hint: `среднее попыток ${summary.averageAttempts}`,
            tone: summary.retries > 0 ? "warning" : "neutral",
          },
          { label: "Флот онлайн", value: `${fleet.online} / ${fleet.total}`, hint: `${fleet.percent} %`, tone: "info" },
          { label: "Состояние", value: health.label, hint: health.detail, tone: health.state === "ok" ? "success" : "warning" },
        ]}
      />

      <div className="grid-2">
        <Panel title="Очередь по статусам">
          {queues.length === 0 ? (
            <p className="muted">Статистика ещё не пришла</p>
          ) : (
            <ul className="bars">
              {queues.map((row) => (
                <li key={row.status} className="bars__row">
                  <span className="bars__label">
                    <StatusBadge tone={taskStatusTone(row.status)}>{taskStatusLabel(row.status)}</StatusBadge>
                  </span>
                  <span className="bars__track">
                    <span className="bars__fill" style={{ width: `${Math.min(100, row.share)}%` }} />
                  </span>
                  <span className="bars__value">{formatNumber(row.count)}</span>
                </li>
              ))}
            </ul>
          )}
        </Panel>

        <Panel title="Флот">
          <RobotGrid robots={(robots.data ?? []).slice(0, 6)} />
        </Panel>
      </div>
    </div>
  );
}
