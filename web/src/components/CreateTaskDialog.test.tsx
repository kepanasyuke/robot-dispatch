import { describe, expect, it, vi } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { CreateTaskDialog } from "./CreateTaskDialog";
import { ApiError } from "../api/client";
import type { CreateTaskInput, Task } from "../api/types";
import { makeTask } from "../test/fixtures";

function setup(onSubmit = vi.fn(async (_input: CreateTaskInput, _key: string) => makeTask())) {
  const onClose = vi.fn();
  render(<CreateTaskDialog onClose={onClose} onSubmit={onSubmit} />);
  return { onSubmit, onClose };
}

describe("CreateTaskDialog", () => {
  it("блокирует отправку без типа", async () => {
    const { onSubmit } = setup();
    expect(screen.getByRole("button", { name: "Создать" })).toBeDisabled();
    await userEvent.type(screen.getByLabelText("Тип"), "delivery");
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it("создаёт задачу с полями формы", async () => {
    const { onSubmit, onClose } = setup();
    await userEvent.type(screen.getByLabelText("Тип"), " Delivery ");
    await userEvent.clear(screen.getByLabelText(/Приоритет/));
    await userEvent.type(screen.getByLabelText(/Приоритет/), "250");
    await userEvent.clear(screen.getByLabelText("Payload (JSON)"));
    await userEvent.type(screen.getByLabelText("Payload (JSON)"), '{{"a":1}');
    await userEvent.click(screen.getByRole("button", { name: "Создать" }));

    await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(1));
    const [input, key] = onSubmit.mock.calls[0] as [CreateTaskInput, string];
    expect(input.type).toBe("Delivery");
    expect(input.priority).toBe(250);
    expect(input.payload).toEqual({ a: 1 });
    expect(key.length).toBeGreaterThan(8);
    expect(onClose).toHaveBeenCalled();
  });

  it("сообщает о битом JSON и не отправляет", async () => {
    const { onSubmit } = setup();
    await userEvent.type(screen.getByLabelText("Тип"), "delivery");
    await userEvent.clear(screen.getByLabelText("Payload (JSON)"));
    await userEvent.type(screen.getByLabelText("Payload (JSON)"), "{{");

    expect(screen.getByText("Payload не является валидным JSON")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Создать" })).toBeDisabled();
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it("отклоняет массив в payload", async () => {
    setup();
    await userEvent.type(screen.getByLabelText("Тип"), "delivery");
    fireEvent.change(screen.getByLabelText("Payload (JSON)"), { target: { value: "[1,2]" } });

    expect(screen.getByText("Payload должен быть JSON-объектом")).toBeInTheDocument();
  });

  it("показывает ошибку API", async () => {
    const failing = vi.fn(async () => {
      throw new ApiError(422, "body.priority: Input should be <= 1000");
    });
    setup(failing);
    await userEvent.type(screen.getByLabelText("Тип"), "delivery");
    await userEvent.click(screen.getByRole("button", { name: "Создать" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("(код 422)");
  });

  it("закрывается по кнопке Отмена", async () => {
    const { onClose } = setup();
    await userEvent.click(screen.getByRole("button", { name: "Отмена" }));
    expect(onClose).toHaveBeenCalled();
  });

  it("закрывается по кнопке в шапке", async () => {
    const { onClose } = setup();
    await userEvent.click(screen.getByRole("button", { name: "Закрыть" }));
    expect(onClose).toHaveBeenCalled();
  });

  it("закрывается по Escape", async () => {
    const { onClose } = setup();
    await userEvent.keyboard("{Escape}");
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("ставит фокус в поле типа при открытии", () => {
    setup();
    expect(screen.getByLabelText("Тип")).toHaveFocus();
  });

  it("позволяет править Idempotency-Key", async () => {
    const { onSubmit } = setup();
    const field = screen.getByLabelText("Idempotency-Key");
    await userEvent.clear(field);
    await userEvent.type(field, "ui-key-1");
    await userEvent.type(screen.getByLabelText("Тип"), "delivery");
    await userEvent.click(screen.getByRole("button", { name: "Создать" }));

    await waitFor(() => expect(onSubmit).toHaveBeenCalled());
    expect(onSubmit.mock.calls[0]?.[1]).toBe("ui-key-1");
  });

  it("рендерится как модальное окно", () => {
    setup();
    const dialog = screen.getByRole("dialog");
    expect(dialog).toHaveAttribute("aria-modal", "true");
    expect(dialog).toHaveAccessibleName("Новая задача");
  });

  it("шлёт пустой payload как объект", async () => {
    const { onSubmit } = setup();
    await userEvent.clear(screen.getByLabelText("Payload (JSON)"));
    await userEvent.type(screen.getByLabelText("Тип"), "patrol");
    await userEvent.click(screen.getByRole("button", { name: "Создать" }));

    await waitFor(() => expect(onSubmit).toHaveBeenCalled());
    expect((onSubmit.mock.calls[0]?.[0] as CreateTaskInput).payload).toEqual({});
  });

  it("не отправляет форму повторно во время запроса", async () => {
    let release: (task: Task) => void = () => undefined;
    const slow = vi.fn(
      () =>
        new Promise<Task>((resolve) => {
          release = resolve;
        }),
    );
    setup(slow);
    await userEvent.type(screen.getByLabelText("Тип"), "delivery");
    await userEvent.click(screen.getByRole("button", { name: "Создать" }));

    expect(await screen.findByRole("button", { name: "Создаём…" })).toBeDisabled();
    release(makeTask());
  });
});
