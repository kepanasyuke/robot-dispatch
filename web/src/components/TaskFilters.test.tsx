import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { TaskFilters } from "./TaskFilters";
import type { TaskFilters as Filters } from "../api/types";

function setup(value: Filters = { statuses: [] }, types = ["delivery", "patrol"]) {
  const onChange = vi.fn();
  render(<TaskFilters value={value} types={types} onChange={onChange} />);
  return { onChange };
}

describe("TaskFilters", () => {
  it("показывает чип на каждый статус", () => {
    setup();
    expect(screen.getByRole("button", { name: "В очереди" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Провалена" })).toBeInTheDocument();
  });

  it("добавляет статус в фильтр", async () => {
    const { onChange } = setup();
    await userEvent.click(screen.getByRole("button", { name: "Повтор" }));
    expect(onChange).toHaveBeenCalledWith({ statuses: ["retrying"] });
  });

  it("убирает статус из фильтра", async () => {
    const { onChange } = setup({ statuses: ["pending", "failed"] });
    await userEvent.click(screen.getByRole("button", { name: "В очереди" }));
    expect(onChange).toHaveBeenCalledWith({ statuses: ["failed"] });
  });

  it("помечает выбранные статусы", () => {
    setup({ statuses: ["running"] });
    expect(screen.getByRole("button", { name: "Выполняется" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("button", { name: "Успешно" })).toHaveAttribute("aria-pressed", "false");
  });

  it("передаёт выбранный тип", async () => {
    const { onChange } = setup();
    await userEvent.selectOptions(screen.getByLabelText("Тип задачи"), "patrol");
    expect(onChange).toHaveBeenCalledWith({ statuses: [], type: "patrol" });
  });

  it("сбрасывает тип при выборе «Все типы»", async () => {
    const { onChange } = setup({ statuses: [], type: "patrol" });
    await userEvent.selectOptions(screen.getByLabelText("Тип задачи"), "");
    expect(onChange).toHaveBeenCalledWith({ statuses: [], type: undefined });
  });

  it("передаёт поисковый запрос", async () => {
    const { onChange } = setup();
    await userEvent.type(screen.getByLabelText("Поиск по задачам"), "bat");
    expect(onChange).toHaveBeenCalledWith({ statuses: [], query: "b" });
    expect(onChange).toHaveBeenCalledTimes(3);
  });

  it("сбрасывает все фильтры", async () => {
    const { onChange } = setup({ statuses: ["failed"], type: "delivery", query: "x" });
    await userEvent.click(screen.getByRole("button", { name: "Сбросить" }));
    expect(onChange).toHaveBeenCalledWith({
      statuses: [],
      type: undefined,
      robotId: undefined,
      query: "",
    });
  });

  it("показывает варианты типов", () => {
    setup({ statuses: [] }, ["delivery", "patrol", "inventory"]);
    const options = screen.getAllByRole("option").map((option) => option.textContent);
    expect(options).toEqual(["Все типы", "delivery", "patrol", "inventory"]);
  });
});
