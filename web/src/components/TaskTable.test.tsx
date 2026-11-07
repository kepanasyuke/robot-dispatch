import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { TaskTable } from "./TaskTable";
import { makeTask } from "../test/fixtures";

const now = new Date("2026-11-07T12:00:00+00:00");

function renderTable(tasks = [makeTask()]) {
  return render(
    <MemoryRouter>
      <TaskTable tasks={tasks} now={now} />
    </MemoryRouter>,
  );
}

describe("TaskTable", () => {
  it("показывает строку на каждую задачу", () => {
    renderTable([makeTask({ id: "a" }), makeTask({ id: "b" })]);
    expect(screen.getAllByTestId("task-row")).toHaveLength(2);
  });

  it("показывает пустое состояние", () => {
    renderTable([]);
    expect(screen.getByText("Задач нет")).toBeInTheDocument();
  });

  it("ведёт на карточку задачи", () => {
    renderTable([makeTask({ type: "delivery" })]);
    expect(screen.getByRole("link", { name: "delivery" })).toHaveAttribute(
      "href",
      "/tasks/11111111-1111-4111-8111-111111111111",
    );
  });

  it("переводит статус на русский", () => {
    renderTable([makeTask({ status: "failed" })]);
    expect(screen.getByText("Провалена")).toBeInTheDocument();
  });

  it("показывает ошибку задачи", () => {
    renderTable([makeTask({ status: "failed", last_error: "battery critical" })]);
    expect(screen.getByText("battery critical")).toBeInTheDocument();
  });

  it("показывает прочерк без робота", () => {
    renderTable([makeTask({ robot_id: null })]);
    expect(screen.getByText("—")).toBeInTheDocument();
  });

  it("показывает счётчик попыток", () => {
    renderTable([makeTask({ attempts: 2, max_attempts: 5 })]);
    expect(screen.getByText("2 / 5")).toBeInTheDocument();
  });

  it("показывает приоритет", () => {
    renderTable([makeTask({ priority: 777 })]);
    expect(screen.getByText("777")).toBeInTheDocument();
  });

  it("обрезает идентификатор робота", () => {
    renderTable([makeTask({ robot_id: "abcdefgh-1111-4111-8111-111111111111" })]);
    expect(screen.getByText("abcdefgh")).toBeInTheDocument();
  });
});

describe("TaskTable: сортировка", () => {
  function renderSortable(
    onSort = vi.fn(),
    sort?: { key: "priority" | "created" | "available"; dir: "asc" | "desc" },
  ) {
    const view = render(
      <MemoryRouter>
        <TaskTable tasks={[makeTask()]} now={now} sort={sort} onSort={onSort} />
      </MemoryRouter>,
    );
    return { onSort, container: view.container };
  }

  it("вызывает onSort по клику на заголовок", async () => {
    const { onSort } = renderSortable();
    await userEvent.click(screen.getByRole("button", { name: /Приоритет/ }));
    expect(onSort).toHaveBeenCalledWith("priority");
  });

  it("помечает активную колонку и направление", () => {
    const { container } = renderSortable(vi.fn(), { key: "created", dir: "asc" });
    const headers = Array.from(container.querySelectorAll<HTMLTableCellElement>("th"));
    const created = headers.find((header) => header.textContent?.includes("Создана"));
    expect(created).toHaveAttribute("aria-sort", "ascending");
  });

  it("показывает стрелку направления", () => {
    renderSortable(vi.fn(), { key: "priority", dir: "desc" });
    expect(screen.getByRole("button", { name: /Приоритет/ })).toHaveTextContent("↓");
  });

  it("без onSort заголовки остаются текстом", () => {
    render(
      <MemoryRouter>
        <TaskTable tasks={[makeTask()]} now={now} />
      </MemoryRouter>,
    );
    expect(screen.queryByRole("button", { name: /Приоритет/ })).toBeNull();
  });
});

describe("TaskTable: взаимодействие", () => {
  it("не падает при клике по ссылке внутри MemoryRouter", async () => {
    renderTable([makeTask({ type: "patrol" })]);
    await userEvent.click(screen.getByRole("link", { name: "patrol" }));
    expect(screen.getByRole("link", { name: "patrol" })).toBeInTheDocument();
  });

  it("не вызывает обработчиков при рендере", () => {
    const spy = vi.fn();
    render(
      <MemoryRouter>
        <button type="button" onClick={spy}>
          <TaskTable tasks={[makeTask()]} now={now} />
        </button>
      </MemoryRouter>,
    );
    expect(spy).not.toHaveBeenCalled();
  });
});
