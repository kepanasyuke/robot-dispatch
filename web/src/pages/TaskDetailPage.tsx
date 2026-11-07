import { useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useApi } from "../hooks/useApi";
import { useResource } from "../hooks/useResource";
import { ErrorBanner } from "../components/ErrorBanner";
import { EventTimeline } from "../components/EventTimeline";
import { Panel } from "../components/KpiCards";
import { StatusBadge } from "../components/StatusBadge";
import { ApiError } from "../api/client";
import { formatDateTime, formatDuration, formatLease, formatRelative } from "../lib/format";
import { isTerminalStatus, taskStatusLabel, taskStatusTone } from "../lib/status";
import { canCancelTasks, denyReason } from "../lib/permissions";
import { useRole } from "../auth/RoleContext";
import { countIgnoredResults, countRetries, executionSeconds, transitionPath } from "../lib/timeline";

export function TaskDetailPage() {
  const { taskId = "" } = useParams();
  const api = useApi();
  const role = useRole();
  const allowCancel = canCancelTasks(role);
  const task = useResource(() => api.getTask(taskId), [taskId], 3000);
  const events = useResource(() => api.getTaskEvents(taskId), [taskId], 3000);
  const [actionError, setActionError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const eventList = events.data ?? [];
  const meta = useMemo(
    () => ({
      retries: countRetries(eventList),
      ignored: countIgnoredResults(eventList),
      path: transitionPath(eventList),
      executed: executionSeconds(eventList),
    }),
    [eventList],
  );

  async function cancel() {
    setBusy(true);
    setActionError(null);
    try {
      await api.cancelTask(taskId);
      task.reload();
      events.reload();
    } catch (error) {
      const message =
        error instanceof ApiError
          ? `${error.message}${error.status ? ` (код ${error.status})` : ""}`
          : String(error);
      setActionError(message);
    } finally {
      setBusy(false);
    }
  }

  if (task.error) {
    return (
      <div className="stack">
        <Link to="/tasks" className="link">
          ← ко всем задачам
        </Link>
        <ErrorBanner message={task.error} onRetry={task.reload} />
      </div>
    );
  }

  if (!task.data) {
    return <p className="muted">Загрузка задачи…</p>;
  }

  const current = task.data;
  const now = new Date();

  return (
    <div className="stack">
      <Link to="/tasks" className="link">
        ← ко всем задачам
      </Link>

      <Panel
        title={`Задача ${current.type}`}
        actions={
          <button
            type="button"
            className="button button--danger"
            disabled={busy || isTerminalStatus(current.status) || !allowCancel}
            title={allowCancel ? "Отменить задачу" : denyReason(role)}
            onClick={() => void cancel()}
          >
            {isTerminalStatus(current.status) ? "Завершена" : busy ? "Отменяем…" : "Отменить"}
          </button>
        }
      >
        <div className="detail-head">
          <StatusBadge tone={taskStatusTone(current.status)}>{taskStatusLabel(current.status)}</StatusBadge>
          <span className="mono">{current.id}</span>
          <span className="muted">
            попытка {current.attempts} из {current.max_attempts}
          </span>
        </div>

        {actionError ? (
          <p className="error-text" role="alert">
            {actionError}
          </p>
        ) : null}

        <dl className="detail-grid">
          <div>
            <dt>Приоритет</dt>
            <dd>{current.priority}</dd>
          </div>
          <div>
            <dt>Робот</dt>
            <dd className="mono">{current.robot_id ? current.robot_id.slice(0, 8) : "не назначен"}</dd>
          </div>
          <div>
            <dt>Аренда</dt>
            <dd>{formatLease(current.lease_expires_at, now)}</dd>
          </div>
          <div>
            <dt>Лимит попытки</dt>
            <dd>{formatDuration(current.timeout_seconds)}</dd>
          </div>
          <div>
            <dt>Создана</dt>
            <dd>{formatDateTime(current.created_at)}</dd>
          </div>
          <div>
            <dt>Обновлена</dt>
            <dd>{formatRelative(current.updated_at, now)}</dd>
          </div>
          <div>
            <dt>Внешний ключ</dt>
            <dd className="mono">{current.external_id ?? "—"}</dd>
          </div>
          <div>
            <dt>Переходы</dt>
            <dd className="mono">{meta.path || "—"}</dd>
          </div>
          <div>
            <dt>Повторы по событиям</dt>
            <dd>
              {meta.retries} · проигнорировано результатов: {meta.ignored}
            </dd>
          </div>
          <div>
            <dt>Время выполнения</dt>
            <dd>{meta.executed === null ? "—" : formatDuration(meta.executed)}</dd>
          </div>
        </dl>

        {current.last_error ? (
          <div className="callout callout--danger">
            <strong>Последняя ошибка</strong>
            <p>{current.last_error}</p>
          </div>
        ) : null}

        {current.payload && Object.keys(current.payload).length > 0 ? (
          <details className="details">
            <summary>Payload</summary>
            <pre className="code">{JSON.stringify(current.payload, null, 2)}</pre>
          </details>
        ) : null}
      </Panel>

      <Panel title="История событий" actions={<span className="muted">{eventList.length} событий</span>}>
        {events.error ? (
          <ErrorBanner message={events.error} onRetry={events.reload} />
        ) : (
          <EventTimeline events={eventList} now={now} />
        )}
      </Panel>
    </div>
  );
}
