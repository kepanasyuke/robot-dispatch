import { beforeEach, describe, expect, it } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { App } from "./App";
import { clearSession, loadSession, saveSession } from "./auth/session";
import { makeFakeApi } from "./test/fakeApi";
import { makeTask } from "./test/fixtures";

function renderApp() {
  const api = makeFakeApi({ tasks: [makeTask({ type: "delivery" })] });
  render(<App clientFactory={() => api} />);
  return api;
}

async function login(role: "operator" | "viewer" = "operator") {
  if (role === "viewer") {
    await userEvent.click(screen.getByLabelText(/Наблюдатель/));
  }
  await userEvent.click(screen.getByRole("button", { name: "Войти" }));
}

describe("App: вход", () => {
  beforeEach(() => {
    clearSession();
    window.location.hash = "";
  });

  it("начинает с экрана входа", () => {
    renderApp();
    expect(screen.getByRole("form", { name: "Вход в консоль" })).toBeInTheDocument();
  });

  it("после входа показывает консоль", async () => {
    renderApp();
    await login();

    await waitFor(() => expect(screen.getByText("Robot Dispatch")).toBeInTheDocument());
    expect(screen.getByText("Задач всего")).toBeInTheDocument();
  });

  it("сохраняет сессию в sessionStorage", async () => {
    renderApp();
    await login();

    expect(loadSession()).toEqual({ role: "operator", apiKey: "" });
  });

  it("показывает роль в шапке", async () => {
    renderApp();
    await login("viewer");

    expect(await screen.findByText("Наблюдатель")).toBeInTheDocument();
  });

  it("выход возвращает на экран входа", async () => {
    renderApp();
    await login();
    await userEvent.click(screen.getByRole("button", { name: "Выйти" }));

    expect(await screen.findByRole("form", { name: "Вход в консоль" })).toBeInTheDocument();
    expect(loadSession()).toBeNull();
  });

  it("восстанавливает сессию из хранилища", async () => {
    saveSession({ role: "operator", apiKey: "k" });
    renderApp();

    await waitFor(() => expect(screen.getByText("Оператор")).toBeInTheDocument());
  });
});

describe("App: навигация", () => {
  beforeEach(() => {
    saveSession({ role: "operator", apiKey: "" });
    window.location.hash = "";
  });

  it("открывает обзор по умолчанию", async () => {
    renderApp();
    await waitFor(() => expect(screen.getByText("Задач всего")).toBeInTheDocument());
    expect(screen.getByRole("link", { name: "Обзор" })).toBeInTheDocument();
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

  it("показывает подвал с источниками", async () => {
    renderApp();
    await waitFor(() =>
      expect(screen.getByText("FastAPI · PostgreSQL · RabbitMQ")).toBeInTheDocument(),
    );
  });

  it("показывает состояние сервиса в шапке", async () => {
    renderApp();
    await waitFor(() =>
      expect(screen.getByTitle("База и брокер доступны")).toHaveTextContent("Всё в порядке"),
    );
  });

  it("показывает 404 для неизвестного маршрута", async () => {
    window.location.hash = "#/nope";
    renderApp();
    expect(await screen.findByText("Страница не найдена")).toBeInTheDocument();
  });
});
