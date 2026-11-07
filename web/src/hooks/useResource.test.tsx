import { afterEach, describe, expect, it, vi } from "vitest";
import { act, renderHook, waitFor } from "@testing-library/react";
import { useResource } from "./useResource";

describe("useResource", () => {
  afterEach(() => {
    vi.useRealTimers();
  });

  it("загружает данные и снимает флаг загрузки", async () => {
    const loader = vi.fn(async () => 42);
    const { result } = renderHook(() => useResource(loader, []));

    expect(result.current.loading).toBe(true);
    await waitFor(() => expect(result.current.data).toBe(42));
    expect(result.current.loading).toBe(false);
    expect(result.current.error).toBeNull();
    expect(result.current.updatedAt).toBeInstanceOf(Date);
  });

  it("кладёт текст ошибки", async () => {
    const loader = vi.fn(async () => {
      throw new Error("boom");
    });
    const { result } = renderHook(() => useResource(loader, []));

    await waitFor(() => expect(result.current.error).toBe("boom"));
    expect(result.current.data).toBeNull();
  });

  it("повторяет загрузку по reload", async () => {
    let value = 1;
    const loader = vi.fn(async () => value);
    const { result } = renderHook(() => useResource(loader, []));

    await waitFor(() => expect(result.current.data).toBe(1));
    value = 2;
    act(() => result.current.reload());
    await waitFor(() => expect(result.current.data).toBe(2));
    expect(loader).toHaveBeenCalledTimes(2);
  });

  it("перезагружает данные при смене зависимостей", async () => {
    const loader = vi.fn(async (id: string) => id);
    const { result, rerender } = renderHook(({ id }) => useResource(() => loader(id), [id]), {
      initialProps: { id: "a" },
    });

    await waitFor(() => expect(result.current.data).toBe("a"));
    rerender({ id: "b" });
    await waitFor(() => expect(result.current.data).toBe("b"));
  });

  it("опрашивает сервер по интервалу", async () => {
    vi.useFakeTimers();
    const loader = vi.fn(async () => "ping");
    renderHook(() => useResource(loader, [], 1000));

    await vi.advanceTimersByTimeAsync(0);
    expect(loader).toHaveBeenCalledTimes(1);

    await vi.advanceTimersByTimeAsync(3000);
    expect(loader).toHaveBeenCalledTimes(4);
  });

  it("останавливает опрос после размонтирования", async () => {
    vi.useFakeTimers();
    const loader = vi.fn(async () => "ping");
    const { unmount } = renderHook(() => useResource(loader, [], 1000));

    await vi.advanceTimersByTimeAsync(0);
    unmount();
    await vi.advanceTimersByTimeAsync(5000);

    expect(loader).toHaveBeenCalledTimes(1);
  });

  it("не обновляет состояние после размонтирования", async () => {
    let resolve: (value: string) => void = () => undefined;
    const loader = vi.fn(
      () =>
        new Promise<string>((done) => {
          resolve = done;
        }),
    );
    const { unmount, result } = renderHook(() => useResource(loader, []));

    unmount();
    resolve("late");
    await Promise.resolve();

    expect(result.current.data).toBeNull();
  });

  it("не опрашивает при нулевом интервале", async () => {
    vi.useFakeTimers();
    const loader = vi.fn(async () => "once");
    renderHook(() => useResource(loader, [], 0));

    await vi.advanceTimersByTimeAsync(0);
    await vi.advanceTimersByTimeAsync(10_000);

    expect(loader).toHaveBeenCalledTimes(1);
  });
});
