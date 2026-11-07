import { useMemo, useState } from "react";
import type { TaskFilters as Filters } from "../api/types";
import { useApi } from "../hooks/useApi";
import { useResource } from "../hooks/useResource";
import { ErrorBanner } from "../components/ErrorBanner";
import { Panel } from "../components/KpiCards";
import { TaskFilters } from "../components/TaskFilters";
import { TaskTable } from "../components/TaskTable";
import { distinctTypes, filterTasks, sortTasks } from "../lib/tasks";
import { formatDateTime } from "../lib/format";

export function TasksPage() {
  const api = useApi();
  const [filters, setFilters] = useState<Filters>({ statuses: [] });
  const tasks = useResource(() => api.getTasks({}, { limit: 200 }), [], 3000);

  const items = tasks.data?.items ?? [];
  const types = useMemo(() => distinctTypes(items), [items]);
  const visible = useMemo(() => sortTasks(filterTasks(items, filters), "created", "desc"), [items, filters]);

  return (
    <div className="stack">
      <Panel
        title="Задачи"
        actions={
          <span className="muted">
            {visible.length} из {items.length}
            {tasks.updatedAt ? ` · обновлено ${formatDateTime(tasks.updatedAt.toISOString())}` : ""}
          </span>
        }
      >
        <TaskFilters value={filters} types={types} onChange={setFilters} />
        {tasks.error ? (
          <ErrorBanner message={tasks.error} onRetry={tasks.reload} />
        ) : (
          <TaskTable tasks={visible} />
        )}
      </Panel>
    </div>
  );
}
