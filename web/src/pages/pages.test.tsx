import { describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { DashboardPage } from "./DashboardPage";
import { TasksPage } from "./TasksPage";
import { TaskDetailPage } from "./TaskDetailPage";
import { RobotsPage } from "./RobotsPage";
import { ApiContext } from "../hooks/useApi";
import { makeFakeApi, makeStats } from "../test/fakeApi";
import type { ApiClient } from "../api/client";
import { makeEvent, makeRobot, makeTask } from "../test/fixtures";

function renderWith(api: ApiClient, ui: React.ReactElement, route = "/") {
  return render(
    <ApiContext.Provider value={api}>
      <MemoryRouter initialEntries={[route]}>
        <Routes>
          <Route path="/" element={ui} />
          <Route path="/tasks" element={ui} />
          <Route path="/tasks/:taskId" element={ui} />
          <Route path="/robots" element={ui} />
        </Routes>
      </MemoryRouter>
    </ApiContext.Provider>,
  );
}

const tasks = [
  makeTask({ id: "t-1", type: "delivery", status: "pending", priority: 200 }),
  makeTask({ id: "t-2", type: "inventory", status: "failed", last_error: "battery critical" }),
  makeTask({ id: "t-3", type: "delivery", status: "succeeded", attempts: 2 }),
];

describe("DashboardPage", () => {
  it("показывает KPI и очередь", async () => {
    const api = makeFakeApi({ tasks, stats: makeStats({ pending: 1, failed: 1, succeeded: 1 }) });
    renderWith(api, <DashboardPage />);

    await waitFor(() => expect(screen.getByText("Задач всего")).toBeInTheDocument());
    expect(screen.getAllByText("В очереди").length).toBeGreaterThan(0);
    expect(screen.getByText("Повторы")).toBeInTheDocument();
    expect((await screen.findAllByText("Провалена")).length).toBeGreaterThan(0);
  });

  it("показывает роботов и состояние", async () => {
    const api = makeFakeApi({ tasks, robots: [makeRobot({ name: "robot-7" })] });
    renderWith(api, <DashboardPage />);

    expect(await screen.findByText("robot-7")).toBeInTheDocument();
    expect(await screen.findByText("Всё в порядке")).toBeInTheDocument();
  });

  it("показывает деградацию при проблемах брокера", async () => {
    const api = makeFakeApi({
      tasks,
      ready: { status: "degraded", checks: { database: "ok", rabbitmq: "unavailable" } },
    });
    renderWith(api, <DashboardPage />);

    expect(await screen.findByText("Работает с деградацией")).toBeInTheDocument();
  });

  it("показывает баннер при ошибке загрузки", async () => {
    const api = makeFakeApi({ failTasks: "connection refused" });
    renderWith(api, <DashboardPage />);

    expect(await screen.findByRole("alert")).toHaveTextContent("connection refused");
  });

  it("перезапрашивает данные по кнопке", async () => {
    const api = makeFakeApi({ failTasks: "boom" });
    renderWith(api, <DashboardPage />);

    await screen.findByRole("alert");
    await userEvent.click(screen.getByRole("button", { name: "Повторить" }));
    expect(api.getTasks.mock.calls.length).toBeGreaterThan(1);
  });
});

describe("TasksPage", () => {
  it("показывает все задачи", async () => {
    const api = makeFakeApi({ tasks });
    renderWith(api, <TasksPage />, "/tasks");

    await waitFor(() => expect(screen.getAllByTestId("task-row")).toHaveLength(3));
    expect(screen.getByText(/3 из 3/)).toBeInTheDocument();
  });

  it("фильтрует по статусу", async () => {
    const api = makeFakeApi({ tasks });
    renderWith(api, <TasksPage />, "/tasks");

    await screen.findAllByTestId("task-row");
    await userEvent.click(screen.getByRole("button", { name: "Провалена" }));
    expect(screen.getAllByTestId("task-row")).toHaveLength(1);
  });

  it("фильтрует по поиску", async () => {
    const api = makeFakeApi({ tasks });
    renderWith(api, <TasksPage />, "/tasks");

    await screen.findAllByTestId("task-row");
    await userEvent.type(screen.getByLabelText("Поиск по задачам"), "battery");
    expect(screen.getByText(/1 из 3/)).toBeInTheDocument();
  });

  it("показывает ошибку вместо таблицы", async () => {
    const api = makeFakeApi({ failTasks: "timeout" });
    renderWith(api, <TasksPage />, "/tasks");

    expect(await screen.findByRole("alert")).toHaveTextContent("timeout");
  });
});

describe("TaskDetailPage", () => {
  const running = makeTask({ id: "t-run", type: "delivery", status: "running", priority: 300 });

  function renderDetail(api: ApiClient, id = "t-run") {
    return renderWith(api, <TaskDetailPage />, `/tasks/${id}`);
  }

  it("показывает поля задачи", async () => {
    const api = makeFakeApi({ tasks: [running] });
    renderDetail(api);

    expect(await screen.findByText("Выполняется")).toBeInTheDocument();
    expect(screen.getByText("t-run")).toBeInTheDocument();
    expect(screen.getByText("300")).toBeInTheDocument();
  });

  it("показывает историю событий и путь", async () => {
    const api = makeFakeApi({
      tasks: [running],
      events: [
        makeEvent({ kind: "created", to_status: "pending" }),
        makeEvent({ id: "e-2", kind: "assigned", to_status: "assigned" }),
      ],
    });
    renderDetail(api);

    await waitFor(() => expect(screen.getAllByTestId("timeline-item")).toHaveLength(2));
    expect(screen.getByText("pending → assigned")).toBeInTheDocument();
  });

  it("показывает ошибку отмены и обновляет данные", async () => {
    const api = makeFakeApi({ tasks: [running], failCancel: "running tasks cannot be cancelled" });
    renderDetail(api);

    await userEvent.click(await screen.findByRole("button", { name: "Отменить" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("running tasks cannot be cancelled");
  });

  it("отменяет задачу и перезапрашивает её", async () => {
    const pending = makeTask({ id: "t-run", type: "delivery", status: "pending" });
    const api = makeFakeApi({ tasks: [pending] });
    renderDetail(api);

    await userEvent.click(await screen.findByRole("button", { name: "Отменить" }));
    await waitFor(() => expect(api.cancelTask).toHaveBeenCalledWith("t-run"));
    expect(api.getTask.mock.calls.length).toBeGreaterThan(1);
  });

  it("блокирует отмену завершённой задачи", async () => {
    const done = makeTask({ id: "t-run", status: "succeeded" });
    const api = makeFakeApi({ tasks: [done] });
    renderDetail(api);

    const button = await screen.findByRole("button", { name: "Завершена" });
    expect(button).toBeDisabled();
  });

  it("показывает ошибку загрузки задачи", async () => {
    const api = makeFakeApi({ failTask: "task not found" });
    renderDetail(api);

    expect(await screen.findByRole("alert")).toHaveTextContent("task not found");
  });

  it("показывает последнюю ошибку задачи", async () => {
    const failed = makeTask({ id: "t-run", status: "failed", last_error: "battery critical" });
    const api = makeFakeApi({ tasks: [failed] });
    renderDetail(api);

    expect(await screen.findByText("Последняя ошибка")).toBeInTheDocument();
    expect(screen.getAllByText("battery critical").length).toBeGreaterThan(0);
  });

  it("раскрывает payload", async () => {
    const api = makeFakeApi({ tasks: [running] });
    renderDetail(api);

    await userEvent.click(await screen.findByText("Payload"));
    expect(screen.getByText(/"target": "a"/)).toBeInTheDocument();
  });

  it("показывает ошибку истории событий", async () => {
    const api = makeFakeApi({ tasks: [running], failEvents: "events unavailable" });
    renderDetail(api);

    const banners = await screen.findAllByRole("alert");
    expect(banners.some((banner) => banner.textContent?.includes("events unavailable"))).toBe(true);
  });
});

describe("RobotsPage", () => {
  it("показывает парк и роботов без связи", async () => {
    const api = makeFakeApi({
      robots: [
        makeRobot({ id: "r-1", name: "robot-1", status: "idle" }),
        makeRobot({ id: "r-2", name: "robot-2", status: "offline", last_seen_at: null }),
      ],
    });
    renderWith(api, <RobotsPage />, "/robots");

    expect((await screen.findAllByText("robot-1")).length).toBeGreaterThan(0);
    expect(screen.getByText(/1 из 2 на связи/)).toBeInTheDocument();
    expect(screen.getByText(/нет/)).toBeInTheDocument();
  });

  it("сообщает, когда все роботы на связи", async () => {
    const api = makeFakeApi({
      robots: [makeRobot({ last_seen_at: new Date().toISOString() })],
    });
    renderWith(api, <RobotsPage />, "/robots");

    expect(await screen.findByText("Все роботы выходили на связь недавно")).toBeInTheDocument();
  });

  it("показывает ошибку загрузки", async () => {
    const api = makeFakeApi({ failRobots: "robots unavailable" });
    renderWith(api, <RobotsPage />, "/robots");

    expect(await screen.findByRole("alert")).toHaveTextContent("robots unavailable");
  });
});

describe("страницы без данных", () => {
  it("показывает заглушку, пока задача не загружена", async () => {
    const api = makeFakeApi({ tasks: [] });
    api.getTask.mockImplementation(() => new Promise(() => undefined));
    renderWith(api, <TaskDetailPage />, "/tasks/missing");

    expect(screen.getByText("Загрузка задачи…")).toBeInTheDocument();
    vi.restoreAllMocks();
  });
});
