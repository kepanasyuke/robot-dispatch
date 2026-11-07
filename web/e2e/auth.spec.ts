import { expect, test } from "@playwright/test";

const MOCK = "http://127.0.0.1:8787";

test.describe("вход и роли", () => {
  test("без сессии показывает экран входа", async ({ page }) => {
    await page.goto("/#/");

    await expect(page.getByRole("form", { name: "Вход в консоль" })).toBeVisible();
    await expect(page.getByText("Наблюдатель")).toBeVisible();
  });

  test("вход оператором открывает консоль", async ({ page, request }) => {
    await request.post(`${MOCK}/__reset`);
    await page.goto("/#/");
    await page.getByRole("button", { name: "Войти" }).click();

    await expect(page.getByText("Задач всего")).toBeVisible();
    await expect(page.getByText("Оператор")).toBeVisible();
  });

  test("наблюдатель видит заблокированное создание", async ({ page, request }) => {
    await request.post(`${MOCK}/__reset`);
    await page.goto("/#/");
    await page.getByLabel(/Наблюдатель/).check();
    await page.getByRole("button", { name: "Войти" }).click();
    await page.getByRole("link", { name: "Задачи" }).click();

    await expect(page.getByRole("button", { name: "Новая задача" })).toBeDisabled();
  });

  test("выход возвращает на экран входа", async ({ page, request }) => {
    await request.post(`${MOCK}/__reset`);
    await page.goto("/#/");
    await page.getByRole("button", { name: "Войти" }).click();
    await page.getByRole("button", { name: "Выйти" }).click();

    await expect(page.getByRole("form", { name: "Вход в консоль" })).toBeVisible();
  });

  test("сессия живёт в рамках вкладки", async ({ page, request }) => {
    await request.post(`${MOCK}/__reset`);
    await page.goto("/#/");
    await page.getByRole("button", { name: "Войти" }).click();
    await page.reload();

    await expect(page.getByText("Задач всего")).toBeVisible();
  });
});
