import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { EventTimeline } from "./EventTimeline";
import { makeEvent } from "../test/fixtures";

const now = new Date("2026-11-07T12:00:00+00:00");

describe("EventTimeline", () => {
  it("показывает пустое состояние", () => {
    render(<EventTimeline events={[]} now={now} />);
    expect(screen.getByText("Событий пока нет")).toBeInTheDocument();
  });

  it("рендерит элемент на каждое событие", () => {
    render(<EventTimeline events={[makeEvent({ id: "1" }), makeEvent({ id: "2" })]} now={now} />);
    expect(screen.getAllByTestId("timeline-item")).toHaveLength(2);
  });

  it("переводит вид события", () => {
    render(<EventTimeline events={[makeEvent({ kind: "lease_expired" })]} now={now} />);
    expect(screen.getByText("Аренда истекла")).toBeInTheDocument();
  });

  it("показывает сообщение события", () => {
    render(<EventTimeline events={[makeEvent({ message: "retry in 30.0s" })]} now={now} />);
    expect(screen.getByText("retry in 30.0s")).toBeInTheDocument();
  });

  it("показывает переход статусов", () => {
    render(
      <EventTimeline
        events={[makeEvent({ from_status: "running", to_status: "retrying" })]}
        now={now}
      />,
    );
    expect(screen.getByText("running → retrying")).toBeInTheDocument();
  });

  it("сортирует события по времени", () => {
    render(
      <EventTimeline
        events={[
          makeEvent({ id: "late", kind: "succeeded", created_at: "2026-11-07T11:30:00+00:00" }),
          makeEvent({ id: "early", kind: "created", created_at: "2026-11-07T10:00:00+00:00" }),
        ]}
        now={now}
      />,
    );
    const items = screen.getAllByTestId("timeline-item");
    expect(items[0]).toHaveTextContent("Задача создана");
    expect(items[1]).toHaveTextContent("Выполнена");
  });

  it("не показывает сообщение, если его нет", () => {
    render(<EventTimeline events={[makeEvent({ message: null })]} now={now} />);
    expect(screen.queryByRole("paragraph")).toBeNull();
  });
});

describe("EventTimeline: производительность", () => {
  it("рендерит сто событий", () => {
    const events = Array.from({ length: 100 }, (_, index) =>
      makeEvent({ id: `e-${index}`, created_at: new Date(now.getTime() - index * 1000).toISOString() }),
    );
    render(<EventTimeline events={events} now={now} />);
    expect(screen.getAllByTestId("timeline-item")).toHaveLength(100);
  });

  it("не перерисовывает при повторном рендере списка", async () => {
    const onChange = vi.fn();
    const { rerender } = render(
      <div onChange={onChange}>
        <EventTimeline events={[makeEvent()]} now={now} />
      </div>,
    );
    rerender(
      <div onChange={onChange}>
        <EventTimeline events={[makeEvent()]} now={now} />
      </div>,
    );
    expect(onChange).not.toHaveBeenCalled();
  });
});

describe("EventTimeline: доступность", () => {
  it("использует список", () => {
    render(<EventTimeline events={[makeEvent()]} now={now} />);
    expect(screen.getByRole("list")).toBeInTheDocument();
  });

  it("проставляет дату в time", async () => {
    render(<EventTimeline events={[makeEvent()]} now={now} />);
    const time = screen.getByText("2 часа назад");
    expect(time).toBeInTheDocument();
    expect(time.tagName.toLowerCase()).toBe("time");
    await userEvent.hover(time);
    expect(time).toHaveAttribute("title");
  });
});
