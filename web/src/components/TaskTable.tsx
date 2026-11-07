import { Link } from "react-router-dom";
import type { Task } from "../api/types";
import type { SortDirection, SortKey } from "../lib/tasks";
import { formatDateTime, formatDuration, formatRelative } from "../lib/format";
import { taskStatusLabel, taskStatusTone } from "../lib/status";
import { StatusBadge } from "./StatusBadge";
import { EmptyState } from "./EmptyState";

export interface TaskTableProps {
  tasks: Task[];
  now?: Date;
  sort?: { key: SortKey; dir: SortDirection };
  onSort?: (key: SortKey) => void;
}

const COLUMNS: Array<{ key: SortKey; label: string }> = [
  { key: "priority", label: "Приоритет" },
  { key: "created", label: "Создана" },
  { key: "available", label: "Доступна" },
];

export function TaskTable({ tasks, now, sort, onSort }: TaskTableProps) {
  const reference = now ?? new Date();

  if (tasks.length === 0) {
    return <EmptyState title="Задач нет" hint="Измените фильтры или создайте задачу через API." />;
  }

  function header(label: string, key?: SortKey) {
    if (!key || !onSort) {
      return <th scope="col">{label}</th>;
    }
    const active = sort?.key === key;
    const direction = active ? (sort?.dir === "asc" ? "ascending" : "descending") : "none";
    return (
      <th scope="col" aria-sort={direction}>
        <button
          type="button"
          className={active ? "th-sort th-sort--active" : "th-sort"}
          onClick={() => onSort(key)}
        >
          {label}
          <span aria-hidden="true">{active ? (sort?.dir === "asc" ? " ↑" : " ↓") : ""}</span>
        </button>
      </th>
    );
  }

  return (
    <div className="table-wrap">
      <table className="table">
        <thead>
          <tr>
            <th scope="col">Тип</th>
            <th scope="col">Статус</th>
            {header("Приоритет", "priority")}
            <th scope="col">Попытки</th>
            <th scope="col">Робот</th>
            {header("Создана", "created")}
            {header("Лимит", "available")}
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
              <td>{formatDuration(task.timeout_seconds)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export { COLUMNS };
