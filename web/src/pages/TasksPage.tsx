import { useMemo, useState } from "react";
import type { TaskFilters as Filters } from "../api/types";
import { useApi } from "../hooks/useApi";
import { useResource } from "../hooks/useResource";
import { ErrorBanner } from "../components/ErrorBanner";
import { Panel } from "../components/KpiCards";
import { TaskFilters } from "../components/TaskFilters";
import { TaskTable } from "../components/TaskTable";
import { CreateTaskDialog } from "../components/CreateTaskDialog";
import { distinctTypes, filterTasks, sortTasks } from "../lib/tasks";
import { canCreateTasks, denyReason } from "../lib/permissions";
import { useRole } from "../auth/RoleContext";
import { formatDateTime } from "../lib/format";

export function TasksPage() {
  const api = useApi();
  const role = useRole();
  const [filters, setFilters] = useState<Filters>({ statuses: [] });
  const [creating, setCreating] = useState(false);
  const tasks = useResource(() => api.getTasks({}, { limit: 200 }), [], 3000);

  const items = tasks.data?.items ?? [];
  const types = useMemo(() => distinctTypes(items), [items]);
  const visible = useMemo(() => sortTasks(filterTasks(items, filters), "created", "desc"), [items, filters]);
  const allowCreate = canCreateTasks(role);

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
          <TaskTable tasks={visible} />
        )}
      </Panel>

      {creating ? (
        <CreateTaskDialog
          onClose={() => setCreating(false)}
          onSubmit={async (input, idempotencyKey) => {
            const task = await api.createTask(input, idempotencyKey);
            tasks.reload();
            return task;
          }}
        />
      ) : null}
    </div>
  );
}
