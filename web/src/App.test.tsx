import { describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { App } from "./App";
import { ApiContext, useApi } from "./hooks/useApi";
import { makeFakeApi } from "./test/fakeApi";
import { makeTask } from "./test/fixtures";

function renderApp() {
  const api = makeFakeApi({ tasks: [makeTask({ type: "delivery" })] });
  render(
    <ApiContext.Provider value={api}>
      <App />
    </ApiContext.Provider>,
  );
  return api;
}

describe("useApi", () => {
  it("падает без провайдера", () => {
    const Probe = () => {
      useApi();
      return null;
    };
    expect(() => render(<Probe />)).toThrow("ApiContext is not provided");
  });

  it("возвращает клиента из провайдера", () => {
    const api = makeFakeApi();
    const Probe = () => {
      const client = useApi();
      return <span>{client.baseUrl}</span>;
    };
    render(
      <ApiContext.Provider value={api}>
        <Probe />
      </ApiContext.Provider>,
    );
    expect(screen.getByText("http://fake/api/v1")).toBeInTheDocument();
  });
});

describe("App", () => {
  it("рисует шапку и обзор", async () => {
    renderApp();
    expect(screen.getByText("Robot Dispatch")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Обзор" })).toBeInTheDocument();
    await waitFor(() => expect(screen.getByText("Задач всего")).toBeInTheDocument());
  });

  it("переходит на вкладку задач", async () => {
    renderApp();
    await userEvent.click(screen.getByRole("link", { name: "Задачи" }));
    expect(await screen.findByRole("heading", { name: "Задачи" })).toBeInTheDocument();
  });

  it("переходит на вкладку роботов", async () => {
    renderApp();
    await userEvent.click(screen.getByRole("link", { name: "Роботы" }));
    expect(await screen.findByRole("heading", { name: "Парк роботов" })).toBeInTheDocument();
  });

  it("показывает подвал с источниками", () => {
    renderApp();
    expect(screen.getByText("FastAPI · PostgreSQL · RabbitMQ")).toBeInTheDocument();
  });

  it("показывает состояние сервиса в шапке", async () => {
    renderApp();
    await waitFor(() =>
      expect(screen.getByTitle("База и брокер доступны")).toHaveTextContent("Всё в порядке"),
    );
  });

  it("показывает 404 для неизвестного маршрута", async () => {
    const api = makeFakeApi();
    window.location.hash = "#/nope";
    render(
      <ApiContext.Provider value={api}>
        <App />
      </ApiContext.Provider>,
    );
    expect(await screen.findByText("Страница не найдена")).toBeInTheDocument();
    vi.restoreAllMocks();
  });
});
