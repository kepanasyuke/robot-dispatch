import { useMemo, useState } from "react";
import type { TaskFilters as Filters } from "../api/types";
import { useApi } from "../hooks/useApi";
import { useResource } from "../hooks/useResource";
import { ErrorBanner } from "../components/ErrorBanner";
import { Panel } from "../components/KpiCards";
import { TaskFilters } from "../components/TaskFilters";
import { TaskTable } from "../components/TaskTable";
import { CreateTaskDialog } from "../components/CreateTaskDialog";
import { useToast } from "../components/Toasts";
import { distinctTypes, filterTasks, sortTasks, type SortDirection, type SortKey } from "../lib/tasks";
import { canCreateTasks, denyReason } from "../lib/permissions";
import { useRole } from "../auth/RoleContext";
import { formatDateTime } from "../lib/format";

const PAGE_SIZES = [10, 25, 50];

export function TasksPage() {
  const api = useApi();
  const role = useRole();
  const toast = useToast();
  const [filters, setFilters] = useState<Filters>({ statuses: [] });
  const [creating, setCreating] = useState(false);
  const [page, setPage] = useState(0);
  const [pageSize, setPageSize] = useState(25);
  const [sort, setSort] = useState<{ key: SortKey; dir: SortDirection }>({ key: "created", dir: "desc" });

  const tasks = useResource(
    () => api.getTasks({}, { limit: pageSize, offset: page * pageSize }),
    [page, pageSize],
    3000,
  );

  const items = useMemo(() => tasks.data?.items ?? [], [tasks.data]);
  const types = useMemo(() => distinctTypes(items), [items]);
  const visible = useMemo(
    () => sortTasks(filterTasks(items, filters), sort.key, sort.dir),
    [items, filters, sort],
  );
  const allowCreate = canCreateTasks(role);
  const canPrev = page > 0;
  const canNext = items.length === pageSize;

  function toggleSort(key: SortKey) {
    setSort((current) =>
      current.key === key ? { key, dir: current.dir === "asc" ? "desc" : "asc" } : { key, dir: "desc" },
    );
  }

  return (
    <div className="stack">
      <Panel
        title="Задачи"
        actions={
          <div className="panel__actions-group">
            <span className="muted">
              {visible.length} из {items.length}
              {tasks.updatedAt ? ` · обновлено ${formatDateTime(tasks.updatedAt.toISOString())}` : ""}
            </span>
            <button
              type="button"
              className="button button--primary"
              disabled={!allowCreate}
              title={allowCreate ? "Создать задачу" : denyReason(role)}
              onClick={() => setCreating(true)}
            >
              Новая задача
            </button>
          </div>
        }
      >
        <TaskFilters value={filters} types={types} onChange={setFilters} />
        {tasks.error ? (
          <ErrorBanner message={tasks.error} onRetry={tasks.reload} />
        ) : (
          <TaskTable tasks={visible} sort={sort} onSort={toggleSort} />
        )}

        <div className="pager">
          <button
            type="button"
            className="button button--ghost"
            disabled={!canPrev}
            onClick={() => setPage((value) => Math.max(0, value - 1))}
          >
            Назад
          </button>
          <span className="muted" data-testid="pager-status">
            страница {page + 1}
          </span>
          <button
            type="button"
            className="button button--ghost"
            disabled={!canNext}
            onClick={() => setPage((value) => value + 1)}
          >
            Вперёд
          </button>
          <label className="field field--inline">
            <span>На странице</span>
            <select
              aria-label="Задач на странице"
              value={pageSize}
              onChange={(event) => {
                setPageSize(Number(event.target.value));
                setPage(0);
              }}
            >
              {PAGE_SIZES.map((size) => (
                <option key={size} value={size}>
                  {size}
                </option>
              ))}
            </select>
          </label>
        </div>
      </Panel>

      {creating ? (
        <CreateTaskDialog
          onClose={() => setCreating(false)}
          onSubmit={async (input, idempotencyKey) => {
            const task = await api.createTask(input, idempotencyKey);
            toast(`Задача «${task.type}» создана`);
            setPage(0);
            tasks.reload();
            return task;
          }}
        />
      ) : null}
    </div>
  );
}
