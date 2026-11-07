import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { RobotGrid } from "./RobotGrid";
import { KpiCards, Panel } from "./KpiCards";
import { ErrorBanner } from "./ErrorBanner";
import { EmptyState } from "./EmptyState";
import { ServiceHealthPill } from "./ServiceHealthPill";
import { makeRobot } from "../test/fixtures";

const now = new Date("2026-11-07T12:00:00+00:00");

describe("RobotGrid", () => {
  it("показывает пустое состояние", () => {
    render(<RobotGrid robots={[]} now={now} />);
    expect(screen.getByText("Парк пуст")).toBeInTheDocument();
  });

  it("рендерит карточку на робота", () => {
    render(<RobotGrid robots={[makeRobot({ id: "a" }), makeRobot({ id: "b" })]} now={now} />);
    expect(screen.getAllByTestId("robot-card")).toHaveLength(2);
  });

  it("переводит статус робота", () => {
    render(<RobotGrid robots={[makeRobot({ status: "offline" })]} now={now} />);
    expect(screen.getByText("Не в сети")).toBeInTheDocument();
  });

  it("показывает возможности", () => {
    render(<RobotGrid robots={[makeRobot({ capabilities: ["delivery", "patrol"] })]} now={now} />);
    expect(screen.getByText("delivery")).toBeInTheDocument();
    expect(screen.getByText("patrol")).toBeInTheDocument();
  });

  it("показывает прочерк без текущей задачи", () => {
    render(<RobotGrid robots={[makeRobot({ current_task_id: null })]} now={now} />);
    expect(screen.getByText("—")).toBeInTheDocument();
  });

  it("обрезает идентификатор задачи", () => {
    render(<RobotGrid robots={[makeRobot({ current_task_id: "abcdefgh-1111" })]} now={now} />);
    expect(screen.getByText("abcdefgh")).toBeInTheDocument();
  });
});

describe("KpiCards", () => {
  it("рендерит значения и подсказки", () => {
    render(
      <KpiCards
        items={[
          { label: "Задач всего", value: "12", hint: "3 в работе" },
          { label: "Повторы", value: "2", tone: "warning" },
        ]}
      />,
    );
    expect(screen.getByText("Задач всего")).toBeInTheDocument();
    expect(screen.getByText("12")).toBeInTheDocument();
    expect(screen.getByText("3 в работе")).toBeInTheDocument();
    expect(screen.getByText("Повторы")).toBeInTheDocument();
  });

  it("применяет тон к карточке", () => {
    const { container } = render(<KpiCards items={[{ label: "x", value: "1", tone: "danger" }]} />);
    expect(container.querySelector(".kpi--danger")).not.toBeNull();
  });

  it("не рендерит подсказку без текста", () => {
    const { container } = render(<KpiCards items={[{ label: "x", value: "1" }]} />);
    expect(container.querySelector(".kpi__hint")).toBeNull();
  });
});

describe("Panel", () => {
  it("рендерит заголовок и содержимое", () => {
    render(
      <Panel title="Задачи">
        <p>тело</p>
      </Panel>,
    );
    expect(screen.getByRole("heading", { name: "Задачи" })).toBeInTheDocument();
    expect(screen.getByText("тело")).toBeInTheDocument();
  });

  it("рендерит действия", () => {
    render(
      <Panel title="Задачи" actions={<button type="button">обновить</button>}>
        <p>тело</p>
      </Panel>,
    );
    expect(screen.getByRole("button", { name: "обновить" })).toBeInTheDocument();
  });
});

describe("ErrorBanner", () => {
  it("показывает сообщение и роль alert", () => {
    render(<ErrorBanner message="Сервис недоступен" />);
    expect(screen.getByRole("alert")).toHaveTextContent("Сервис недоступен");
  });

  it("не показывает кнопку без обработчика", () => {
    render(<ErrorBanner message="ошибка" />);
    expect(screen.queryByRole("button")).toBeNull();
  });

  it("вызывает обработчик повтора", () => {
    let called = false;
    render(<ErrorBanner message="ошибка" onRetry={() => (called = true)} />);
    screen.getByRole("button", { name: "Повторить" }).click();
    expect(called).toBe(true);
  });
});

describe("EmptyState", () => {
  it("показывает заголовок и подсказку", () => {
    render(<EmptyState title="Пусто" hint="добавьте данные" />);
    expect(screen.getByText("Пусто")).toBeInTheDocument();
    expect(screen.getByText("добавьте данные")).toBeInTheDocument();
  });

  it("обходится без подсказки", () => {
    render(<EmptyState title="Пусто" />);
    expect(screen.queryByRole("paragraph")).toBeNull();
  });
});

describe("ServiceHealthPill", () => {
  it.each([
    ["ok", "Всё в порядке", "success"],
    ["degraded", "Работает с деградацией", "warning"],
    ["down", "Недоступно", "danger"],
    ["unknown", "Нет данных", "neutral"],
  ] as const)("показывает состояние %s", (state, label, tone) => {
    const { container } = render(
      <ServiceHealthPill health={{ state, label, detail: "детали" }} />,
    );
    expect(screen.getByText(label)).toBeInTheDocument();
    expect(container.querySelector(`.health--${tone}`)).not.toBeNull();
  });
});
