import { describe, expect, it, vi } from "vitest";
import { useRef } from "react";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useFocusTrap } from "./useFocusTrap";

function Trap({ onClose }: { onClose: () => void }) {
  const ref = useRef<HTMLDivElement>(null);
  useFocusTrap(ref, onClose);
  return (
    <div ref={ref} role="dialog" aria-label="trap">
      <button type="button">первая</button>
      <input data-autofocus aria-label="поле" />
      <button type="button">последняя</button>
    </div>
  );
}

describe("useFocusTrap", () => {
  it("фокусирует элемент с data-autofocus", () => {
    render(<Trap onClose={() => undefined} />);
    expect(screen.getByLabelText("поле")).toHaveFocus();
  });

  it("закрывает по Escape", async () => {
    const onClose = vi.fn();
    render(<Trap onClose={onClose} />);

    await userEvent.keyboard("{Escape}");

    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("переносит фокус с последнего на первый по Tab", async () => {
    render(<Trap onClose={() => undefined} />);
    screen.getByRole("button", { name: "последняя" }).focus();

    await userEvent.tab();

    expect(screen.getByRole("button", { name: "первая" })).toHaveFocus();
  });

  it("переносит фокус с первого на последний по Shift+Tab", async () => {
    render(<Trap onClose={() => undefined} />);
    screen.getByRole("button", { name: "первая" }).focus();

    await userEvent.tab({ shift: true });

    expect(screen.getByRole("button", { name: "последняя" })).toHaveFocus();
  });

  it("возвращает фокус после размонтирования", async () => {
    const outside = document.createElement("button");
    outside.textContent = "снаружи";
    document.body.appendChild(outside);
    outside.focus();

    const { unmount } = render(<Trap onClose={() => undefined} />);
    expect(screen.getByLabelText("поле")).toHaveFocus();

    unmount();

    expect(outside).toHaveFocus();
    outside.remove();
  });

  it("не мешает обычному Tab внутри", async () => {
    render(<Trap onClose={() => undefined} />);
    screen.getByLabelText("поле").focus();

    await userEvent.tab();

    expect(screen.getByRole("button", { name: "последняя" })).toHaveFocus();
  });
});
