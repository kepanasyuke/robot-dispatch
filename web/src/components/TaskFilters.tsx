import type { TaskFilters as Filters, TaskStatus } from "../api/types";
import { TASK_STATUSES } from "../api/types";
import { taskStatusLabel } from "../lib/status";

export interface TaskFiltersProps {
  value: Filters;
  types: string[];
  onChange: (next: Filters) => void;
}

export function TaskFilters({ value, types, onChange }: TaskFiltersProps) {
  const selected = value.statuses ?? [];

  function toggleStatus(status: TaskStatus) {
    const next = selected.includes(status)
      ? selected.filter((item) => item !== status)
      : [...selected, status];
    onChange({ ...value, statuses: next });
  }

  return (
    <div className="filters">
      <div className="filters__row" role="group" aria-label="Статусы">
        {TASK_STATUSES.map((status) => (
          <button
            key={status}
            type="button"
            className={selected.includes(status) ? "chip chip--active" : "chip"}
            aria-pressed={selected.includes(status)}
            onClick={() => toggleStatus(status)}
          >
            {taskStatusLabel(status)}
          </button>
        ))}
      </div>
      <div className="filters__row">
        <label className="field">
          <span>Тип</span>
          <select
            aria-label="Тип задачи"
            value={value.type ?? ""}
            onChange={(event) => onChange({ ...value, type: event.target.value || undefined })}
          >
            <option value="">Все типы</option>
            {types.map((type) => (
              <option key={type} value={type}>
                {type}
              </option>
            ))}
          </select>
        </label>
        <label className="field field--wide">
          <span>Поиск</span>
          <input
            type="search"
            aria-label="Поиск по задачам"
            placeholder="ID, тип, робот, ошибка"
            value={value.query ?? ""}
            onChange={(event) => onChange({ ...value, query: event.target.value })}
          />
        </label>
        <button
          type="button"
          className="button button--ghost"
          onClick={() => onChange({ statuses: [], type: undefined, robotId: undefined, query: "" })}
        >
          Сбросить
        </button>
      </div>
    </div>
  );
}
