import { Link } from "react-router-dom";
import type { Task } from "../api/types";
import { formatDateTime, formatDuration, formatRelative } from "../lib/format";
import { taskStatusLabel, taskStatusTone } from "../lib/status";
import { StatusBadge } from "./StatusBadge";
import { EmptyState } from "./EmptyState";

export function TaskTable({ tasks, now }: { tasks: Task[]; now?: Date }) {
  const reference = now ?? new Date();

  if (tasks.length === 0) {
    return <EmptyState title="Задач нет" hint="Измените фильтры или создайте задачу через API." />;
  }

  return (
    <div className="table-wrap">
      <table className="table">
        <thead>
          <tr>
            <th scope="col">Тип</th>
            <th scope="col">Статус</th>
            <th scope="col">Приоритет</th>
            <th scope="col">Попытки</th>
            <th scope="col">Робот</th>
            <th scope="col">Создана</th>
            <th scope="col">Обновлена</th>
          </tr>
        </thead>
        <tbody>
          {tasks.map((task) => (
            <tr key={task.id} data-testid="task-row">
              <td>
                <Link to={`/tasks/${task.id}`} className="link">
                  {task.type}
                </Link>
                <small className="mono">{task.id.slice(0, 8)}</small>
              </td>
              <td>
                <StatusBadge tone={taskStatusTone(task.status)}>{taskStatusLabel(task.status)}</StatusBadge>
                {task.last_error ? <small className="error-text">{task.last_error}</small> : null}
              </td>
              <td>{task.priority}</td>
              <td>
                {task.attempts} / {task.max_attempts}
              </td>
              <td className="mono">{task.robot_id ? task.robot_id.slice(0, 8) : "—"}</td>
              <td title={formatDateTime(task.created_at)}>{formatRelative(task.created_at, reference)}</td>
              <td>{formatDuration(task.timeout_seconds)} лимит</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
