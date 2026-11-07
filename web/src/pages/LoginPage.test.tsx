import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { LoginPage } from "./LoginPage";

function setup() {
  const onLogin = vi.fn();
  render(<LoginPage onLogin={onLogin} />);
  return { onLogin };
}

describe("LoginPage", () => {
  it("по умолчанию выбирает оператора", () => {
    setup();
    expect(screen.getByLabelText(/Оператор/)).toBeChecked();
  });

  it("входит как оператор без ключа", async () => {
    const { onLogin } = setup();
    await userEvent.click(screen.getByRole("button", { name: "Войти" }));
    expect(onLogin).toHaveBeenCalledWith({ role: "operator", apiKey: "" });
  });

  it("переключает роль на наблюдателя", async () => {
    const { onLogin } = setup();
    await userEvent.click(screen.getByLabelText(/Наблюдатель/));
    await userEvent.click(screen.getByRole("button", { name: "Войти" }));
    expect(onLogin).toHaveBeenCalledWith({ role: "viewer", apiKey: "" });
  });

  it("передаёт ключ без окружающих пробелов", async () => {
    const { onLogin } = setup();
    await userEvent.type(screen.getByLabelText(/Ключ доступа/), "  secret  ");
    await userEvent.click(screen.getByRole("button", { name: "Войти" }));
    expect(onLogin).toHaveBeenCalledWith({ role: "operator", apiKey: "secret" });
  });

  it("отклоняет слишком короткий ключ", async () => {
    const { onLogin } = setup();
    await userEvent.type(screen.getByLabelText(/Ключ доступа/), "abc");
    await userEvent.click(screen.getByRole("button", { name: "Войти" }));

    expect(onLogin).not.toHaveBeenCalled();
    expect(screen.getByRole("alert")).toHaveTextContent("слишком короткий");
  });

  it("сбрасывает ошибку при исправлении ключа", async () => {
    setup();
    const input = screen.getByLabelText(/Ключ доступа/);
    await userEvent.type(input, "abc");
    await userEvent.click(screen.getByRole("button", { name: "Войти" }));
    await userEvent.type(input, "def");

    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("объясняет, где хранится ключ", () => {
    setup();
    expect(screen.getByText(/sessionStorage/)).toBeInTheDocument();
  });
});
