import { describe, expect, it, vi } from "vitest";
import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ToastProvider, useToast } from "./Toasts";

function Trigger({ text, tone }: { text: string; tone?: "success" | "danger" }) {
  const notify = useToast();
  return (
    <button type="button" onClick={() => notify(text, tone)}>
      показать
    </button>
  );
}

function renderWithProvider(props: { text: string; tone?: "success" | "danger" }) {
  return render(
    <ToastProvider>
      <Trigger {...props} />
    </ToastProvider>,
  );
}

describe("ToastProvider", () => {
  it("показывает уведомление", async () => {
    renderWithProvider({ text: "Задача создана" });
    await userEvent.click(screen.getByRole("button", { name: "показать" }));

    expect(screen.getByRole("status")).toHaveTextContent("Задача создана");
  });

  it("применяет тон danger", async () => {
    renderWithProvider({ text: "Ошибка", tone: "danger" });
    await userEvent.click(screen.getByRole("button", { name: "показать" }));

    expect(screen.getByRole("status")).toHaveClass("toast--danger");
  });

  it("скрывает уведомление через 4 секунды", async () => {
    vi.useFakeTimers();
    renderWithProvider({ text: "Готово" });
    await act(async () => {
      screen.getByRole("button", { name: "показать" }).click();
    });
    expect(screen.getByRole("status")).toBeInTheDocument();

    await act(async () => {
      vi.advanceTimersByTime(4100);
    });

    expect(screen.queryByRole("status")).toBeNull();
    vi.useRealTimers();
  });

  it("показывает несколько уведомлений подряд", async () => {
    renderWithProvider({ text: "Раз" });
    const button = screen.getByRole("button", { name: "показать" });
    await userEvent.click(button);
    await userEvent.click(button);

    expect(screen.getAllByRole("status")).toHaveLength(2);
  });

  it("работает без провайдера как no-op", async () => {
    render(<Trigger text="без провайдера" />);
    await userEvent.click(screen.getByRole("button", { name: "показать" }));

    expect(screen.queryByRole("status")).toBeNull();
  });
});
